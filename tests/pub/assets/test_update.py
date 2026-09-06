import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.pub.assets.test_context import HOOK, SKILL, service
from tests.pub.assets.test_inspection import source_asset

from zuat.pub import AssetSelector, ZuatRequest


@pytest.mark.parametrize("kind", ["skill", "hook"])
def test_public_update_reopen_restore_remove_preserves_other_project(tmp_path, kind):
    asset = source_asset(tmp_path, kind)
    a, b = tmp_path / "a", tmp_path / "b"
    for project in (a, b):
        with service(tmp_path, project) as current:
            assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
    if kind == "skill":
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
    else:
        Path(asset.source).write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [{"hooks": [{"type": "command", "command": "echo B"}]}]
                    }
                }
            ),
            encoding="utf-8",
        )
    with service(tmp_path, a) as current:
        assert current.inspect_asset(asset).classification == "outdated"
        updated = current.update_asset(asset)
        assert updated.ok, updated.diagnostics
        assert updated.data["changed"]
        assert current.inspect_asset(asset).classification == "current"
        noop_history = current.registry.history()
        noop = current.update_asset(asset)
        assert noop.ok and not noop.data["changed"]
        assert current.registry.history() == noop_history
    with service(tmp_path, a) as current:
        restored = current.restore_all(
            updated.operation_id,
            AssetSelector("claude", kind=kind, scope="project"),
            force=True,
        )
        assert restored.ok, restored.diagnostics
        assert current.inspect_asset(asset).classification == "outdated"
        removed = current.uninstall_all(
            AssetSelector("claude", kind=kind, scope="project")
        )
        assert removed.ok, removed.diagnostics
        assert current.inspect_asset(asset).classification == "absent"
    with service(tmp_path, b) as current:
        assert current.inspect_asset(asset).classification == "outdated"


def test_force_update_restores_actual_local_content_and_authority(tmp_path):
    asset = source_asset(tmp_path)
    project = tmp_path / "a"
    with service(tmp_path, project) as current:
        assert not current.update_asset(asset).ok
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        assert current.inspect_asset(asset).classification == "outdated"
        native = project / ".claude/skills/reviewer/SKILL.md"
        native.write_text(SKILL + "LOCAL", encoding="utf-8")
        assert not current.update_asset(asset).ok
        repaired = current.update_asset(asset, force=True)
        assert repaired.ok, repaired.diagnostics
        restored = current.restore_all(
            repaired.operation_id, AssetSelector("claude", kind="skill"), force=True
        )
        assert restored.ok, restored.diagnostics
        assert native.read_text(encoding="utf-8") == SKILL + "LOCAL"
        assert current.inspect_asset(asset).classification == "conflict"


def test_skill_update_removes_obsolete_projection_and_preserves_neighbor(tmp_path):
    asset = source_asset(tmp_path)
    Path(asset.source, "obsolete.txt").write_text("old", encoding="utf-8")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        neighbor = tmp_path / "a/.claude/skills/neighbor/notes"
        neighbor.parent.mkdir(parents=True)
        neighbor.write_text("untouched", encoding="utf-8")
        Path(asset.source, "obsolete.txt").unlink()
        assert current.update_asset(asset).ok
        assert not (tmp_path / "a/.claude/skills/reviewer/obsolete.txt").exists()
        assert neighbor.read_text(encoding="utf-8") == "untouched"


@pytest.mark.parametrize("failure", ["mutation", "verification", "compensation"])
def test_failed_update_never_publishes_unverified_profile(
    tmp_path, monkeypatch, failure
):
    asset = source_asset(tmp_path)
    project = tmp_path / "a"
    with service(tmp_path, project) as current:
        installed = current.install(ZuatRequest(agents=("claude",), assets=(asset,)))
        assert installed.ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        resolver = current._resolver("claude")
        real_replace = resolver.replace_asset

        def fail(target):
            if failure != "mutation":
                real_replace(target)
            raise OSError("injected failure")

        monkeypatch.setattr(resolver, "replace_asset", fail)
        if failure == "compensation":
            monkeypatch.setattr(
                resolver,
                "materialize",
                lambda plan: (_ for _ in ()).throw(OSError("compensation failed")),
            )
        result = current.update_asset(asset)
        assert not result.ok
        profile_path = (
            current.registry.profile_root()
            / installed.assets[0].evidence["normalized_path"]
            / "SKILL.md"
        )
        assert profile_path.read_text(encoding="utf-8") == SKILL
        native = project / ".claude/skills/reviewer/SKILL.md"
        if failure == "compensation":
            assert current.registry.recovery_marker.exists()
        else:
            assert native.read_text(encoding="utf-8") == SKILL
            assert not current.registry.recovery_marker.exists()


def test_interrupted_update_survives_wrong_context_then_explicit_restore(
    tmp_path, monkeypatch
):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        resolver = current._resolver("claude")
        real_replace = resolver.replace_asset

        def interrupt(target):
            real_replace(target)
            raise KeyboardInterrupt()

        monkeypatch.setattr(resolver, "replace_asset", interrupt)
        with pytest.raises(KeyboardInterrupt):
            current.update_asset(asset)
        pending = json.loads(
            current.registry.recovery_marker.read_text(encoding="utf-8")
        )
        operation_id = pending["operation_id"]
    with service(tmp_path, tmp_path / "b") as other:
        assert other.registry.recovery_marker.exists()
        result = other.restore_all(
            operation_id, AssetSelector("claude", kind="skill"), force=True
        )
        assert not result.ok
        assert other.registry.recovery_marker.exists()
        assert (tmp_path / "a/.claude/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL + "B"
    with service(tmp_path, tmp_path / "a") as current:
        restored = current.restore_all(
            operation_id, AssetSelector("claude", kind="skill"), force=True
        )
        assert restored.ok, restored.diagnostics
        assert not current.registry.recovery_marker.exists()
        assert (tmp_path / "a/.claude/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL


@pytest.mark.parametrize("kind", ["skill", "hook"])
def test_forced_unowned_update_restore_does_not_adopt_prior_state(tmp_path, kind):
    from tests.pub.assets.test_context import native_assets

    asset = source_asset(tmp_path, kind)
    native_assets(tmp_path / "a")
    if kind == "skill":
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.inspect_asset(asset).classification == "unowned"
        assert not current.update_asset(asset).ok
        result = current.update_asset(asset, force=True)
        assert result.ok, result.diagnostics
        restored = current.restore_all(
            result.operation_id, AssetSelector("claude", kind=kind), force=True
        )
        assert restored.ok, restored.diagnostics
        inspection = current.inspect_asset(asset)
        assert inspection.classification == "unowned" and not inspection.owned


def test_revert_update_restores_conflicting_baseline(tmp_path):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        native = tmp_path / "a/.claude/skills/reviewer/SKILL.md"
        native.write_text(SKILL + "LOCAL", encoding="utf-8")
        result = current.update_asset(asset, force=True)
        assert result.ok
        reverted = current.revert(
            ZuatRequest(
                agents=("claude",), operation_id=result.operation_id, force=True
            )
        )
        assert reverted.ok, reverted.diagnostics
        assert native.read_text(encoding="utf-8") == SKILL + "LOCAL"
        assert current.inspect_asset(asset).classification == "conflict"
        observed = current.status(ZuatRequest(agents=("claude",))).assets
        assert (
            next(
                item for item in observed if item.ref.id == result.assets[0].ref.id
            ).authority.value
            == "conflicting"
        )


def test_profile_publication_uses_verified_source_snapshot(tmp_path, monkeypatch):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        source = Path(asset.source, "SKILL.md")
        source.write_text(SKILL + "B", encoding="utf-8")
        store = current.registry.store_profile_asset

        def edit_source_then_publish(*args, **kwargs):
            source.write_text(SKILL + "AFTER-VERIFY", encoding="utf-8")
            return store(*args, **kwargs)

        monkeypatch.setattr(
            current.registry, "store_profile_asset", edit_source_then_publish
        )
        result = current.update_asset(asset)
        assert result.ok, result.diagnostics
        payload = (
            current.registry.profile_root()
            / result.assets[0].evidence["normalized_path"]
            / "SKILL.md"
        )
        assert payload.read_text(encoding="utf-8") == SKILL + "B"


def test_shared_hook_update_restore_preserves_inserted_neighbors_and_settings(tmp_path):
    asset = source_asset(tmp_path, "hook")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        settings = tmp_path / "a/.claude/settings.json"
        neighbor = {"hooks": [{"type": "command", "command": "neighbor"}]}
        document = json.loads(settings.read_text(encoding="utf-8"))
        document["model"] = "preserved"
        document["hooks"]["Stop"].insert(0, neighbor)
        settings.write_text(json.dumps(document), encoding="utf-8")
        Path(asset.source).write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [{"hooks": [{"type": "command", "command": "echo B"}]}]
                    }
                }
            ),
            encoding="utf-8",
        )
        result = current.update_asset(asset)
        assert result.ok, result.diagnostics
        assert current.restore_all(
            result.operation_id, AssetSelector("claude", kind="hook"), force=True
        ).ok
        actual = json.loads(settings.read_text(encoding="utf-8"))
        assert actual["model"] == "preserved"
        assert actual["hooks"]["Stop"] == [neighbor, HOOK["hooks"]["Stop"][0]]


def test_force_cannot_choose_duplicate_hook_or_bundle(tmp_path):
    asset = source_asset(tmp_path, "hook")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        settings = tmp_path / "a/.claude/settings.json"
        settings.write_text(
            json.dumps({"hooks": {"Stop": HOOK["hooks"]["Stop"] * 2}}), encoding="utf-8"
        )
        before = settings.read_bytes()
        assert not current.update_asset(asset, force=True).ok
        assert not current.update_asset(replace(asset, kind="plugin"), force=True).ok
        assert settings.read_bytes() == before


def test_project_update_preserves_shared_user_assets_and_plugin_bodies(tmp_path):
    from tests.pub.assets.test_context import native_assets

    from zuat.pub import PluginRecord, PluginRef

    native_assets(tmp_path / "home")
    bundle = tmp_path / "plugin/bundle"
    bundle.mkdir(parents=True)
    secret = b"PLUGIN-SOURCE-MUST-NOT-ENTER-THE-JOURNAL"
    (bundle / "runtime.ts").write_bytes(secret)
    record = PluginRecord(
        PluginRef("claude", "bundle@market"),
        "bundle",
        True,
        "active",
        "1.0.0",
        runtime_root=bundle,
    )

    class Inventory:
        def discover(self):
            return (record,)

        def contributions(self, value):
            return ()

    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a", Inventory()) as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        updated = current.update_asset(asset)
        assert updated.ok
        assert current.restore_all(
            updated.operation_id,
            AssetSelector("claude", kind="skill", scope="project"),
            force=True,
        ).ok
        assert current.uninstall_all(
            AssetSelector("claude", kind="skill", scope="project")
        ).ok
        assert (tmp_path / "home/.claude/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL
        assert (
            json.loads(
                (tmp_path / "home/.claude/settings.json").read_text(encoding="utf-8")
            )
            == HOOK
        )
        assert (bundle / "runtime.ts").read_bytes() == secret
        for commit in current.registry.repo.iter_commits():
            for entry in commit.tree.traverse():
                if entry.type == "blob":
                    assert secret not in entry.data_stream.read()


def test_restore_clears_pending_when_native_before_state_already_matches(
    tmp_path, monkeypatch
):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        resolver = current._resolver("claude")

        def fail(*args):
            raise OSError("injected before native mutation")

        with monkeypatch.context() as patch:
            patch.setattr(resolver, "replace_asset", fail)
            patch.setattr(resolver, "materialize", fail)
            result = current.update_asset(asset)
        assert current.registry.recovery_marker.exists()
        restored = current.restore_all(
            result.operation_id, AssetSelector("claude", kind="skill"), force=True
        )
        assert restored.ok, restored.diagnostics
        assert not current.registry.recovery_marker.exists()


def test_restore_verifies_receipt_even_when_native_and_profile_already_match(tmp_path):
    from zuat.specs.native import Scope

    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        updated = current.update_asset(asset)
        selector = AssetSelector("claude", kind="skill")
        assert current.restore_all(updated.operation_id, selector, force=True).ok
        support = current._resolver("claude")._support
        support.ordinary_store(
            support.bind(current.registry.root), Scope.PROJECT
        ).remove("skill", "reviewer", "project")
        assert current.inspect_asset(asset).classification == "unowned"
        assert current.restore_all(updated.operation_id, selector, force=True).ok
        assert current.inspect_asset(asset).classification == "outdated"


def test_restoration_itself_retains_recoverable_profile_authority(tmp_path):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        Path(asset.source, "SKILL.md").write_text(SKILL + "B", encoding="utf-8")
        updated = current.update_asset(asset)
        selector = AssetSelector("claude", kind="skill", scope="project")
        restored = current.restore_all(updated.operation_id, selector, force=True)
        assert restored.ok
        replayed = current.restore_all(restored.operation_id, selector, force=True)
        assert replayed.ok, replayed.diagnostics
        assert current.inspect_asset(asset).classification == "current"
        assert (
            current.list_assets(selector).assets[0].authority.value == "authoritative"
        )


def test_update_accepts_a_valid_single_document_skill_source(tmp_path):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        document = Path(asset.source, "SKILL.md")
        document.write_text(SKILL + "B", encoding="utf-8")
        file_asset = replace(asset, source=str(document))
        assert current.inspect_asset(file_asset).classification == "outdated"
        updated = current.update_asset(file_asset)
        assert updated.ok, updated.diagnostics
        assert (tmp_path / "a/.claude/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL + "B"


def test_compound_owned_hook_source_is_one_recoverable_asset(tmp_path):
    asset = source_asset(tmp_path, "hook")
    fragment = {
        "Stop": [{"command": "first"}, {"command": "second"}],
        "Start": [{"command": "start"}],
    }
    Path(asset.source).write_text(json.dumps({"hooks": fragment}), encoding="utf-8")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        assert current.inspect_asset(asset).classification == "current"
        settings = tmp_path / "a/.claude/settings.json"
        native = json.loads(settings.read_text(encoding="utf-8"))
        neighbor = {"command": "neighbor"}
        native["hooks"]["Stop"].insert(0, neighbor)
        settings.write_text(json.dumps(native), encoding="utf-8")
        fragment["Stop"][1]["command"] = "new second"
        Path(asset.source).write_text(json.dumps({"hooks": fragment}), encoding="utf-8")
        assert current.inspect_asset(asset).classification == "outdated"
        updated = current.update_asset(asset)
        assert updated.ok, updated.diagnostics
        selector = AssetSelector(
            "claude", kind="hook", scope="project", name="reviewer"
        )
        restored = current.restore_all(updated.operation_id, selector, force=True)
        assert restored.ok, restored.diagnostics
        assert current.inspect_asset(asset).classification == "outdated"
        assert current.uninstall_all(selector).ok
        assert json.loads(settings.read_text(encoding="utf-8"))["hooks"]["Stop"] == [
            neighbor
        ]
