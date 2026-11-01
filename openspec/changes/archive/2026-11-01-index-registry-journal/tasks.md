# Tasks

## 1. Shared fold and journal index

- [x] 1.1 Add tests in a new `tests/gitcore/test_journal_index.py`. Cover: for a journal built from install, artifact-policy, and full-snapshot observe events, index answers (latest observation, identity, policy per key, operation existence and lookup, next sequence) equal a full-replay fold, and a fresh handle answers them without decoding unrequested documents. Verify they fail (`uv run --all-extras pytest tests/gitcore/test_journal_index.py`)
- [x] 1.2 Add `src/zuat/gitcore/journal_index.py` with the single `fold(state, event)` (legacy `observe` retention, `artifact-policy`, operation map, watermark) and index load/persist at `control_root/journal-index.json` with atomic replace. Verify the 1.1 fold-equivalence tests pass
- [x] 1.3 Wire the index into `GitRegistry`: validation by name listing (current / stale catch-up / rebuild, gap rejection), maintenance in `append_event`, and `latest_observation`, `projected_state`, `record_observation` dedup, `event`, plus new `has_operation` and `latest_policy` served from it. Verify the 1.1 tests pass, including the no-decode assertions

## 2. Self-healing index

- [x] 2.1 Add tests: catch-up after another handle appends, rebuild after the index file is deleted, corrupted, version-mismatched, or has a stale watermark, a missing operation document still raises the sequence error, and no index file appears in the projected tree or its commits. Verify they fail first where behavior is missing, then pass

## 3. Delta observation events

- [x] 3.1 Add tests: one changed asset in a complete observation yields a one-item `observe-delta`; removal in a complete observation records the removed id and prior evidence; a partial observation records no removal and keeps the asset; a mixed legacy-then-delta journal folds to the same snapshot as equivalent full snapshots; dedup of an unchanged observation still appends nothing; `history()` reports `observe-delta`. Verify they fail
- [x] 3.2 Add `OperationKind.OBSERVE_DELTA`, compute deltas in `record_observation` via the legacy rule plus diff (`after`, `before`, `metadata.observation_removed`), and fold `observe-delta` in `fold`. Verify the 3.1 tests and existing `tests/gitcore/test_observation.py` and `test_projection.py` pass
- [x] 3.3 Update every remaining `OperationKind.OBSERVE` check in `src/` so both kinds count as observations where appropriate. Verify with `grep` and the full gitcore suite

## 4. Consumers off history scans

- [x] 4.1 Switch `pub/artifacts._policy` to `latest_policy`, and the "published?" scans in `pub/plugins` and `pub/assets` to `has_operation`. Verify `tests/pub/plugins/test_artifacts.py`, `tests/pub/plugins/`, and `tests/pub/assets/` pass

## 5. Documentation and integration

- [x] 5.1 Document the derived index, delta observations, and the downgrade restriction in `README.md`. Verify the section is accurate against the implementation
- [x] 5.2 Run the full suite (`uv run --all-extras pytest`) and Behave if present. Verify they pass
- [x] 5.3 Against a copy of the real registry: time a fresh-handle `inspect_asset` and one-skill `install` before and after, confirm that the next observation's document is delta-sized, and record the results in design.md

## Workflow follow-up

- Commit with zmem-author-commits, then sync and archive the change.
- Bump Powerspec's pinned `zuat` revision and re-measure `pspec init --agent <new-agent>`.
