from pathlib import Path

from zuat.gitcore import GitRegistry, OperationKind


def test_named_profiles_are_desired_state_projections_not_public_branches(
    tmp_path: Path,
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        default_root = registry.profile_root()
        source = tmp_path / "reviewer"
        source.mkdir()
        (source / "SKILL.md").write_text("review", encoding="utf-8")
        ref = registry.ensure_asset_ref(
            agent="codex",
            kind="skill",
            scope="user",
            locator="skills/reviewer",
        )
        registry.store_profile_asset(
            "default",
            ref,
            "codex/user/skills/reviewer",
            source,
            "sha256:reviewer",
        )

        event = registry.create_profile("work")

        profiles = registry.profiles()
        assert event.kind is OperationKind.PROFILE_CREATE
        assert [profile.to_dict() for profile in profiles] == [
            {
                "name": "default",
                "selected": True,
                "assets": [ref.id],
            },
            {
                "name": "work",
                "selected": False,
                "assets": [ref.id],
            },
        ]
        copied = (
            registry.profile_root("work")
            / "codex/user/skills/reviewer/SKILL.md"
        )
        assert copied.read_text(encoding="utf-8") == "review"
        assert [head.name for head in registry.repo.heads] == ["zuat-journal"]
