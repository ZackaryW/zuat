from pathlib import Path

from zuat.gitcore import GitRegistry, OperationKind
from zuat.pub import AssetInput, OperationStatus, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for


SKILL = "---\nname: reviewer\ndescription: Review changes\n---\nReview.\n"


class EmptyPlugins:
    def discover(self):
        return ()


def service(tmp_path: Path):
    home = tmp_path / "home"
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "codex",
        home=home,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    return Zuat(registry=registry, resolvers={"codex": resolver}), registry, home


def install(service: Zuat, source: Path):
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


def test_install_revert_and_revert_of_revert_update_native_state(
    tmp_path: Path,
) -> None:
    zuat, registry, home = service(tmp_path)
    source = tmp_path / "source/reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    native = home / ".codex/skills/reviewer/SKILL.md"
    try:
        installed = install(zuat, source)

        removed = zuat.revert(
            ZuatRequest(
                agents=("codex",), operation_id=installed.operation_id
            )
        )
        assert removed.status is OperationStatus.SUCCESS
        assert not native.exists()
        assert registry.history()[-1].kind is OperationKind.REVERT
        assert registry.history()[-1].reverts == installed.operation_id

        restored = zuat.revert(
            ZuatRequest(
                agents=("codex",), operation_id=removed.operation_id
            )
        )
        assert restored.status is OperationStatus.SUCCESS
        assert native.read_text(encoding="utf-8") == SKILL
        assert registry.history()[-1].reverts == removed.operation_id
    finally:
        registry.close()


def test_uninstall_revert_restores_archived_payload(tmp_path: Path) -> None:
    zuat, registry, home = service(tmp_path)
    source = tmp_path / "source/reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    try:
        installed = install(zuat, source)
        uninstalled = zuat.uninstall(
            ZuatRequest(
                agents=("codex",), asset_refs=(installed.assets[0].ref.id,)
            )
        )

        restored = zuat.revert(
            ZuatRequest(
                agents=("codex",), operation_id=uninstalled.operation_id
            )
        )

        assert restored.status is OperationStatus.SUCCESS
        assert (home / ".codex/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL
        assert registry.projected_state().profile("default").assets == (
            installed.assets[0].ref.id,
        )
    finally:
        registry.close()


def test_profile_switch_revert_and_revert_of_revert_reconcile_native_state(
    tmp_path: Path,
) -> None:
    zuat, registry, home = service(tmp_path)
    source = tmp_path / "source/reviewer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    native = home / ".codex/skills/reviewer/SKILL.md"
    try:
        installed = install(zuat, source)
        evidence = installed.assets[0]
        assert zuat.create_profile(
            ZuatRequest(agents=("codex",), profile="work")
        ).ok
        registry.set_profile_assets("work", ())
        registry.remove_profile_asset(
            "work", evidence.ref, str(evidence.evidence["normalized_path"])
        )

        switched = zuat.switch_profile(
            ZuatRequest(agents=("codex",), profile="work")
        )
        assert switched.ok
        assert not native.exists()

        restored = zuat.revert(
            ZuatRequest(agents=("codex",), operation_id=switched.operation_id)
        )
        assert restored.ok
        assert registry.projected_state().selected_profile == "default"
        assert native.read_text(encoding="utf-8") == SKILL

        removed_again = zuat.revert(
            ZuatRequest(agents=("codex",), operation_id=restored.operation_id)
        )
        assert removed_again.ok
        assert registry.projected_state().selected_profile == "work"
        assert not native.exists()
    finally:
        registry.close()
