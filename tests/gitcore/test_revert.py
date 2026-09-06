from pathlib import Path

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    GitRegistry,
    OperationKind,
    OperationOutcome,
)


def asset_states(registry: GitRegistry, source: Path):
    ref = registry.ensure_asset_ref(
        agent="codex",
        kind="skill",
        scope="user",
        locator="skills/reviewer",
    )
    absent = AssetEvidence(
        ref, None, Authority.UNAUTHORITATIVE, present=False
    )
    installed = AssetEvidence(
        ref,
        "sha256:reviewer",
        Authority.AUTHORITATIVE,
        evidence={"normalized_path": "codex/user/skills/reviewer"},
    )
    registry.archive_asset(
        ref,
        "codex/user/skills/reviewer",
        source,
        "sha256:reviewer",
    )
    return ref, absent, installed


def test_install_and_uninstall_revert_as_new_forward_events(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        source = tmp_path / "reviewer"
        source.mkdir()
        (source / "SKILL.md").write_text("review", encoding="utf-8")
        ref, absent, installed = asset_states(registry, source)
        install = registry.record_asset_operation(
            OperationKind.INSTALL,
            OperationOutcome.SUCCESS,
            profile="default",
            before=(absent,),
            after=(installed,),
        )
        assert registry.projected_state().profile("default").assets == (ref.id,)

        revert_install = registry.record_revert(install.operation_id)
        assert revert_install.kind is OperationKind.REVERT
        assert revert_install.reverts == install.operation_id
        assert registry.projected_state().profile("default").assets == ()

        revert_the_revert = registry.record_revert(revert_install.operation_id)
        assert revert_the_revert.reverts == revert_install.operation_id
        assert registry.projected_state().profile("default").assets == (ref.id,)

        uninstall = registry.record_asset_operation(
            OperationKind.UNINSTALL,
            OperationOutcome.SUCCESS,
            profile="default",
            before=(installed,),
            after=(absent,),
        )
        assert registry.projected_state().profile("default").assets == ()

        registry.record_revert(uninstall.operation_id)
        assert registry.projected_state().profile("default").assets == (ref.id,)
        assert [event.kind for event in registry.history()] == [
            OperationKind.INSTALL,
            OperationKind.REVERT,
            OperationKind.REVERT,
            OperationKind.UNINSTALL,
            OperationKind.REVERT,
        ]


def test_profile_switch_revert_selects_prior_profile_in_a_new_event(
    tmp_path: Path,
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        registry.create_profile("work")
        switched = registry.record_profile_switch(
            "work", OperationOutcome.SUCCESS
        )
        history_before = registry.history()

        reverted = registry.record_revert(switched.operation_id)

        assert registry.projected_state().selected_profile == "default"
        assert reverted.kind is OperationKind.REVERT
        assert reverted.reverts == switched.operation_id
        assert registry.history()[:-1] == history_before


def test_intervening_drift_requires_a_fresh_force_decision(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        source = tmp_path / "reviewer"
        source.mkdir()
        (source / "SKILL.md").write_text("review", encoding="utf-8")
        ref, absent, installed = asset_states(registry, source)
        install = registry.record_asset_operation(
            OperationKind.INSTALL,
            OperationOutcome.SUCCESS,
            profile="default",
            before=(absent,),
            after=(installed,),
        )
        drift = AssetEvidence(
            ref, "sha256:user-edit", Authority.CONFLICTING
        )

        rejected = registry.record_revert(
            install.operation_id, current=(drift,)
        )

        assert rejected.outcome is OperationOutcome.REJECTED
        assert registry.projected_state().profile("default").assets == (ref.id,)
        forced = registry.record_revert(
            install.operation_id, current=(drift,), forced=True
        )
        assert forced.outcome is OperationOutcome.SUCCESS
        assert forced.forced is True
        assert registry.projected_state().profile("default").assets == ()
