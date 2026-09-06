import json
from pathlib import Path

from zuat.gitcore import AssetEvidence, Authority, GitRegistry, OperationKind
from zuat.pub import AssetInput, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for


SKILL = """---
name: reviewer
description: Review changes
---
Review the current change.
"""


class EmptyPlugins:
    def discover(self):
        return ()


def _write_claude_native_state(home: Path) -> None:
    skill = home / ".claude" / "skills" / "reviewer"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL, encoding="utf-8")
    settings = home / ".claude" / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "model": "unrelated",
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {"type": "command", "command": "prepare-workspace"}
                            ]
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def test_fresh_registry_projects_observations_as_a_concrete_tree(
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry"
    home = tmp_path / "home"
    _write_claude_native_state(home)

    with GitRegistry(root) as registry:
        result = Zuat(registry=registry, home=home).status(
            ZuatRequest(agents=("claude",))
        )

        assert result.ok
        assert (root / "claude/user/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL
        hook_paths = tuple((root / "claude/user/hooks").rglob("*.json"))
        assert hook_paths
        assert "prepare-workspace" in hook_paths[0].read_text(encoding="utf-8")
        assert all(
            (root / agent).is_dir() for agent in ("claude", "codex", "kimi", "pi")
        )
        assert (root / "selected-profile").read_text(encoding="utf-8") == "default\n"

        catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        assert {item["id"] for item in catalog.values()} == {
            asset.ref.id for asset in result.assets
        }
        operation_files = tuple((root / "operations").glob("*.json"))
        assert len(operation_files) == 1
        assert operation_files[0].name.startswith("000000000001-op_")
        operation = json.loads(operation_files[0].read_text(encoding="utf-8"))
        assert operation["kind"] == OperationKind.OBSERVE.value

        assert not (root / "observations").exists()
        assert not (root / "events").exists()
        assert not (root / "state.json").exists()


def test_profile_membership_recovers_from_concrete_asset_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry"
    home = tmp_path / "home"
    source = tmp_path / "source" / "reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")

    with GitRegistry(root) as registry:
        resolver = resolver_for(
            "claude",
            home=home,
            state_root=registry.control_root / "native",
            plugins=EmptyPlugins(),
        )
        installed = Zuat(registry=registry, resolvers={"claude": resolver}).install(
            ZuatRequest(
                agents=("claude",),
                assets=(
                    AssetInput(
                        agent="claude",
                        kind="skill",
                        name="reviewer",
                        locator="skills/reviewer",
                        source=str(source),
                    ),
                ),
            )
        )
        assert installed.ok
        asset_id = installed.assets[0].ref.id

        payload = root / "profiles/default/claude/user/skills/reviewer"
        metadata_path = payload.with_name("reviewer.zuat.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["asset_ref"] == asset_id
        assert metadata["normalized_path"] == "claude/user/skills/reviewer"
        profile_marker = json.loads(
            (root / "profiles/default/.profile.json").read_text(encoding="utf-8")
        )
        assert profile_marker == {"name": "default"}

        catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        catalog_entry = next(
            value for value in catalog.values() if value["id"] == asset_id
        )
        assert catalog_entry["normalized_path"] == "claude/user/skills/reviewer"
        assert not (root / "objects").exists()
        assert registry.asset_payload(
            installed.assets[0].ref, installed.assets[0].fingerprint
        ).exists()

    with GitRegistry(root) as reopened:
        assert reopened.projected_state().profile("default").assets == (asset_id,)
        assert (
            reopened.profile_root()
            / "claude/user/skills/reviewer/SKILL.md"
        ).read_text(encoding="utf-8") == SKILL


def test_operation_stream_preserves_other_agent_observations_after_restart(
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        codex_ref = registry.ensure_asset_ref(
            agent="codex",
            kind="skill",
            scope="user",
            locator="skills/reviewer",
        )
        claude_ref = registry.ensure_asset_ref(
            agent="claude",
            kind="hook",
            scope="user",
            locator="settings/hooks/SessionStart/0",
        )
        codex = AssetEvidence(
            codex_ref, "sha256:codex", Authority.UNAUTHORITATIVE
        )
        claude = AssetEvidence(
            claude_ref, "sha256:claude", Authority.UNAUTHORITATIVE
        )
        registry.record_observation((codex,), agents=("codex",))
        claude_event = registry.record_observation((claude,), agents=("claude",))
        assert claude_event is not None

    with GitRegistry(root) as reopened:
        assert reopened.latest_observation() == tuple(
            sorted((codex, claude), key=lambda item: item.ref.id)
        )
        assert reopened.event(claude_event.operation_id) == claude_event
        assert reopened.record_observation(
            (claude,), agents=("claude",)
        ) is None


def test_claude_lifecycle_keeps_concrete_observation_and_history_current(
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry"
    home = tmp_path / "home"
    source = tmp_path / "source" / "reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")

    with GitRegistry(root) as registry:
        resolver = resolver_for(
            "claude",
            home=home,
            state_root=registry.control_root / "native",
            plugins=EmptyPlugins(),
        )
        service = Zuat(registry=registry, resolvers={"claude": resolver})
        installed = service.install(
            ZuatRequest(
                agents=("claude",),
                assets=(
                    AssetInput(
                        agent="claude",
                        kind="skill",
                        name="reviewer",
                        locator="skills/reviewer",
                        source=str(source),
                    ),
                ),
            )
        )
        assert installed.ok
        observed = root / "claude/user/skills/reviewer/SKILL.md"
        assert observed.read_text(encoding="utf-8") == SKILL

        removed = service.uninstall(
            ZuatRequest(
                agents=("claude",), asset_refs=(installed.assets[0].ref.id,)
            )
        )
        assert removed.ok
        assert not observed.exists()
        assert registry.projected_state().profile("default").assets == ()
        lifecycle = tuple(
            event
            for event in registry.history()
            if event.kind in {OperationKind.INSTALL, OperationKind.UNINSTALL}
        )
        assert tuple(event.operation_id for event in lifecycle) == (
            installed.operation_id,
            removed.operation_id,
        )
        assert lifecycle[0].sequence < lifecycle[1].sequence
