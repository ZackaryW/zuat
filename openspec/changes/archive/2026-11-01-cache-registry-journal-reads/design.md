# Design

## Context

`GitRegistry` stores one immutable JSON document per operation under `operations/`. These are written through `_atomic_json`, which does a temp write followed by `os.replace`. `history()` globs and decodes all of them on every call. `projected_state()`, `latest_observation()`, `record_observation()`, `append_event()`, and `event()` all call `history()`. `find_asset_ref()` calls `projected_state()` only to scan the catalog. One `Zuat` service owns one `GitRegistry` for its lifetime, and `zuat.pub` functions open a short-lived service per call.

Profiling a one-skill install against a 75-operation registry: 82 `history()` calls (63 of them through `find_asset_ref`), about 6,100 event decodes, and about 516,000 evidence decodes. Plugin-evidence validation (`clean_evidence`) accounts for most of the time.

## Goals / Non-Goals

**Goals:**
- Make repeated history reads within one registry handle cost a directory listing plus `stat` calls, with no re-decoding.
- Remove journal replay from asset-reference lookup.

**Non-Goals:**
- Cross-process or on-disk caching of decoded events.
- Compacting or snapshotting the journal. Cold-start cost still grows with history, and that is left to a later change.
- Changing the journal format, the public `zuat.pub` contracts, or Powerspec's per-skill call pattern.

## Decisions

**Per-handle decoded-event cache keyed by file identity.** `GitRegistry` keeps `dict[str, tuple[signature, JournalEvent]]`, where the key is the document name and `signature = (st_mtime_ns, st_size, st_ino)`. Each `history()` call still globs and sorts `operations/*.json` and stats each entry. It decodes only when the signature differs, then drops entries whose files no longer exist. The contiguous-sequence check runs on the assembled tuple every time.
- *Why include the inode:* `os.replace` creates a new inode, so a rewrite is detected even when mtime granularity is coarse and the size happens to match.
- *Alternative: cache the whole tuple and invalidate on our own writes.* Rejected because it would miss appends from other handles or processes, such as `_recover_interrupted_operation` in another handle or a concurrent CLI run after the lock is released.
- *Alternative: key on directory mtime.* Rejected because directory mtime is unreliable across filesystems and would force a full re-decode on any change.

**Shared immutable events.** `JournalEvent` and `AssetEvidence` are frozen slotted dataclasses, and nothing in `src/` mutates `event.metadata` or `evidence.evidence`. Returning the same cached instances is safe and avoids defensive copies.

**`find_asset_ref` reads the catalog.** It scans `_read_catalog().values()` through `_asset_ref_from_dict` and keeps the same `RegistryError` for unknown identifiers. `projected_state().catalog` is built from the same file, so the results are identical.

**Thread safety.** Cache updates run under the existing `self._mutex` (an RLock), so concurrent readers on one handle cannot interleave partial updates.

## Risks / Trade-offs

- [A document is rewritten in place with identical mtime, size, and inode] → Zuat never rewrites operation documents (the journal is append-only) and always replaces them atomically. Manual edits would also break other invariants. Acceptable.
- [The cache holds decoded history in memory for the handle's lifetime] → Bounded by journal size, which is already fully materialized on every read today. No regression.
- [Cold start is still O(history)] → Each short-lived `pub` call still decodes once. That is about 0.6s at 75 operations today, down from about 50 decodes per call. Compaction is out of scope.

## Results

Measured on a copy of a real 75-operation registry with an empty home: a one-skill Codex install via `zuat.pub.install` dropped from 15.6s to 0.47s. Inspection stayed at about 0.25s. The full suite passes (716 passed, 2 skipped).
