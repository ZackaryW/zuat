from pathlib import Path

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    GitRegistry,
    OperationKind,
)


def observed(registry: GitRegistry, fingerprint: str) -> AssetEvidence:
    ref = registry.ensure_asset_ref(
        agent="claude",
        kind="hook",
        scope="user",
        locator="settings/hooks/SessionStart/0",
    )
    return AssetEvidence(ref, fingerprint, Authority.UNAUTHORITATIVE)


def test_changed_observations_append_and_identical_observations_deduplicate(
    tmp_path: Path,
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        initial = observed(registry, "sha256:one")
        first = registry.record_observation((initial,))
        duplicate_evidence = observed(registry, "sha256:one")
        duplicate = registry.record_observation((duplicate_evidence,))
        changed_evidence = observed(registry, "sha256:two")
        changed = registry.record_observation((changed_evidence,))

        assert first is not None
        assert duplicate is None
        assert changed is not None
        assert duplicate_evidence.ref == initial.ref == changed_evidence.ref
        assert [event.kind for event in registry.history()] == [
            OperationKind.OBSERVE,
            OperationKind.OBSERVE,
        ]
        assert registry.projected_state().profile("default").assets == ()


def test_partial_observation_does_not_turn_unseen_assets_into_deletions(
    tmp_path: Path,
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        complete = observed(registry, "sha256:one")
        registry.record_observation((complete,))

        partial = registry.record_observation((), completeness="partial")

        assert partial is not None
        assert partial.completeness == "partial"
        assert partial.after == ()
        assert registry.latest_observation() == (complete,)
        assert registry.projected_state().profile("default").assets == ()
