import json
from pathlib import Path

from zuat.gitcore import (
    Authority,
    GitRegistry,
    OperationKind,
    OperationOutcome,
    RegistryLockedError,
)
from zuat.pub import AssetSelector, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for


SKILL = "---\nname: {name}\ndescription: Test skill\n---\nRun.\n"


class EmptyPlugins:
    def discover(self):
        return ()


def write_skill(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(SKILL.format(name=name), encoding="utf-8")


def codex_service(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "codex",
        home=home,
        project_root=project,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    return (
        Zuat(registry=registry, resolvers={"codex": resolver}),
        registry,
        home,
        project,
    )


def test_list_assets_filters_observed_evidence_and_is_deterministic(
    tmp_path: Path,
) -> None:
    service, registry, home, project = codex_service(tmp_path)
    write_skill(home / ".codex/skills/user-one", "user-one")
    write_skill(home / ".codex/skills/user-two", "user-two")
    write_skill(project / ".agents/skills/project-one", "project-one")
    try:
        observed = service.status(ZuatRequest(agents=("codex",))).assets
        user_one = next(
            item for item in observed if item.evidence.get("asset_name") == "user-one"
        )
        assert service.install(
            ZuatRequest(agents=("codex",), asset_refs=(user_one.ref.id,))
        ).ok

        selector = AssetSelector(
            agent="codex",
            kind="skill",
            scope="user",
            authority=Authority.UNAUTHORITATIVE,
            present=True,
        )
        first = service.list_assets(selector)
        second = service.list_assets(selector)

        assert [item.evidence["asset_name"] for item in first.assets] == ["user-two"]
        assert first.assets == second.assets
        assert first.operation == "asset-list"
        assert first.ok
    finally:
        registry.close()


def test_list_assets_can_select_missing_authoritative_evidence(tmp_path: Path) -> None:
    service, registry, home, _ = codex_service(tmp_path)
    write_skill(home / ".codex/skills/reviewer", "reviewer")
    try:
        observed = service.status(ZuatRequest(agents=("codex",))).assets[0]
        assert service.install(
            ZuatRequest(agents=("codex",), asset_refs=(observed.ref.id,))
        ).ok
        native = home / ".codex/skills/reviewer"
        (native / "SKILL.md").unlink()
        native.rmdir()

        result = service.list_assets(
            AssetSelector(
                agent="codex",
                kind="skill",
                authority=Authority.CONFLICTING,
                present=False,
            )
        )

        assert result.ok
        assert len(result.assets) == 1
        assert result.assets[0].ref == observed.ref
        assert result.assets[0].present is False
    finally:
        registry.close()


def test_adopt_all_makes_every_selected_asset_authoritative(tmp_path: Path) -> None:
    service, registry, home, project = codex_service(tmp_path)
    write_skill(home / ".codex/skills/user-one", "user-one")
    write_skill(home / ".codex/skills/user-two", "user-two")
    write_skill(project / ".agents/skills/project-one", "project-one")
    try:
        result = service.adopt_all(
            AssetSelector(agent="codex", kind="skill", scope="user")
        )

        assert result.ok
        assert result.operation == "adopt-all"
        assert len(result.assets) == 2
        assert all(item.authority is Authority.AUTHORITATIVE for item in result.assets)
        selected = registry.projected_state().profile("default").assets
        assert selected == tuple(sorted(item.ref.id for item in result.assets))
    finally:
        registry.close()


def test_bulk_selection_remains_locked_until_primitive_mutation_begins(
    tmp_path: Path,
) -> None:
    base, registry, home, _ = codex_service(tmp_path)
    rival = GitRegistry(registry.root)

    class ProbedZuat(Zuat):
        rival_was_blocked = False

        def install(self, request):
            try:
                with rival.operation():
                    pass
            except RegistryLockedError:
                self.rival_was_blocked = True
            return super().install(request)

    service = ProbedZuat(registry=registry, resolvers=base._resolvers)
    write_skill(home / ".codex/skills/reviewer", "reviewer")
    try:
        result = service.adopt_all(
            AssetSelector(agent="codex", kind="skill")
        )

        assert result.ok
        assert service.rival_was_blocked is True
    finally:
        rival.close()
        registry.close()


def test_empty_bulk_selection_is_a_successful_non_mutating_noop(
    tmp_path: Path,
) -> None:
    service, registry, _, _ = codex_service(tmp_path)
    try:
        before = len(registry.history())

        result = service.adopt_all(
            AssetSelector(agent="codex", kind="plugin", present=True)
        )

        assert result.ok
        assert result.operation == "adopt-all"
        assert result.operation_id is None
        assert result.assets == ()
        assert not [
            event
            for event in registry.history()[before:]
            if event.kind.value in {"install", "uninstall", "restore"}
        ]
    finally:
        registry.close()


def test_uninstall_all_orders_shared_hook_removals_and_preserves_neighbors(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "model": "unrelated",
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": command}]}
                        for command in ("one", "two", "three")
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "claude",
        home=home,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    service = Zuat(registry=registry, resolvers={"claude": resolver})
    try:
        hooks = service.status(ZuatRequest(agents=("claude",))).assets
        third = next(item for item in hooks if item.ref.locator.endswith("/2"))
        assert service.install(
            ZuatRequest(
                agents=("claude",),
                asset_refs=(third.ref.id,),
            )
        ).ok

        result = service.uninstall_all(
            AssetSelector(
                agent="claude",
                kind="hook",
                authority=Authority.UNAUTHORITATIVE,
            ),
            force=True,
        )

        assert result.ok
        assert result.operation == "uninstall-all"
        document = json.loads(settings.read_text(encoding="utf-8"))
        assert document["model"] == "unrelated"
        assert [
            item["hooks"][0]["command"]
            for item in document["hooks"]["SessionStart"]
        ] == ["three"]
        mutations = [
            event
            for event in registry.history()
            if event.kind.value in {"install", "uninstall"}
        ]
        assert [event.kind.value for event in mutations] == ["install", "uninstall"]
    finally:
        registry.close()


def test_restore_all_recovers_successful_uninstall_without_removing_unrelated(
    tmp_path: Path,
) -> None:
    service, registry, home, _ = codex_service(tmp_path)
    write_skill(home / ".codex/skills/reviewer", "reviewer")
    try:
        observed = service.status(ZuatRequest(agents=("codex",))).assets[0]
        removed = service.uninstall(
            ZuatRequest(
                agents=("codex",),
                asset_refs=(observed.ref.id,),
                force=True,
            )
        )
        write_skill(home / ".codex/skills/unrelated", "unrelated")

        result = service.restore_all(
            removed.operation_id,
            AssetSelector(agent="codex", kind="skill"),
        )

        assert result.ok
        assert result.operation == "restore-all"
        assert (home / ".codex/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL.format(name="reviewer")
        assert (home / ".codex/skills/unrelated/SKILL.md").exists()
        restored = service.list_assets(
            AssetSelector(agent="codex", kind="skill", scope="user")
        ).assets
        reviewer = next(
            item for item in restored if item.evidence.get("asset_name") == "reviewer"
        )
        assert reviewer.authority is Authority.UNAUTHORITATIVE
        event = registry.event(result.operation_id)
        assert event.kind.value == "restore"
        assert event.metadata["restores"] == removed.operation_id
    finally:
        registry.close()


def test_restore_all_recovers_partial_operation_and_authority(tmp_path: Path) -> None:
    service, registry, home, _ = codex_service(tmp_path)
    write_skill(home / ".codex/skills/reviewer", "reviewer")
    try:
        observed = service.status(ZuatRequest(agents=("codex",))).assets[0]
        assert service.install(
            ZuatRequest(agents=("codex",), asset_refs=(observed.ref.id,))
        ).ok
        authoritative = service.status(ZuatRequest(agents=("codex",))).assets[0]
        normalized = str(authoritative.evidence["normalized_path"])
        registry.archive_asset(
            authoritative.ref,
            normalized,
            registry.observation_root / normalized,
            str(authoritative.fingerprint),
        )
        native = home / ".codex/skills/reviewer"
        (native / "SKILL.md").unlink()
        native.rmdir()
        partial = registry.append_event(
            OperationKind.UNINSTALL,
            OperationOutcome.PARTIAL,
            profile="default",
            before=(authoritative,),
            diagnostics=("simulated interruption",),
        )

        result = service.restore_all(
            partial.operation_id,
            AssetSelector(agent="codex", kind="skill"),
        )

        assert result.ok
        current = service.list_assets(
            AssetSelector(agent="codex", kind="skill")
        ).assets[0]
        assert current.fingerprint == authoritative.fingerprint
        assert current.authority is Authority.AUTHORITATIVE
    finally:
        registry.close()


def test_restore_all_rejects_conflict_then_force_archives_displaced_content(
    tmp_path: Path,
) -> None:
    service, registry, home, _ = codex_service(tmp_path)
    write_skill(home / ".codex/skills/reviewer", "reviewer")
    native = home / ".codex/skills/reviewer/SKILL.md"
    try:
        original = service.status(ZuatRequest(agents=("codex",))).assets[0]
        normalized = str(original.evidence["normalized_path"])
        registry.archive_asset(
            original.ref,
            normalized,
            registry.observation_root / normalized,
            str(original.fingerprint),
        )
        source = registry.append_event(
            OperationKind.UNINSTALL,
            OperationOutcome.PARTIAL,
            profile="default",
            before=(original,),
        )
        native.write_text(SKILL.format(name="reviewer") + "Changed.\n", encoding="utf-8")

        rejected = service.restore_all(
            source.operation_id,
            AssetSelector(agent="codex", kind="skill"),
        )
        displaced = service.status(ZuatRequest(agents=("codex",))).assets[0]

        assert not rejected.ok
        assert native.read_text(encoding="utf-8").endswith("Changed.\n")
        forced = service.restore_all(
            source.operation_id,
            AssetSelector(agent="codex", kind="skill"),
            force=True,
        )
        assert forced.ok
        assert native.read_text(encoding="utf-8") == SKILL.format(name="reviewer")
        assert registry.asset_payload(
            displaced.ref, displaced.fingerprint
        ).exists()
    finally:
        registry.close()
