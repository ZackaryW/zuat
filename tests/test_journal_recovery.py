from pathlib import Path

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    GitRegistry,
    OperationKind,
    OperationOutcome,
)


def test_interrupted_operation_becomes_an_indeterminate_recovery_event(
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        ref = registry.ensure_asset_ref(
            agent="codex",
            kind="skill",
            scope="user",
            locator="skills/reviewer",
        )
        before = AssetEvidence(ref, "sha256:before", Authority.UNAUTHORITATIVE)
        interrupted_id = registry.begin_operation(
            OperationKind.INSTALL,
            profile="default",
            before=(before,),
        )
        assert registry.recovery_marker.exists()
        assert registry.projected_state().profile("default").assets == ()

    with GitRegistry(root) as recovered:
        event = recovered.history()[-1]
        assert event.kind is OperationKind.RECOVERY
        assert event.outcome is OperationOutcome.INDETERMINATE
        assert event.metadata["interrupted_operation_id"] == interrupted_id
        assert event.before == (before,)
        assert recovered.projected_state().profile("default").assets == ()
        assert not recovered.recovery_marker.exists()
