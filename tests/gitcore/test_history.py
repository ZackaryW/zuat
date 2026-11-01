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


def _count_decodes(monkeypatch) -> list[int]:
    decoded = [0]
    original = GitRegistry._event_from_dict.__func__

    def counting(cls, value):
        decoded[0] += 1
        return original(cls, value)

    monkeypatch.setattr(GitRegistry, "_event_from_dict", classmethod(counting))
    return decoded


def test_history_reads_decode_only_new_operation_documents(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        first = registry.append_event(OperationKind.INSTALL, OperationOutcome.SUCCESS)
        decoded = _count_decodes(monkeypatch)

        assert registry.history() == (first,)
        decoded[0] = 0
        assert registry.history() == (first,)
        assert decoded[0] == 0

        second = registry.append_event(OperationKind.UNINSTALL, OperationOutcome.SUCCESS)
        decoded[0] = 0
        assert registry.history() == (first, second)
        assert decoded[0] == 1


def test_history_includes_documents_appended_by_another_handle(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        first = registry.append_event(OperationKind.INSTALL, OperationOutcome.SUCCESS)
        assert registry.history() == (first,)
        with GitRegistry(root) as other:
            second = other.append_event(OperationKind.UNINSTALL, OperationOutcome.SUCCESS)
        assert registry.history() == (first, second)


def test_history_rejects_a_gap_after_a_cached_read(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        registry.append_event(OperationKind.INSTALL, OperationOutcome.SUCCESS)
        registry.append_event(OperationKind.UNINSTALL, OperationOutcome.SUCCESS)
        registry.history()
        sorted((root / "operations").glob("*.json"))[0].unlink()
        with pytest.raises(RegistryError, match="not contiguous"):
            registry.history()


def test_find_asset_ref_resolves_from_the_catalog_without_the_journal(
    tmp_path: Path, monkeypatch
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        ref = registry.ensure_asset_ref(
            agent="codex", kind="skill", scope="user", locator="skills/reviewer"
        )
        registry.append_event(OperationKind.INSTALL, OperationOutcome.SUCCESS)

        def journal_read(self):
            raise AssertionError("asset lookup replayed the journal")

        monkeypatch.setattr(GitRegistry, "history", journal_read)
        assert registry.find_asset_ref(ref.id) == ref
        with pytest.raises(RegistryError, match="unknown asset reference"):
            registry.find_asset_ref("asset_missing")
