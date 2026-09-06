from dataclasses import FrozenInstanceError

import pytest

from zuat.gitcore.models import (
    AssetEvidence,
    AssetRef,
    Authority,
    JournalEvent,
    OperationKind,
    OperationOutcome,
    Profile,
    ProjectedState,
    new_operation_id,
)
from zuat.pub.models import OperationResult, OperationStatus


def evidence(*, fingerprint: str = "sha256:one") -> AssetEvidence:
    return AssetEvidence(
        ref=AssetRef(
            id="asset_codex_reviewer",
            agent="codex",
            kind="skill",
            scope="user",
            locator="skills/reviewer",
        ),
        fingerprint=fingerprint,
        authority=Authority.UNAUTHORITATIVE,
    )


def test_domain_event_is_immutable_and_uses_zuat_identifiers() -> None:
    operation_id = new_operation_id()
    event = JournalEvent(
        operation_id=operation_id,
        sequence=7,
        kind=OperationKind.INSTALL,
        outcome=OperationOutcome.SUCCESS,
        profile="default",
        after=(evidence(),),
    )

    assert operation_id.startswith("op_")
    assert event.to_dict()["operation_id"] == operation_id
    assert event.to_dict()["after"][0]["asset_ref"] == "asset_codex_reviewer"
    assert not (
        {"revision", "commit", "branch", "tree", "index"}
        & set(event.to_dict())
    )
    with pytest.raises(FrozenInstanceError):
        event.sequence = 8  # type: ignore[misc]


def test_projected_state_contains_named_profiles_without_revisions() -> None:
    profile = Profile("work", selected=True, assets=("asset_codex_reviewer",))
    state = ProjectedState(selected_profile="work", profiles=(profile,))

    assert state.profile("work") == profile
    assert state.to_dict() == {
        "selected_profile": "work",
        "profiles": [
            {
                "name": "work",
                "selected": True,
                "assets": ["asset_codex_reviewer"],
            }
        ],
    }


def test_public_result_exposes_domain_evidence_without_git_identifiers() -> None:
    result = OperationResult(
        operation="status",
        status=OperationStatus.SUCCESS,
        operation_id="op_status",
        profile="default",
        assets=(evidence(),),
    )

    payload = result.to_dict()
    assert payload["operation_id"] == "op_status"
    assert payload["assets"][0]["authority"] == "unauthoritative"
    assert not ({"revision", "commit", "branch", "tree", "index"} & set(payload))
