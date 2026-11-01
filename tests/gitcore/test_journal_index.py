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


def evidence(registry: GitRegistry, name: str, fingerprint: str, agent="claude"):
    ref = registry.ensure_asset_ref(
        agent=agent, kind="skill", scope="user", locator=f"skills/{name}"
    )
    return AssetEvidence(ref, fingerprint, Authority.UNAUTHORITATIVE)


def legacy_observe(registry, assets, *, agents, identity, completeness="complete"):
    """Append a full-snapshot observation as written before delta events."""
    return registry.append_event(
        OperationKind.OBSERVE,
        OperationOutcome.SUCCESS,
        before=registry.latest_observation(),
        after=tuple(assets),
        completeness=completeness,
        metadata={
            "observation_agents": list(agents),
            "observation_identity": identity,
            "observation_context": None,
        },
    )


def policy(registry, key, value):
    return registry.append_event(
        OperationKind.ARTIFACT_POLICY,
        OperationOutcome.SUCCESS,
        metadata={"policy_key": key, "policy": value},
    )


def count_decodes(monkeypatch) -> list[int]:
    decoded = [0]
    original = GitRegistry._event_from_dict.__func__

    def counting(cls, value):
        decoded[0] += 1
        return original(cls, value)

    monkeypatch.setattr(GitRegistry, "_event_from_dict", classmethod(counting))
    return decoded


def build_journal(registry):
    install = registry.append_event(OperationKind.INSTALL, OperationOutcome.SUCCESS)
    alpha = evidence(registry, "alpha", "sha256:a1")
    beta = evidence(registry, "beta", "sha256:b1")
    codex = evidence(registry, "gamma", "sha256:g1", agent="codex")
    legacy_observe(registry, (alpha, beta, codex), agents=("claude", "codex"), identity="one")
    policy(registry, "key-a", "enabled")
    alpha2 = evidence(registry, "alpha", "sha256:a2")
    legacy_observe(registry, (alpha2,), agents=("claude",), identity="two", completeness="partial")
    policy(registry, "key-a", "disabled")
    policy(registry, "key-b", "enabled")
    return install, {alpha2.ref.id: alpha2, beta.ref.id: beta, codex.ref.id: codex}


def test_fresh_handle_answers_from_the_index_without_decoding(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        install, expected = build_journal(registry)

    decoded = count_decodes(monkeypatch)
    with GitRegistry(root) as fresh:
        assert fresh.latest_observation() == tuple(expected[key] for key in sorted(expected))
        assert fresh.projected_state().latest_observation == "two"
        assert fresh.latest_policy("key-a") == "disabled"
        assert fresh.latest_policy("key-b") == "enabled"
        assert fresh.latest_policy("key-c") is None
        assert fresh.has_operation(install.operation_id)
        assert not fresh.has_operation("op_missing")
        assert decoded[0] == 0

        assert fresh.event(install.operation_id) == install
        assert decoded[0] == 1
        with pytest.raises(RegistryError, match="unknown operation"):
            fresh.event("op_missing")


def test_complete_observation_drops_only_its_agents(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        _, expected = build_journal(registry)
        beta2 = evidence(registry, "beta", "sha256:b2")
        legacy_observe(registry, (beta2,), agents=("claude",), identity="three")
        codex = next(item for item in expected.values() if item.ref.agent == "codex")

        assert registry.latest_observation() == tuple(
            sorted((beta2, codex), key=lambda item: item.ref.id)
        )


def test_append_uses_the_index_for_sequence_and_identity(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        install, _ = build_journal(registry)
        nxt = registry.append_event(OperationKind.UNINSTALL, OperationOutcome.SUCCESS)
        assert nxt.sequence == len(registry.history())
        with pytest.raises(RegistryError, match="operation identifier"):
            registry.append_event(
                OperationKind.REVERT,
                OperationOutcome.SUCCESS,
                operation_id=install.operation_id,
            )


def index_path(root: Path) -> Path:
    return root / ".git" / "zuat" / "journal-index.json"


def answers(registry):
    return (
        registry.latest_observation(),
        registry.projected_state().latest_observation,
        registry.latest_policy("key-a"),
        registry.latest_policy("key-b"),
        tuple(event.operation_id for event in registry.history()
              if registry.has_operation(event.operation_id)),
    )


def test_index_catches_up_after_another_handle_appends(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        build_journal(registry)
        registry.latest_observation()
        with GitRegistry(root) as other:
            appended = policy(other, "key-a", "inherit")
        decoded = count_decodes(monkeypatch)
        assert registry.latest_policy("key-a") == "inherit"
        assert registry.has_operation(appended.operation_id)
        assert decoded[0] == 1


def test_index_folds_only_documents_it_does_not_cover(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        build_journal(registry)
        stale = index_path(root).read_text(encoding="utf-8")
        policy(registry, "key-b", "disabled")
    index_path(root).write_text(stale, encoding="utf-8")

    decoded = count_decodes(monkeypatch)
    with GitRegistry(root) as fresh:
        assert fresh.latest_policy("key-b") == "disabled"
        assert decoded[0] == 1


@pytest.mark.parametrize(
    "damage",
    [
        lambda path: path.unlink(),
        lambda path: path.write_text("{not json", encoding="utf-8"),
        lambda path: path.write_text(
            path.read_text(encoding="utf-8").replace('"version": 1', '"version": 99'),
            encoding="utf-8",
        ),
        lambda path: path.write_text(
            path.read_text(encoding="utf-8")
            .replace('"document": "0000', '"document": "x000')
            .replace('"observation_identity": "two"', '"observation_identity": "tampered"'),
            encoding="utf-8",
        ),
    ],
    ids=["deleted", "corrupt", "version", "watermark"],
)
def test_damaged_index_is_rebuilt_from_the_journal(tmp_path: Path, damage) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        build_journal(registry)
        expected = answers(registry)
    damage(index_path(root))

    with GitRegistry(root) as fresh:
        assert answers(fresh) == expected
    assert index_path(root).exists()


def test_missing_document_is_rejected_before_index_answers(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        build_journal(registry)
    sorted((root / "operations").glob("*.json"))[1].unlink()
    with pytest.raises(RegistryError, match="not contiguous"):
        with GitRegistry(root) as fresh:
            fresh.latest_observation()


def test_index_stays_out_of_the_projected_tree(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        build_journal(registry)
        tracked = registry.repo.git.ls_files().splitlines()
    assert index_path(root).exists()
    assert not any("journal-index" in path for path in tracked)
    assert not [
        path for path in root.rglob("journal-index.json")
        if ".git" not in path.relative_to(root).parts
    ]


def snapshot(registry):
    return {item.ref.id: item for item in registry.latest_observation()}


def test_changed_asset_yields_a_one_item_delta(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        assets = [evidence(registry, f"s{i}", "sha256:1") for i in range(30)]
        registry.record_observation(assets, agents=("claude",))
        assets[7] = evidence(registry, "s7", "sha256:2")
        event = registry.record_observation(assets, agents=("claude",))

        assert event.kind is OperationKind.OBSERVE_DELTA
        assert event.after == (assets[7],)
        assert [item.fingerprint for item in event.before] == ["sha256:1"]
        assert event.metadata["observation_removed"] == []
        assert snapshot(registry) == {item.ref.id: item for item in assets}
        assert registry.history()[-1].kind is OperationKind.OBSERVE_DELTA


def test_complete_observation_records_removal(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        keep = evidence(registry, "keep", "sha256:k")
        gone = evidence(registry, "gone", "sha256:g")
        registry.record_observation((keep, gone), agents=("claude",))
        event = registry.record_observation((keep,), agents=("claude",))

        assert event.after == ()
        assert event.metadata["observation_removed"] == [gone.ref.id]
        assert event.before == (gone,)
        assert snapshot(registry) == {keep.ref.id: keep}


def test_partial_observation_never_removes(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        keep = evidence(registry, "keep", "sha256:k")
        other = evidence(registry, "other", "sha256:o")
        registry.record_observation((keep, other), agents=("claude",))
        changed = evidence(registry, "keep", "sha256:k2")
        event = registry.record_observation((changed,), agents=("claude",), completeness="partial")

        assert event.metadata["observation_removed"] == []
        assert snapshot(registry) == {changed.ref.id: changed, other.ref.id: other}


def test_mixed_legacy_and_delta_journal_folds_like_full_snapshots(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    with GitRegistry(root) as registry:
        alpha = evidence(registry, "alpha", "sha256:a1")
        beta = evidence(registry, "beta", "sha256:b1")
        codex = evidence(registry, "gamma", "sha256:g1", agent="codex")
        legacy_observe(registry, (alpha, beta, codex), agents=("claude", "codex"), identity="one")
        alpha2 = evidence(registry, "alpha", "sha256:a2")
        registry.record_observation((alpha2,), agents=("claude",))
        delta = registry.record_observation((alpha2, codex), agents=("codex",), completeness="partial")
        expected = {alpha2.ref.id: alpha2, codex.ref.id: codex}

        assert delta.kind is OperationKind.OBSERVE_DELTA
        assert snapshot(registry) == expected
    index_path(root).unlink()
    with GitRegistry(root) as fresh:
        assert snapshot(fresh) == expected


def test_unchanged_observation_still_deduplicates(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        assets = (evidence(registry, "one", "sha256:1"),)
        assert registry.record_observation(assets, agents=("claude",)) is not None
        assert registry.record_observation(assets, agents=("claude",)) is None
        assert len(registry.history()) == 1
