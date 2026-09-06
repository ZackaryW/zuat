"""Pure evidence transformations shared by observation and recovery.

These helpers retain identity and ownership facts without reading native state
or granting authority. Transaction and conflict policy remain with orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from zuat.gitcore import (
    AssetEvidence,
    Authority,
)


def affected_evidence(
    before: Sequence[AssetEvidence], after: Sequence[AssetEvidence]
) -> tuple[AssetEvidence, ...]:
    """Union both sides of a transition so newly introduced assets can be undone."""
    selected: dict[str, AssetEvidence] = {item.ref.id: item for item in after}
    selected.update({item.ref.id: item for item in before})
    return tuple(selected[key] for key in sorted(selected))


def current_evidence(
    affected: Sequence[AssetEvidence], observed: Sequence[AssetEvidence]
) -> tuple[AssetEvidence, ...]:
    """Align observations with targets while retaining identity for missing assets."""
    observed_by_id = {item.ref.id: item for item in observed}
    return tuple(
        observed_by_id.get(item.ref.id)
        or AssetEvidence(
            item.ref,
            None,
            Authority.CONFLICTING,
            present=False,
            evidence=dict(item.evidence),
        )
        for item in affected
    )


def desired_inverse(
    inverse: Sequence[AssetEvidence], affected: Sequence[AssetEvidence]
) -> tuple[AssetEvidence, ...]:
    """Mark assets absent when the original transition introduced them.

    This is what distinguishes a full revert from restoring only prior content.
    """
    desired = {item.ref.id: item for item in inverse}
    return tuple(
        desired.get(item.ref.id)
        or AssetEvidence(
            item.ref,
            None,
            Authority.UNAUTHORITATIVE,
            present=False,
            evidence=dict(item.evidence),
        )
        for item in affected
    )


def same_recovery_state(expected: AssetEvidence, actual: AssetEvidence) -> bool:
    """Require content and authority, plus captured ownership, before a no-op.

    Matching bytes alone must not hide a changed receipt or accidental adoption.
    """
    return (
        actual.present
        and actual.fingerprint == expected.fingerprint
        and actual.authority is expected.authority
        and (
            "ownership" not in expected.evidence
            or actual.evidence.get("ownership") == expected.evidence["ownership"]
        )
    )


def absent_evidence(item: AssetEvidence) -> AssetEvidence:
    """Keep identity/provider metadata when expressing removal without ownership."""
    return AssetEvidence(
        item.ref,
        None,
        Authority.UNAUTHORITATIVE,
        present=False,
        evidence=dict(item.evidence),
    )
