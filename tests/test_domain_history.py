from pathlib import Path

import pytest

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    GitRegistry,
    OperationKind,
    OperationOutcome,
    RegistryError,
)
from zuat.pub import Zuat


def test_history_preserves_domain_evidence_and_stable_lookup(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        ref = registry.ensure_asset_ref(
            agent="codex",
            kind="skill",
            scope="user",
            locator="skills/reviewer",
        )
        before = AssetEvidence(ref, "sha256:old", Authority.UNAUTHORITATIVE)
        after = AssetEvidence(ref, "sha256:new", Authority.AUTHORITATIVE)
        first = registry.append_event(
            OperationKind.INSTALL,
            OperationOutcome.SUCCESS,
            profile="default",
            forced=True,
            before=(before,),
            after=(after,),
        )
        second = registry.append_event(
            OperationKind.UNINSTALL,
            OperationOutcome.REJECTED,
            profile="default",
            diagnostics=("force required",),
        )

        assert registry.event(first.operation_id) == first
        assert registry.history() == (first, second)
        with pytest.raises(RegistryError, match="operation identifier"):
            registry.append_event(
                OperationKind.REVERT,
                OperationOutcome.SUCCESS,
                operation_id=first.operation_id,
            )

    with GitRegistry(root) as reopened:
        result = Zuat(registry=reopened).history()
        assert [item.operation_id for item in result.history] == [
            first.operation_id,
            second.operation_id,
        ]
        payload = result.to_dict()
        assert payload["history"][0]["forced"] is True
        assert payload["history"][0]["before"][0]["fingerprint"] == "sha256:old"
        assert not (
            {"revision", "commit", "branch", "tree", "index"}
            & set(payload["history"][0])
        )
