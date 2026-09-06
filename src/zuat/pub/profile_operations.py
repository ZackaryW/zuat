"""Named-profile selection and its inverse transitions.

The module name deliberately differs from the exported ``zuat.pub.profiles``
function: importing a same-named submodule would replace that package attribute.

A profile is desired state, not proof that an agent applied it. Preflight all
selected agents before starting mutation, and advance profile selection only
through the journal's verified transition. Foreign project entries remain stored
without being claimed as applied in this runtime context."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zuat.gitcore import (
    OperationKind,
    OperationOutcome,
    RegistryError,
)
from zuat.pub.models import (
    OperationResult,
    OperationStatus,
    ZuatRequest,
)
from zuat.pub.results import (
    failed,
    materialization_outcome,
)
from zuat.pub.selection import validate_agents
from zuat.specs.interface import (
    ConflictPolicy,
    ResolutionError,
)
from zuat.utils.contexts import (
    locator_context,
    project_context,
)

if TYPE_CHECKING:
    from zuat.pub.service import Zuat


class ProfileOperations:
    """Focused orchestration using the facade's shared registry and resolver context."""

    def __init__(self, service: Zuat) -> None:
        self.service = service

    def profiles(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        """List desired profiles without implying they have been applied natively."""
        service = self.service
        del request
        try:
            state = service.registry.projected_state()
            return OperationResult(
                operation="profile-list",
                status=OperationStatus.SUCCESS,
                profile=state.selected_profile,
                profiles=state.profiles,
            )
        except RegistryError as error:
            return failed("profile-list", str(error))

    def create_profile(self, request: ZuatRequest) -> OperationResult:
        """Observe before creating a profile so current drift remains in the trail."""
        service = self.service
        if not request.profile:
            return failed("profile-create", "a profile is required")
        try:
            with service.registry.operation():
                service._observations.observe(request.agents)
                event = service.registry.create_profile(request.profile)
                state = service.registry.projected_state()
            return OperationResult(
                operation="profile-create",
                status=OperationStatus.SUCCESS,
                operation_id=event.operation_id,
                profile=state.selected_profile,
                profiles=state.profiles,
            )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return failed("profile-create", str(error))

    def switch_profile(self, request: ZuatRequest) -> OperationResult:
        """Preflight every agent before starting a named-profile transition.

        Selection is journaled only after materialization reports its outcome; a
        rejected or partial native application must not masquerade as convergence.
        """
        service = self.service
        if not request.profile:
            return failed("profile-switch", "a profile is required")
        selected_agents = request.agents
        operation_id: str | None = None
        try:
            with service.registry.operation():
                before, _, _, _ = service._observations.observe(selected_agents)
                target_root = service.registry.profile_root(request.profile)
                policy = (
                    ConflictPolicy.REPLACE if request.force else ConflictPolicy.ABORT
                )
                plans = tuple(
                    service._resolver(agent).plan(target_root, conflict_policy=policy)
                    for agent in validate_agents(selected_agents)
                )
                try:
                    for plan in plans:
                        service._resolver(plan.agent).preflight(plan)
                except (ResolutionError, ValueError, OSError) as error:
                    event = service.registry.record_profile_switch(
                        request.profile,
                        OperationOutcome.REJECTED,
                        forced=request.force,
                        before=before,
                        diagnostics=(str(error),),
                    )
                    return OperationResult(
                        operation="profile-switch",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=service.registry.projected_state().selected_profile,
                        assets=before,
                        diagnostics=(str(error),),
                    )

                operation_id = service.registry.begin_operation(
                    OperationKind.PROFILE_SWITCH,
                    profile=request.profile,
                    before=before,
                )
                materializations = tuple(
                    service._resolver(plan.agent).materialize(plan) for plan in plans
                )
                public_status, outcome = materialization_outcome(materializations)
                diagnostics = tuple(
                    message for item in materializations for message in item.diagnostics
                )
                event = service.registry.record_profile_switch(
                    request.profile,
                    outcome,
                    forced=request.force,
                    before=before,
                    diagnostics=diagnostics,
                    operation_id=operation_id,
                )
                service.registry.finish_operation(operation_id, event.outcome)
                return OperationResult(
                    operation="profile-switch",
                    status=public_status,
                    operation_id=event.operation_id,
                    profile=service.registry.projected_state().selected_profile,
                    assets=before,
                    materializations=materializations,
                    diagnostics=diagnostics,
                    data={
                        "coverage": self.profile_coverage(
                            request.profile, selected_agents
                        )
                    },
                )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if operation_id is not None:
                try:
                    event = service.registry.record_profile_switch(
                        request.profile,
                        OperationOutcome.FAILED,
                        forced=request.force,
                        diagnostics=(str(error),),
                        operation_id=operation_id,
                    )
                    service.registry.finish_operation(operation_id, event.outcome)
                    return OperationResult(
                        operation="profile-switch",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=service.registry.projected_state().selected_profile,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return failed("profile-switch", str(error))

    def revert_profile_switch(self, request: ZuatRequest, target) -> OperationResult:
        """Invert profile selection while preserving forward transition history.

        Called from revert with the registry lock held. This uses profile plans,
        not asset inverses, because selection and native application must agree.
        """
        service = self.service
        destination = target.metadata.get("from_profile")
        if not isinstance(destination, str):
            raise RegistryError("profile transition has no prior profile")
        current_profile = service.registry.projected_state().selected_profile
        if service.registry.revert_conflicts(target.operation_id) and not request.force:
            event = service.registry.record_revert(target.operation_id)
            return OperationResult(
                "revert",
                OperationStatus.FAILED,
                operation_id=event.operation_id,
                profile=current_profile,
                diagnostics=event.diagnostics,
            )
        before, _, _, _ = service._observations.observe(request.agents)
        target_root = service.registry.profile_root(destination)
        policy = ConflictPolicy.REPLACE if request.force else ConflictPolicy.ABORT
        plans = tuple(
            service._resolver(agent).plan(target_root, conflict_policy=policy)
            for agent in validate_agents(request.agents)
        )
        try:
            for plan in plans:
                service._resolver(plan.agent).preflight(plan)
        except (ResolutionError, ValueError, OSError) as error:
            event = service.registry.append_event(
                OperationKind.REVERT,
                OperationOutcome.REJECTED,
                profile=current_profile,
                forced=request.force,
                before=before,
                reverts=target.operation_id,
                diagnostics=(str(error),),
                metadata={
                    "reverted_kind": target.kind.value,
                    "state_kind": "profile-switch",
                },
            )
            return OperationResult(
                "revert",
                OperationStatus.FAILED,
                operation_id=event.operation_id,
                profile=current_profile,
                assets=before,
                diagnostics=(str(error),),
            )
        marker_id = service.registry.begin_operation(
            OperationKind.REVERT,
            profile=current_profile,
            before=before,
            metadata={"reverts": target.operation_id},
        )
        materializations = tuple(
            service._resolver(plan.agent).materialize(plan) for plan in plans
        )
        public_status, outcome = materialization_outcome(materializations)
        diagnostics = tuple(
            message for item in materializations for message in item.diagnostics
        )
        if outcome is OperationOutcome.SUCCESS:
            event = service.registry.record_revert(
                target.operation_id,
                forced=request.force,
                diagnostics=diagnostics,
                event_operation_id=marker_id,
            )
        else:
            event = service.registry.append_event(
                OperationKind.REVERT,
                outcome,
                profile=current_profile,
                forced=request.force,
                before=before,
                reverts=target.operation_id,
                diagnostics=diagnostics,
                metadata={
                    "reverted_kind": target.kind.value,
                    "state_kind": "profile-switch",
                },
                operation_id=marker_id,
            )
        service.registry.finish_operation(marker_id, event.outcome)
        return OperationResult(
            "revert",
            public_status,
            operation_id=event.operation_id,
            profile=service.registry.projected_state().selected_profile,
            assets=before,
            materializations=materializations,
            diagnostics=diagnostics,
        )

    def profile_coverage(self, profile, agents):
        """Report excluded profile entries rather than imply cross-project success."""
        service = self.service
        state = service.registry.projected_state()
        ids = set(state.profile(profile).assets)
        excluded = tuple(
            sorted(
                ref.id
                for ref in state.catalog
                if ref.id in ids
                and (
                    ref.agent not in agents
                    or (
                        ref.scope == "project"
                        and locator_context(ref.locator)
                        != project_context(service.project_root)
                    )
                )
            )
        )
        return {
            "project_context": project_context(service.project_root),
            "excluded_asset_refs": excluded,
        }
