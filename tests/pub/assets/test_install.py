from pathlib import Path

from zuat.gitcore import Authority, GitRegistry, OperationKind, OperationOutcome
from zuat.pub import AssetInput, OperationStatus, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for


SKILL = "---\nname: reviewer\ndescription: Review changes\n---\nReview.\n"


class EmptyPlugins:
    def discover(self):
        return ()


def codex_service(tmp_path: Path):
    home = tmp_path / "home"
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "codex",
        home=home,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    return Zuat(registry=registry, resolvers={"codex": resolver}), registry, home


def test_install_adopts_equivalent_unowned_native_content_without_rewrite(
    tmp_path: Path,
) -> None:
    service, registry, home = codex_service(tmp_path)
    native = home / ".codex/skills/reviewer/SKILL.md"
    native.parent.mkdir(parents=True)
    native.write_text(SKILL, encoding="utf-8")
    try:
        observed = service.status(ZuatRequest(agents=("codex",))).assets[0]
        modified_before = native.stat().st_mtime_ns

        result = service.install(
            ZuatRequest(
                agents=("codex",), asset_refs=(observed.ref.id,)
            )
        )

        assert result.status is OperationStatus.SUCCESS
        assert result.assets[0].ref == observed.ref
        assert result.assets[0].authority is Authority.AUTHORITATIVE
        assert native.stat().st_mtime_ns == modified_before
        assert registry.projected_state().profile("default").assets == (
            observed.ref.id,
        )
        event = registry.history()[-1]
        assert event.kind is OperationKind.INSTALL
        assert event.outcome is OperationOutcome.SUCCESS
        assert event.before[0].authority is Authority.UNAUTHORITATIVE
        assert event.after[0].authority is Authority.AUTHORITATIVE
    finally:
        registry.close()


def test_install_new_skill_updates_native_and_selected_profile(tmp_path: Path) -> None:
    service, registry, home = codex_service(tmp_path)
    source = tmp_path / "source/reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    try:
        result = service.install(
            ZuatRequest(
                agents=("codex",),
                assets=(
                    AssetInput(
                        agent="codex",
                        kind="skill",
                        scope="user",
                        name="reviewer",
                        locator="skills/reviewer",
                        source=str(source),
                    ),
                ),
            )
        )

        assert result.status is OperationStatus.SUCCESS
        assert result.assets[0].authority is Authority.AUTHORITATIVE
        assert (home / ".codex/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL
        profile_copy = registry.profile_root() / "codex/user/skills/reviewer/SKILL.md"
        assert profile_copy.read_text(encoding="utf-8") == SKILL
        assert registry.asset_payload(
            result.assets[0].ref, result.assets[0].fingerprint
        ).is_dir()
    finally:
        registry.close()


def test_forced_install_replaces_only_the_conflict_and_is_not_persistent(
    tmp_path: Path,
) -> None:
    service, registry, home = codex_service(tmp_path)
    native = home / ".codex/skills/reviewer/SKILL.md"
    other = home / ".codex/skills/other/SKILL.md"
    native.parent.mkdir(parents=True)
    other.parent.mkdir(parents=True)
    native.write_text(SKILL + "Native version.\n", encoding="utf-8")
    other.write_text(
        "---\nname: other\ndescription: Other\n---\nOther.\n",
        encoding="utf-8",
    )
    source = tmp_path / "source/reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    request = ZuatRequest(
        agents=("codex",),
        assets=(
            AssetInput(
                agent="codex",
                kind="skill",
                name="reviewer",
                locator="skills/reviewer",
                source=str(source),
            ),
        ),
    )
    try:
        rejected = service.install(request)
        assert rejected.status is OperationStatus.FAILED
        assert native.read_text(encoding="utf-8").endswith("Native version.\n")

        forced = service.install(
            ZuatRequest(
                agents=request.agents,
                assets=request.assets,
                force=True,
            )
        )
        assert forced.status is OperationStatus.SUCCESS
        assert native.read_text(encoding="utf-8") == SKILL
        assert other.exists()
        forced_event = registry.history()[-1]
        assert forced_event.forced is True
        assert forced_event.before[0].fingerprint != forced_event.after[0].fingerprint

        native.write_text(SKILL + "Later edit.\n", encoding="utf-8")
        later = service.install(request)
        assert later.status is OperationStatus.FAILED
        assert "Later edit" in native.read_text(encoding="utf-8")
    finally:
        registry.close()
