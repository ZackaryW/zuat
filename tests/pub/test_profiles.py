from pathlib import Path

from zuat.gitcore import GitRegistry, OperationKind, OperationOutcome
from zuat.pub import OperationStatus, Zuat, ZuatRequest
from zuat.specs.interface import (
    ConflictPolicy,
    Materialization,
    Observation,
    ResolutionError,
    ResolutionPlan,
)


class SwitchResolver:
    agent = "codex"

    def __init__(self) -> None:
        self.preflight_error: str | None = None
        self.materialization_state = "converged"
        self.last_policy: ConflictPolicy | None = None
        self.require_replace = False

    def observe(self, root: Path) -> Observation:
        return Observation(self.agent)

    def plan(
        self,
        desired_root: Path,
        *,
        conflict_policy: ConflictPolicy = ConflictPolicy.ABORT,
    ) -> ResolutionPlan:
        self.last_policy = conflict_policy
        return ResolutionPlan(
            self.agent, desired_root / self.agent, (), conflict_policy
        )

    def preflight(self, plan: ResolutionPlan) -> None:
        if self.require_replace and plan.conflict_policy is ConflictPolicy.ABORT:
            raise ResolutionError("conflicting unauthoritative state")
        if self.preflight_error:
            raise ResolutionError(self.preflight_error)

    def materialize(self, plan: ResolutionPlan) -> Materialization:
        return Materialization(self.agent, self.materialization_state)


def service_with_profile(tmp_path: Path):
    registry = GitRegistry(tmp_path / "registry")
    registry.create_profile("work")
    resolver = SwitchResolver()
    service = Zuat(registry=registry, resolvers={"codex": resolver})
    return service, registry, resolver


def test_verified_switch_selects_target_and_appends_domain_event(
    tmp_path: Path,
) -> None:
    service, registry, _ = service_with_profile(tmp_path)
    try:
        result = service.switch_profile(
            ZuatRequest(profile="work", agents=("codex",))
        )

        assert result.status is OperationStatus.SUCCESS
        assert result.profile == "work"
        assert registry.projected_state().selected_profile == "work"
        event = registry.history()[-1]
        assert event.kind is OperationKind.PROFILE_SWITCH
        assert event.outcome is OperationOutcome.SUCCESS
        assert result.operation_id == event.operation_id
    finally:
        registry.close()


def test_failed_preflight_never_selects_or_mutates_target(tmp_path: Path) -> None:
    service, registry, resolver = service_with_profile(tmp_path)
    resolver.preflight_error = "destination is not writable"
    try:
        result = service.switch_profile(
            ZuatRequest(profile="work", agents=("codex",))
        )

        assert result.status is OperationStatus.FAILED
        assert registry.projected_state().selected_profile == "default"
        event = registry.history()[-1]
        assert event.kind is OperationKind.PROFILE_SWITCH
        assert event.outcome is OperationOutcome.REJECTED
    finally:
        registry.close()


def test_partial_switch_is_journaled_without_selecting_target(tmp_path: Path) -> None:
    service, registry, resolver = service_with_profile(tmp_path)
    resolver.materialization_state = "indeterminate"
    try:
        result = service.switch_profile(
            ZuatRequest(profile="work", agents=("codex",))
        )

        assert result.status is OperationStatus.PARTIAL
        assert registry.projected_state().selected_profile == "default"
        assert registry.history()[-1].outcome is OperationOutcome.INDETERMINATE
    finally:
        registry.close()


def test_force_is_scoped_to_the_requested_switch(tmp_path: Path) -> None:
    service, registry, resolver = service_with_profile(tmp_path)
    try:
        result = service.switch_profile(
            ZuatRequest(profile="work", agents=("codex",), force=True)
        )

        assert result.status is OperationStatus.SUCCESS
        assert resolver.last_policy is ConflictPolicy.REPLACE
        assert registry.history()[-1].forced is True
    finally:
        registry.close()


def test_conflicting_switch_rejects_then_accepts_one_forced_attempt(
    tmp_path: Path,
) -> None:
    service, registry, resolver = service_with_profile(tmp_path)
    resolver.require_replace = True
    try:
        rejected = service.switch_profile(
            ZuatRequest(profile="work", agents=("codex",))
        )
        assert rejected.status is OperationStatus.FAILED
        assert registry.projected_state().selected_profile == "default"

        forced = service.switch_profile(
            ZuatRequest(profile="work", agents=("codex",), force=True)
        )
        assert forced.status is OperationStatus.SUCCESS
        assert registry.projected_state().selected_profile == "work"
        assert registry.history()[-1].forced is True
    finally:
        registry.close()
