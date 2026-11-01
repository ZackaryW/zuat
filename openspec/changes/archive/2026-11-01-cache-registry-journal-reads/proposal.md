# Proposal

## Why

Each journal read re-parses every operation document. A single non-forced skill install against a 75-operation registry calls `GitRegistry.history()` 82 times and takes about 20 seconds (50s under a profiler), almost all of it spent in `_event_from_dict`/`clean_evidence`. Callers such as Powerspec install one skill per call, so bootstrapping a new agent with 20 skills takes several minutes. The cost also grows with every new operation, so an older registry is slower than a new one.

## What Changes

- Within one registry handle, `GitRegistry.history()` parses each operation document only once while that document is unchanged. Later reads parse only the documents that were added or modified.
- The cache is checked against the `operations/` directory on every read, so documents appended by other processes or other handles still show up. Sequence validation still runs on every read.
- `GitRegistry.find_asset_ref()` reads `catalog.json` directly instead of building the full `ProjectedState`, which replays the journal.
- No change to the journal format, public API, or recorded history.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `git-profile-registry`: adds a requirement that journal reads stay incremental within a registry handle and stay consistent with documents appended elsewhere.

## Impact

- `src/zuat/gitcore/repository.py`: `history()`, `find_asset_ref()`, and the new per-handle event cache.
- Tests under `tests/gitcore/` cover cache reuse, detection of external appends, and catalog lookup.
- Downstream callers (Powerspec `pspec init` / `pspec upgrade`) get faster with no code change.
