"""Agent-neutral lifecycle result assembly."""

from __future__ import annotations

from collections.abc import Callable

from zuat.specs.interface import Materialization, MaterializationRecord, PlannedAction, ResolutionPlan
from zuat.specs.native import NativeError


def materialize_plan(
    agent: str,
    plan: ResolutionPlan,
    apply: Callable[[PlannedAction], object],
) -> Materialization:
    records: list[MaterializationRecord] = []
    diagnostics: list[str] = []
    for action in plan.actions:
        asset = action.asset
        try:
            result = apply(action)
            status = str(getattr(result, "status", "indeterminate"))
            verified = bool(getattr(result, "verified", False))
            evidence = result.to_dict() if hasattr(result, "to_dict") else {}
        except (NativeError, OSError, ValueError) as error:
            status = "indeterminate" if asset.kind.value == "plugin" else "failed"
            verified = False
            evidence = {"error": str(error)}
            diagnostics.append(f"{asset.kind.value} {asset.name}: {error}")
        records.append(MaterializationRecord(agent, action.operation, asset.kind.value, asset.name, status, verified, evidence))
    failed = [item for item in records if not item.verified]
    if not failed:
        state = "converged"
    elif len(failed) != len(records) or any(item.status == "partial" for item in failed):
        state = "partial"
    elif all(item.status == "indeterminate" for item in failed):
        state = "indeterminate"
    else:
        state = "failed"
    return Materialization(agent, state, tuple(records), tuple(diagnostics))
