from pathlib import Path

from zuat.gitcore import GitRegistry, OperationKind, OperationOutcome
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


def install_new(service: Zuat, source: Path):
    return service.install(
        ZuatRequest(
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
    )


def test_uninstall_removes_authoritative_native_and_profile_content(
    tmp_path: Path,
) -> None:
    service, registry, home = codex_service(tmp_path)
    source = tmp_path / "source/reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    try:
        installed = install_new(service, source)
        ref = installed.assets[0].ref
        fingerprint = installed.assets[0].fingerprint

        result = service.uninstall(
            ZuatRequest(agents=("codex",), asset_refs=(ref.id,))
        )

        assert result.status is OperationStatus.SUCCESS
        assert not (home / ".codex/skills/reviewer").exists()
        assert not (registry.profile_root() / "codex/user/skills/reviewer").exists()
        assert registry.projected_state().profile("default").assets == ()
        assert registry.asset_payload(ref, fingerprint).exists()
        assert registry.history()[-1].kind is OperationKind.UNINSTALL
    finally:
        registry.close()


def test_uninstall_unauthoritative_content_requires_force(tmp_path: Path) -> None:
    service, registry, home = codex_service(tmp_path)
    native = home / ".codex/skills/reviewer/SKILL.md"
    native.parent.mkdir(parents=True)
    native.write_text(SKILL, encoding="utf-8")
    try:
        ref = service.status(ZuatRequest(agents=("codex",))).assets[0].ref

        rejected = service.uninstall(
            ZuatRequest(agents=("codex",), asset_refs=(ref.id,))
        )
        assert rejected.status is OperationStatus.FAILED
        assert native.exists()
        assert registry.history()[-1].outcome is OperationOutcome.REJECTED

        forced = service.uninstall(
            ZuatRequest(agents=("codex",), asset_refs=(ref.id,), force=True)
        )
        assert forced.status is OperationStatus.SUCCESS
        assert not native.exists()
        assert registry.history()[-1].forced is True
        assert registry.history()[-1].outcome is OperationOutcome.SUCCESS
    finally:
        registry.close()
