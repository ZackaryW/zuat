# Proposal

## Why

Registry reads still depend on decoding the operation journal. Every new `GitRegistry` handle (one per `zuat.pub` call) decodes the full history at least once, just to learn the next sequence number, find one operation, read the latest observation identity, fold the current observation, or find the latest artifact policy. The journal is also oversized: each observation event stores the entire previous snapshot as `before` and the entire current snapshot as `after`, so a 74-operation registry takes up 7 MB, with about 170 KB per observation. Decoding cost and disk use both grow faster than the number of operations, which makes bootstrapping agents in downstream tools like Powerspec slower over time.

## What Changes

- **Derived journal index.** Zuat maintains a private, disposable index of the journal under its Git control directory. It holds a watermark (the last sequence and document name), an operation-id-to-document map, the latest observation identity, the folded latest observation snapshot, and the latest artifact policy per key. Every append updates it under the registry lock.
- **Index-backed queries.** Next sequence, operation lookup by id, operation existence, latest observation identity, latest observation, and artifact policy answer from the index without decoding operation documents. Full domain history is still available and still read from the journal.
- **Self-validating and rebuildable.** Each read compares the watermark with a listing of `operations/` (names only). A stale index catches up by folding only the new documents. A mismatched, missing, or corrupt index is rebuilt from the journal. The index is never a source of truth.
- **BREAKING (on-disk format): observation deltas.** New observations append an `observe-delta` event that records only added or changed evidence (`after`), the prior evidence of changed or removed assets (`before`), and the identifiers of removed assets. Older `observe` events with full snapshots remain readable and fold identically. Older Zuat versions reject the new event kind with a registry error instead of silently misreading the journal.
- Observation deduplication, completeness semantics (partial or indeterminate observations never imply deletion), and per-agent/per-context retention are unchanged.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `git-profile-registry`: adds requirements for delta observation events, legacy observation compatibility, the derived journal index, and its self-healing validation. Existing requirements are unchanged.

## Impact

- `src/zuat/gitcore/repository.py`: `append_event`, `record_observation`, `latest_observation`, `projected_state`, `event`, plus a new index module under `src/zuat/gitcore/`.
- `src/zuat/gitcore/models.py`: new `OperationKind.OBSERVE_DELTA`.
- `src/zuat/pub/artifacts.py`, `pub/plugins.py`, `pub/assets.py`: move their history scans to the index-backed queries.
- Public `history()` output: new observation events show `kind: "observe-delta"` with delta-sized `before`/`after`.
- Compatibility: registries written by this version cannot be read by earlier Zuat versions once a delta event exists. Powerspec must pin this version.
