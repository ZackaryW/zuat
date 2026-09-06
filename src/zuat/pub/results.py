"""Translate internal evidence into public outcomes without performing operations."""

from __future__ import annotations

from collections.abc import Sequence

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    OperationOutcome,
)
from zuat.pub.models import (
    OperationResult,
    OperationStatus,
)
from zuat.specs.interface import (
    Materialization,
)


def materialization_outcome(
    materializations: Sequence[Materialization],
) -> tuple[OperationStatus, OperationOutcome]:
    """Translate native verification into honest public and journal outcomes.

    A successful subset remains partial; indeterminate results must retain
    uncertainty rather than be collapsed into a clean failed/no-change claim.
    """
    if all(item.verified for item in materializations):
        return OperationStatus.SUCCESS, OperationOutcome.SUCCESS
    if any(item.verified for item in materializations):
        return OperationStatus.PARTIAL, OperationOutcome.PARTIAL
    if any(item.state == "indeterminate" for item in materializations):
        return OperationStatus.PARTIAL, OperationOutcome.INDETERMINATE
    if any(item.state == "partial" for item in materializations):
        return OperationStatus.PARTIAL, OperationOutcome.PARTIAL
    return OperationStatus.FAILED, OperationOutcome.FAILED


def observation_status(assets: Sequence[AssetEvidence]) -> OperationStatus:
    """Expose uncertain authority without classifying ordinary drift as I/O failure."""
    if any(
        item.authority in {Authority.PARTIAL, Authority.INDETERMINATE}
        for item in assets
    ):
        return OperationStatus.PARTIAL
    return OperationStatus.SUCCESS


def failed(operation: str, diagnostic: str) -> OperationResult:
    """Create a failure result without inventing a journal operation that never began."""
    return OperationResult(
        operation=operation,
        status=OperationStatus.FAILED,
        diagnostics=(diagnostic,),
    )


def empty_bulk_result(profile: str, operation: str) -> OperationResult:
    """Report an empty selection without manufacturing a lifecycle transition."""
    return OperationResult(operation, OperationStatus.SUCCESS, profile=profile)
