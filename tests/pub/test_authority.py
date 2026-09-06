from pathlib import Path

from zuat.gitcore import Authority, GitRegistry
from zuat.pub import OperationStatus, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for


SKILL = "---\nname: reviewer\ndescription: Review changes\n---\nReview.\n"


class EmptyPlugins:
    def discover(self):
        return ()


def test_missing_ownership_does_not_hide_asset_and_authority_tracks_profile(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    native = home / ".codex/skills/reviewer/SKILL.md"
    native.parent.mkdir(parents=True)
    native.write_text(SKILL, encoding="utf-8")
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "codex",
        home=home,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    service = Zuat(registry=registry, resolvers={"codex": resolver})
    try:
        first = service.status(ZuatRequest(agents=("codex",)))
        observed = first.assets[0]
        assert observed.authority is Authority.UNAUTHORITATIVE

        source = registry.observation_root / "codex/user/skills/reviewer"
        desired = registry.profile_root() / "codex/user/skills/reviewer"
        desired.parent.mkdir(parents=True)
        desired.mkdir()
        (desired / "SKILL.md").write_bytes((source / "SKILL.md").read_bytes())
        registry.set_profile_assets("default", (observed.ref.id,))

        authoritative = service.status(ZuatRequest(agents=("codex",)))
        assert authoritative.assets[0].ref == observed.ref
        assert authoritative.assets[0].authority is Authority.AUTHORITATIVE

        native.write_text(SKILL + "User edit.\n", encoding="utf-8")
        conflicting = service.status(ZuatRequest(agents=("codex",)))
        assert conflicting.assets[0].ref == observed.ref
        assert conflicting.assets[0].authority is Authority.CONFLICTING
    finally:
        registry.close()


def test_rejected_native_candidates_make_observation_partial(tmp_path: Path) -> None:
    home = tmp_path / "home"
    invalid = home / ".codex/skills/invalid"
    invalid.mkdir(parents=True)
    (invalid / "README.md").write_text("not a skill", encoding="utf-8")
    registry = GitRegistry(tmp_path / "registry")
    service = Zuat(
        registry=registry,
        resolvers={
            "codex": resolver_for(
                "codex",
                home=home,
                state_root=registry.control_root / "native",
                plugins=EmptyPlugins(),
            )
        },
    )
    try:
        result = service.status(ZuatRequest(agents=("codex",)))
        assert result.status is OperationStatus.PARTIAL
        assert result.completeness == "partial"
        assert result.diagnostics
        assert registry.history()[-1].completeness == "partial"
    finally:
        registry.close()
