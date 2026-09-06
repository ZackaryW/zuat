import json

from tests.pub.assets.test_context import SKILL, native_assets, service

from zuat.pub import AssetInput, AssetSelector, ZuatRequest


def test_adopt_both_projects_and_inspect_receipt_bound_hook_reference(tmp_path):
    for root in (tmp_path / "a", tmp_path / "b", tmp_path / "home"):
        native_assets(root)
    refs = []
    for project in (tmp_path / "a", tmp_path / "b"):
        with service(tmp_path, project) as current:
            adopted = current.adopt_all(AssetSelector("claude", scope="project"))
            assert adopted.ok, adopted.diagnostics
            hook = next(item for item in adopted.assets if item.ref.kind == "hook")
            refs.append(hook.ref.id)
            source = tmp_path / (str(hook.evidence["asset_name"]) + ".json")
            source.write_bytes(
                (
                    current.registry.observation_root / hook.evidence["normalized_path"]
                ).read_bytes()
            )
            result = current.inspect_asset(
                AssetInput(
                    "claude",
                    "hook",
                    scope="project",
                    source=str(source),
                    asset_ref=hook.ref.id,
                )
            )
            assert result.classification == "current", result.diagnostics
            settings = project / ".claude/settings.json"
            document = json.loads(settings.read_text(encoding="utf-8"))
            neighbor = {"hooks": [{"type": "command", "command": "neighbor"}]}
            document["hooks"]["Stop"].insert(0, neighbor)
            settings.write_text(json.dumps(document), encoding="utf-8")
            source.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "Stop": [
                                {"hooks": [{"type": "command", "command": "updated"}]}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            updated = current.update_asset(
                AssetInput(
                    "claude",
                    "hook",
                    scope="project",
                    source=str(source),
                    asset_ref=hook.ref.id,
                )
            )
            assert updated.ok, updated.diagnostics
            restored = current.restore_all(
                updated.operation_id, AssetSelector("claude", kind="hook"), force=True
            )
            assert restored.ok, restored.diagnostics
            assert (
                json.loads(settings.read_text(encoding="utf-8"))["hooks"]["Stop"][0]
                == neighbor
            )
    assert refs[0] != refs[1]


def test_incomplete_other_project_observation_preserves_all_prior_receipts(tmp_path):
    native_assets(tmp_path / "a")
    with service(tmp_path, tmp_path / "a") as current:
        assert current.adopt_all(AssetSelector("claude", scope="project")).ok
        prior = {item.ref.id: item for item in current.registry.latest_observation()}
    with service(tmp_path, tmp_path / "b") as other:

        def offline():
            raise OSError("offline")

        other._resolver("claude")._support._plugin_adapter.discover = offline
        result = other.status(ZuatRequest(agents=("claude",)))
        assert result.completeness == "partial"
        retained = {item.ref.id: item for item in other.registry.latest_observation()}
        assert all(
            retained[asset_id] == evidence for asset_id, evidence in prior.items()
        )


def test_project_operation_without_context_does_not_write_native(tmp_path):
    source = tmp_path / "reviewer"
    source.mkdir()
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    with service(tmp_path, None) as current:
        result = current.install(
            ZuatRequest(
                agents=("claude",),
                assets=(
                    AssetInput("claude", "skill", scope="project", source=str(source)),
                ),
            )
        )
        assert not result.ok
        assert not (tmp_path / "home/.claude/skills/reviewer").exists()


def test_profile_storage_rejects_foreign_context_path(tmp_path):
    import pytest

    from zuat.gitcore import RegistryError
    from zuat.utils.contexts import project_context

    with service(tmp_path, tmp_path / "a") as current:
        ref = current.registry.ensure_asset_ref(
            agent="claude",
            kind="skill",
            scope="project",
            locator=f"contexts/{project_context(tmp_path / 'a')}/skills/reviewer",
        )
        source = tmp_path / "source"
        source.mkdir()
        (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
        with pytest.raises(RegistryError):
            current.registry.store_profile_asset(
                "default",
                ref,
                f"claude/project/contexts/{project_context(tmp_path / 'b')[:16]}/skills/reviewer",
                source,
                "sha256:invalid",
            )


def test_targeted_sidecar_does_not_bypass_profile_force_policy(tmp_path):
    from tests.pub.assets.test_context import install_skill

    with service(tmp_path, tmp_path / "a") as current:
        installed = install_skill(current, tmp_path)
        payload = (
            current.registry.profile_root()
            / installed.assets[0].evidence["normalized_path"]
        )
        metadata = payload.with_name(payload.name + ".zuat.json")
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data["targeted"] = True
        metadata.write_text(json.dumps(data), encoding="utf-8")
        native = tmp_path / "a/.claude/skills/reviewer/SKILL.md"
        native.write_text(SKILL + "LOCAL", encoding="utf-8")
        result = current.switch_profile(
            ZuatRequest(agents=("claude",), profile="default")
        )
        assert not result.ok
        assert native.read_text(encoding="utf-8") == SKILL + "LOCAL"
