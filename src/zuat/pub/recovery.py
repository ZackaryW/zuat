"""Forward-appending inversion and selected-asset restoration.

Revert undoes a successful transition, including its newly introduced assets;
restore recovers selected assets that existed before a transition. Both reuse
archived projections and native resolvers, never Git resets or a second native
rollback implementation."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from zuat.gitcore import (
    AssetEvidence,
    OperationKind,
    OperationOutcome,
    RegistryError,
)
from zuat.pub.models import (
    AssetSelector,
    OperationResult,
    OperationStatus,
    ZuatRequest,
)
from zuat.pub.results import (
    empty_bulk_result,
    failed,
    materialization_outcome,
)
from zuat.pub.selection import validate_agents
from zuat.specs.interface import (
    ConflictPolicy,
    ResolutionError,
)
from zuat.utils.evidence import (
    affected_evidence,
    current_evidence,
    desired_inverse,
    same_recovery_state,
)

if TYPE_CHECKING:
    from zuat.pub.service import Zuat


class RecoveryOperations:
    """Focused orchestration using the facade's shared registry and resolver context."""

    def __init__(self, service: Zuat) -> None:
        self.service = service

    def revert(self, request: ZuatRequest) -> OperationResult:
        """Invert one successful transition against freshly observed current state.

        Validate every affected reference before observation, then check intervening
        changes. Forced inversion archives conflicts first; success appends a new
        event and never erases the operation being reverted.
        """
        service = self.service
        if not request.operation_id:
            return failed("revert", "an operation id is required")
        marker_id: str | None = None
        current: tuple[AssetEvidence, ...] = ()
        try:
            with service.registry.operation():
                target = service.registry.event(request.operation_id)
                service._observations.validate_refs(
                    tuple(item.ref.id for item in (*target.before, *target.after))
                )
                if target.outcome is not OperationOutcome.SUCCESS:
                    raise RegistryError("only a successful operation can be reverted")
                if target.kind is OperationKind.PROFILE_SWITCH or (
                    target.kind is OperationKind.REVERT
                    and target.metadata.get("state_kind") == "profile-switch"
                ):
                    return service._profiles.revert_profile_switch(request, target)
                if target.kind not in {
                    OperationKind.INSTALL,
                    OperationKind.UPDATE,
                    OperationKind.UNINSTALL,
                    OperationKind.REVERT,
                }:
                    raise RegistryError(
                        f"operation cannot be reverted: {target.kind.value}"
                    )

                profile = (
                    target.profile
                    or service.registry.projected_state().selected_profile
                )
                if profile != service.registry.projected_state().selected_profile:
                    raise RegistryError("asset revert requires the selected profile")
                affected = affected_evidence(target.before, target.after)
                required_agents = tuple(
                    dict.fromkeys(item.ref.agent for item in affected)
                )
                selected_agents = validate_agents(request.agents)
                if not set(required_agents).issubset(selected_agents):
                    raise ResolutionError(
                        "revert agents must include: " + ", ".join(required_agents)
                    )
                observed, _, _, observation_diagnostics = service._observations.observe(
                    selected_agents
                )
                current = current_evidence(affected, observed)
                if service.registry.revert_conflicts(target.operation_id, current):
                    if not request.force:
                        event = service.registry.record_revert(
                            target.operation_id,
                            current=current,
                            diagnostics=observation_diagnostics,
                        )
                        return OperationResult(
                            "revert",
                            OperationStatus.FAILED,
                            operation_id=event.operation_id,
                            profile=profile,
                            assets=current,
                            diagnostics=event.diagnostics,
                        )
                    service._projections.archive_current_evidence(current)

                desired = desired_inverse(target.before, affected)
                with tempfile.TemporaryDirectory() as temporary:
                    temporary_profile = Path(temporary) / "profile"
                    shutil.copytree(
                        service.registry.profile_root(profile), temporary_profile
                    )
                    service._projections.write_inverse_profile(
                        temporary_profile, desired
                    )
                    policy = (
                        ConflictPolicy.REPLACE
                        if request.force
                        else ConflictPolicy.ABORT
                    )
                    plans = tuple(
                        service._resolver(agent).plan(
                            temporary_profile, conflict_policy=policy
                        )
                        for agent in required_agents
                    )
                    try:
                        for plan in plans:
                            service._resolver(plan.agent).preflight(plan)
                    except (ResolutionError, ValueError, OSError) as error:
                        event = service.registry.append_event(
                            OperationKind.REVERT,
                            OperationOutcome.REJECTED,
                            profile=profile,
                            forced=request.force,
                            before=current,
                            after=desired,
                            reverts=target.operation_id,
                            diagnostics=(str(error),),
                            metadata={
                                "reverted_kind": target.kind.value,
                                "state_kind": "asset",
                            },
                        )
                        return OperationResult(
                            "revert",
                            OperationStatus.FAILED,
                            operation_id=event.operation_id,
                            profile=profile,
                            assets=current,
                            diagnostics=(str(error),),
                        )

                    marker_id = service.registry.begin_operation(
                        OperationKind.REVERT,
                        profile=profile,
                        before=current,
                        metadata={"reverts": target.operation_id},
                    )
                    materializations = tuple(
                        service._resolver(plan.agent).materialize(plan)
                        for plan in plans
                    )
                    public_status, outcome = materialization_outcome(materializations)
                    diagnostics = tuple(
                        message
                        for item in materializations
                        for message in item.diagnostics
                    )
                    if outcome is OperationOutcome.SUCCESS:
                        service._projections.project_inverse_profile(profile, desired)
                        event = service.registry.record_revert(
                            target.operation_id,
                            current=current,
                            forced=request.force,
                            diagnostics=diagnostics,
                            event_operation_id=marker_id,
                        )
                    else:
                        event = service.registry.append_event(
                            OperationKind.REVERT,
                            outcome,
                            profile=profile,
                            forced=request.force,
                            before=current,
                            after=desired,
                            reverts=target.operation_id,
                            diagnostics=diagnostics,
                            metadata={
                                "reverted_kind": target.kind.value,
                                "state_kind": "asset",
                            },
                            operation_id=marker_id,
                        )
                    service.registry.finish_operation(marker_id, event.outcome)
                    marker_id = None
                    return OperationResult(
                        "revert",
                        public_status,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=desired
                        if outcome is OperationOutcome.SUCCESS
                        else current,
                        materializations=materializations,
                        diagnostics=diagnostics,
                    )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if marker_id is not None:
                try:
                    event = service.registry.append_event(
                        OperationKind.REVERT,
                        OperationOutcome.FAILED,
                        profile=service.registry.projected_state().selected_profile,
                        forced=request.force,
                        before=current,
                        reverts=request.operation_id,
                        diagnostics=(str(error),),
                        metadata={"state_kind": "asset"},
                        operation_id=marker_id,
                    )
                    service.registry.finish_operation(marker_id, event.outcome)
                    return OperationResult(
                        "revert",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=event.profile,
                        assets=current,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return failed("revert", str(error))

    def restore_all(
        self,
        operation_id: str,
        selector: AssetSelector,
        *,
        force: bool = False,
    ) -> OperationResult:
        """Recover selected before-state assets without deleting later additions.

        Compare content and ownership before treating restoration as a no-op. Only
        hand off interrupted-update intent after safe plans exist (or the prior
        state is verified), so a rejected restore leaves recovery actionable.
        """
        service = self.service
        marker_id: str | None = None
        current: tuple[AssetEvidence, ...] = ()
        profile = service.registry.projected_state().selected_profile
        try:
            with service.registry.operation():
                target = service._assets.restore_target(operation_id)
                service._observations.validate_refs(
                    tuple(
                        item.ref.id for item in target.before if selector.matches(item)
                    )
                )
                profile = target.profile or profile
                if profile != service.registry.projected_state().selected_profile:
                    raise RegistryError("restore requires the selected profile")
                desired = tuple(
                    item
                    for item in target.before
                    if item.present and selector.matches(item)
                )
                if not desired:
                    return empty_bulk_result(
                        service.registry.projected_state().selected_profile,
                        "restore-all",
                    )

                observed, _, _, observation_diagnostics = service._observations.observe(
                    (selector.agent,)
                )
                all_current = current_evidence(desired, observed)
                all_current = tuple(
                    service._assets.recovery_evidence(expected)
                    if "ownership" in expected.evidence
                    else actual
                    for expected, actual in zip(desired, all_current)
                )
                repair_pairs = tuple(
                    (expected, actual)
                    for expected, actual in zip(desired, all_current)
                    if not same_recovery_state(expected, actual)
                )
                if not repair_pairs:
                    service._assets.handoff_pending_restore(operation_id)
                    return OperationResult(
                        operation="restore-all",
                        status=OperationStatus.SUCCESS,
                        profile=profile,
                        assets=desired,
                    )

                repairs = tuple(expected for expected, _ in repair_pairs)
                current = tuple(actual for _, actual in repair_pairs)
                conflicts = tuple(
                    actual
                    for expected, actual in repair_pairs
                    if actual.present and actual.fingerprint != expected.fingerprint
                )
                if conflicts and not force:
                    diagnostic = (
                        "force is required to restore over conflicting assets: "
                        + ", ".join(item.ref.id for item in conflicts)
                    )
                    event = service.registry.append_event(
                        OperationKind.RESTORE,
                        OperationOutcome.REJECTED,
                        profile=profile,
                        before=current,
                        after=repairs,
                        diagnostics=tuple((*observation_diagnostics, diagnostic)),
                        metadata={"restores": operation_id},
                    )
                    return OperationResult(
                        operation="restore-all",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=current,
                        diagnostics=event.diagnostics,
                    )
                if conflicts:
                    service._projections.archive_current_evidence(conflicts)

                with tempfile.TemporaryDirectory() as temporary:
                    temporary_profile = Path(temporary) / "profile"
                    shutil.copytree(
                        service.registry.profile_root(profile), temporary_profile
                    )
                    try:
                        service._projections.write_inverse_profile(
                            temporary_profile, repairs
                        )
                        plans = service._projections.restore_plans(
                            temporary_profile, repairs
                        )
                        for plan in plans:
                            service._resolver(plan.agent).preflight(plan)
                    except (
                        RegistryError,
                        ResolutionError,
                        ValueError,
                        OSError,
                    ) as error:
                        event = service.registry.append_event(
                            OperationKind.RESTORE,
                            OperationOutcome.REJECTED,
                            profile=profile,
                            forced=force,
                            before=current,
                            after=repairs,
                            diagnostics=(str(error),),
                            metadata={"restores": operation_id},
                        )
                        return OperationResult(
                            operation="restore-all",
                            status=OperationStatus.FAILED,
                            operation_id=event.operation_id,
                            profile=profile,
                            assets=current,
                            diagnostics=(str(error),),
                        )

                    service._assets.handoff_pending_restore(operation_id)
                    marker_id = service.registry.begin_operation(
                        OperationKind.RESTORE,
                        profile=profile,
                        before=current,
                        metadata={
                            "restores": operation_id,
                            "state_kind": "asset-update",
                        }
                        if any("ownership" in item.evidence for item in repairs)
                        else {"restores": operation_id},
                    )
                    materializations = tuple(
                        service._resolver(plan.agent).materialize(plan)
                        for plan in plans
                    )
                    public_status, outcome = materialization_outcome(materializations)
                    diagnostics = tuple(
                        message
                        for item in materializations
                        for message in item.diagnostics
                    )
                    result_assets: tuple[AssetEvidence, ...] = current
                    if outcome is OperationOutcome.SUCCESS:
                        service._projections.project_inverse_profile(profile, repairs)
                        refreshed, _, _, refresh_diagnostics = (
                            service._observations.observe((selector.agent,))
                        )
                        verified = current_evidence(repairs, refreshed)
                        verified = tuple(
                            service._assets.recovery_evidence(expected)
                            if "ownership" in expected.evidence
                            else actual
                            for expected, actual in zip(repairs, verified)
                        )
                        if all(
                            same_recovery_state(expected, actual)
                            for expected, actual in zip(repairs, verified)
                        ):
                            result_assets = repairs
                        else:
                            public_status = OperationStatus.PARTIAL
                            outcome = OperationOutcome.PARTIAL
                            diagnostics = tuple(
                                (
                                    *diagnostics,
                                    *refresh_diagnostics,
                                    "restore verification failed",
                                )
                            )
                            result_assets = verified
                    event = service.registry.append_event(
                        OperationKind.RESTORE,
                        outcome,
                        profile=profile,
                        forced=force,
                        before=current,
                        after=repairs,
                        diagnostics=diagnostics,
                        metadata={"restores": operation_id},
                        operation_id=marker_id,
                    )
                    service.registry.finish_operation(marker_id, event.outcome)
                    marker_id = None
                    return OperationResult(
                        operation="restore-all",
                        status=public_status,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=result_assets,
                        materializations=materializations,
                        diagnostics=diagnostics,
                    )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if marker_id is not None:
                try:
                    event = service.registry.append_event(
                        OperationKind.RESTORE,
                        OperationOutcome.FAILED,
                        profile=profile,
                        forced=force,
                        before=current,
                        diagnostics=(str(error),),
                        metadata={"restores": operation_id},
                        operation_id=marker_id,
                    )
                    service.registry.finish_operation(marker_id, event.outcome)
                    return OperationResult(
                        operation="restore-all",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=current,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return failed("restore-all", str(error))
