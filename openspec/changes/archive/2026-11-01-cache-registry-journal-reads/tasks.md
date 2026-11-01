# Tasks

## 1. Incremental history reads

- [x] 1.1 Add tests in `tests/gitcore/test_history.py`: repeated reads skip decoding, appends decode only the new document, an append from a second handle is visible, and a removed document raises the sequence error. Verify they fail before the change (`uv run pytest tests/gitcore/test_history.py`)
- [x] 1.2 Add the per-handle decoded-event cache to `GitRegistry.history()`, keyed by document name with a `(st_mtime_ns, st_size, st_ino)` signature and guarded by `self._mutex`. Verify the 1.1 tests pass

## 2. Catalog lookup without replay

- [x] 2.1 Add a test showing `find_asset_ref` resolves known identifiers, rejects unknown ones, and does not read the journal. Verify it fails before the change
- [x] 2.2 Make `find_asset_ref` scan `catalog.json` directly. Verify the 2.1 test passes

## 3. Integration

- [x] 3.1 Run the full suite (`uv run pytest`) and verify it passes
- [x] 3.2 Re-run the one-skill install profile against a copy of a real registry and record the before/after timing in the change summary

## Workflow follow-up

- Bump Powerspec's pinned `zuat` revision after this lands, then re-measure `pspec init --agent <new-agent>`.
- Archive the change after review.
