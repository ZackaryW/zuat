import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from tests.pub.assets.test_context import HOOK, SKILL, service

from zuat.pub import AssetInput, ZuatRequest


def source_asset(tmp_path, kind="skill", scope="project"):
    source = tmp_path / (
        "package/reviewer" if kind == "skill" else "package/reviewer.json"
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    if kind == "skill":
        source.mkdir(exist_ok=True)
        (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    else:
        source.write_text(json.dumps(HOOK), encoding="utf-8")
    return AssetInput("claude", kind, scope=scope, source=str(source))


def test_public_inspection_distinguishes_ownership_baseline_and_source_without_writes(
    tmp_path,
):
    asset = source_asset(tmp_path)
    project = tmp_path / "project"
    with service(tmp_path, project) as current:
        history = current.registry.history()
        assert current.inspect_asset(asset).classification == "absent"
        native = project / ".claude/skills/reviewer/SKILL.md"
        native.parent.mkdir(parents=True)
        native.write_text(SKILL, encoding="utf-8")
        unowned = current.inspect_asset(asset)
        assert unowned.classification == "unowned" and unowned.source_matches
        assert not unowned.owned and unowned.baseline_fingerprint is None
        assert current.registry.history() == history
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        original = current.inspect_asset(asset)
        assert original.classification == "current" and original.owned
        with pytest.raises(FrozenInstanceError):
            original.classification = "absent"
        package = tmp_path / "package/reviewer/SKILL.md"
        package.write_text(SKILL + "B", encoding="utf-8")
        assert current.inspect_asset(asset).classification == "outdated"
        native.write_text(SKILL + "B", encoding="utf-8")
        conflict = current.inspect_asset(asset)
        assert conflict.classification == "conflict" and conflict.source_matches
        assert conflict.observed_fingerprint != conflict.baseline_fingerprint
        assert (
            current.inspect_asset(replace(asset, name="wrong")).classification
            == "indeterminate"
        )
        assert (
            current.inspect_asset(replace(asset, scope="managed")).classification
            == "unsupported"
        )


@pytest.mark.parametrize("kind", ["skill", "hook"])
def test_owned_inspection_works_without_plugin_inventory_but_unknown_is_indeterminate(
    tmp_path, kind
):
    asset = source_asset(tmp_path, kind)
    with service(tmp_path, tmp_path / "project") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok

        def unavailable():
            raise OSError("offline")

        current._resolver("claude")._support._plugin_adapter.discover = unavailable
        history = current.registry.history()
        assert current.inspect_asset(asset).classification == "current"
        assert (
            current.inspect_asset(replace(asset, scope="user")).classification
            == "indeterminate"
        )
        assert current.registry.history() == history


def test_shared_hook_receipt_identity_survives_insertions_but_rejects_ambiguity(
    tmp_path,
):
    asset = source_asset(tmp_path, "hook")
    project = tmp_path / "project"
    with service(tmp_path, project) as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        settings = project / ".claude/settings.json"
        document = json.loads(settings.read_text(encoding="utf-8"))
        document["hooks"]["Stop"].insert(
            0, {"hooks": [{"type": "command", "command": "neighbor"}]}
        )
        settings.write_text(json.dumps(document), encoding="utf-8")
        assert current.inspect_asset(asset).classification == "current"
        document["hooks"]["Stop"].append(HOOK["hooks"]["Stop"][0])
        settings.write_text(json.dumps(document), encoding="utf-8")
        assert current.inspect_asset(asset).classification == "indeterminate"


@pytest.mark.parametrize("agent", ["codex", "claude", "kimi", "pi"])
@pytest.mark.parametrize("kind", ["skill", "hook"])
@pytest.mark.parametrize("scope", ["user", "project"])
def test_native_scope_matrix_and_malformed_source(tmp_path, agent, kind, scope):
    from tests.pub.assets.test_context import EmptyPlugins

    from zuat.pub import Zuat
    from zuat.specs.registry import resolver_for

    source = source_asset(tmp_path, kind, scope)
    path = Path(source.source)
    if kind == "hook" and agent in {"kimi", "pi"}:
        path = path.with_suffix(".toml" if agent == "kimi" else ".ts")
        path.write_text(
            '[[hooks]]\nevent = "Stop"\ncommand = "echo A"\n'
            if agent == "kimi"
            else "export default function (pi) {}\n",
            encoding="utf-8",
        )
    asset = replace(source, agent=agent, source=str(path))
    home, project, root = tmp_path / "home", tmp_path / "project", tmp_path / "registry"
    resolver = resolver_for(
        agent,
        home=home,
        project_root=project,
        state_root=root / ".git/zuat/native",
        plugins=EmptyPlugins(),
    )
    with Zuat(
        root=root, home=home, project_root=project, resolvers={agent: resolver}
    ) as current:
        expected = (
            "unsupported"
            if agent == "kimi" and kind == "hook" and scope == "project"
            else "absent"
        )
        assert current.inspect_asset(asset).classification == expected
        if expected == "unsupported":
            return
        assert current.install(ZuatRequest(agents=(agent,), assets=(asset,))).ok
        assert current.inspect_asset(asset).classification == "current"
        assert (
            current.inspect_asset(replace(asset, asset_ref="missing")).classification
            == "indeterminate"
        )
        ref = (
            current.install(ZuatRequest(agents=(agent,), assets=(asset,))).assets[0].ref
        )
        assert (
            current.inspect_asset(replace(asset, asset_ref=ref.id)).classification
            == "current"
        )
        if kind == "skill":
            (path / "SKILL.md").write_text("invalid", encoding="utf-8")
            assert current.inspect_asset(asset).classification == "indeterminate"


def test_malformed_receipt_cannot_authorize_forced_replacement(tmp_path):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        support = current._resolver("claude")._support
        from zuat.specs.native import Scope

        store = support.ordinary_store(
            support.bind(current.registry.root), Scope.PROJECT
        )
        receipt = store._path("skill", "reviewer", "project")
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["fingerprint"] = "invalid"
        receipt.write_text(json.dumps(data), encoding="utf-8")
        native = tmp_path / "a/.claude/skills/reviewer/SKILL.md"
        before = native.read_bytes()
        assert current.inspect_asset(asset).classification == "indeterminate"
        assert not current.update_asset(asset, force=True).ok
        assert native.read_bytes() == before


def test_malformed_native_kimi_hook_reports_indeterminate(tmp_path):
    from zuat.pub import Zuat

    source = tmp_path / "guard.toml"
    source.write_text(
        '[[hooks]]\nevent = "Stop"\ncommand = "echo ok"\n', encoding="utf-8"
    )
    native = tmp_path / "home/.kimi-code/config.toml"
    native.parent.mkdir(parents=True)
    native.write_text('hooks = ["malformed"]\n', encoding="utf-8")
    with Zuat(root=tmp_path / "registry", home=tmp_path / "home") as current:
        result = current.inspect_asset(AssetInput("kimi", "hook", source=str(source)))
        assert result.classification == "indeterminate"


@pytest.mark.parametrize("field,value", [("destination", None), ("native_locator", 42)])
def test_invalid_receipt_field_is_non_authorizing(tmp_path, field, value):
    asset = source_asset(tmp_path, "hook")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.install(ZuatRequest(agents=("claude",), assets=(asset,))).ok
        from zuat.specs.native import Scope

        support = current._resolver("claude")._support
        receipt = support.ordinary_store(
            support.bind(current.registry.root), Scope.PROJECT
        )._path("hook", "reviewer", "project")
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data[field] = value
        receipt.write_text(json.dumps(data), encoding="utf-8")
        assert current.inspect_asset(asset).classification == "indeterminate"


def test_explicit_locator_cannot_override_a_different_asset_reference(tmp_path):
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as current:
        installed = current.install(ZuatRequest(agents=("claude",), assets=(asset,)))
        assert installed.ok
        ref = installed.assets[0].ref
        other = current.registry.ensure_asset_ref(
            agent="claude",
            kind="skill",
            scope="project",
            locator=ref.locator.removesuffix("reviewer") + "other",
        )
        conflicting = replace(asset, asset_ref=other.id, locator=ref.locator)
        assert current.inspect_asset(conflicting).classification == "indeterminate"
        assert not current.update_asset(conflicting, force=True).ok
