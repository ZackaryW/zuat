# Design

## Context

The previous change (`2026-11-01-cache-registry-journal-reads`) made repeated reads within one `GitRegistry` handle cheap. Every new handle still decodes the whole journal once, though, and `zuat.pub` opens a handle per call. Apart from the public `history()`, every journal consumer needs a small answer:

| Consumer | Needs |
|---|---|
| `append_event` | last sequence; whether the operation id is new |
| `event(id)`, `pub/recovery`, `pub/assets` | one event by id |
| `pub/plugins`, `pub/assets` "published?" | whether an operation id exists |
| `projected_state`, `record_observation` | latest observation identity |
| `latest_observation` (`pub/observations`) | folded current observation |
| `pub/artifacts._policy` | latest `artifact-policy` per key |

OBSERVE events currently store `before = latest_observation()` (every agent's full snapshot) and `after` = the full current snapshot. OBSERVE events can't be reverted (`pub/recovery` rejects them), so only folding and history display read their evidence.

## Goals / Non-Goals

**Goals:**
- No journal decoding on the hot path of a fresh handle while the index is current.
- Observation events sized to what changed.
- Identical folded results and deduplication for legacy and new journals.

**Non-Goals:**
- Rewriting or compacting existing journal documents. History stays append-only, and old full-snapshot events keep their size.
- Making the public full `history()` cheaper. It is the one genuine full reader.
- Sharing the index between registries or keeping it in the projected tree.

## Decisions

### 1. Index location and shape
`<git_dir>/zuat/journal-index.json`, next to the existing recovery marker and native state under `control_root`. Because it lives inside `.git`, it is never committed or projected, so it leaves the browsable-tree requirement unchanged. Shape:

```json
{
  "version": 1,
  "sequence": 74,
  "document": "000000000074-op_....json",
  "operations": {"op_...": "000000000074-op_....json"},
  "observation_identity": "<sha256>|null",
  "observation": [<evidence dict>, ...],
  "policies": {"<policy_key>": "<policy>"}
}
```

`observation` is the folded snapshot as evidence dicts: references, fingerprints and native evidence, never asset payloads.
*Alternative:* SQLite. Rejected because one small JSON document is enough at this size, adds no dependency, and matches the rest of the registry's style.

### 2. Validation without decoding
On first use per handle, list `operations/` names only and parse the 12-digit sequence prefix of each name. This catches gaps (a `RegistryError`, same as today) without decoding anything. Then:
- `len(names) == sequence` and `names[-1] == document`: current, use as-is.
- `len(names) > sequence` and `names[sequence-1] == document`: stale, decode and fold only `names[sequence:]`.
- Anything else (missing, unreadable, unknown `version`, mismatch): rebuild by folding every document.

The handle keeps the validated index in memory and re-checks the listing on each query. A listing costs one `scandir`.

### 3. Maintenance on append
`append_event` already holds the decision point. After the operation document is written and committed, it folds the new event into the in-memory index and atomically replaces the index file. A crash between the document write and the index write leaves a stale index, which the next read catches up (Decision 2). Readers that caught up or rebuilt also persist the index through atomic replace. Concurrent writers can only produce valid, self-validating indexes, so the last writer wins without risk.

### 4. One fold function for both index and deltas
A single `fold(state, event)` applies:
- legacy `observe`: the existing retention rule (a complete observation drops retained evidence for its agents and matching context, then applies `after`).
- `observe-delta`: drop `metadata.observation_removed` ids, then apply `after`.
- `artifact-policy`: `policies[key] = policy`.
- every event: `operations[id] = document`, plus the watermark.

`latest_observation()`, `projected_state()`, and dedup in `record_observation` read from it.

### 5. Delta computation reuses the legacy rule
`record_observation` computes the next folded snapshot by applying the *legacy* retention rule to the current index snapshot with the full observed set, then diffs:
- `after` = evidence that is new or differs (by serialized dict)
- `observation_removed` = ids present before and absent after
- `before` = prior evidence for changed and removed ids

Folding the delta is then equivalent to folding the full snapshot by construction, including partial and indeterminate observations (the legacy rule never removes for them) and context-scoped retention. `observation_identity` is still hashed over the full observed set, so deduplication is unchanged.

### 6. Distinct kind as the format marker
Add `OperationKind.OBSERVE_DELTA = "observe-delta"`. Earlier Zuat versions fail `OperationKind(...)` decoding with `RegistryError("journal event is invalid")` rather than folding a delta as a full snapshot and silently dropping unchanged assets.
*Alternative:* keep `observe` and add a `format` field. Rejected because old readers ignore unknown fields and would misread the journal without any error.

### 7. Consumers move to index queries
Add `GitRegistry` methods `has_operation(id)`, `latest_policy(key)`, and `next_sequence` (used internally). `event(id)` resolves the document through the index and decodes only that file, using the per-file cache from the previous change. `pub/artifacts`, `pub/plugins`, and `pub/assets` stop scanning `history()`.

## Risks / Trade-offs

- [Downgrade breaks] → After the first delta event, earlier Zuat versions refuse the registry loudly. Recovery is upgrading Zuat. Documented in the README; Powerspec pins the new version in the same rollout.
- [Index drift hides a bug] → The index is disposable. Tests assert that index answers equal a full-replay fold for legacy, mixed, and delta journals, and that deleting the index changes no answers.
- [First open of a large legacy registry still decodes everything once] → One-time cost per registry, after which the persisted index makes later handles cheap.
- [Old snapshots keep their size] → Accepted, since history is append-only. New growth is delta-sized.

## Migration Plan

No explicit migration step. The first read by the new version builds the index from the existing journal, and the next changed observation appends the first `observe-delta`. Rollback before any delta event exists: the older version ignores the index file. Rollback after: not supported. Upgrade instead.

## Results

Measured on a copy of a real 74-operation registry with an empty home. "Pinned" is the Zuat revision Powerspec currently pins (`1c2fb36`):

| Step | Pinned | This change |
|---|---|---|
| One-skill codex install | 15.9s | 0.28s |
| Fresh-handle inspect after it | 0.20s | 0.01s |
| Follow-up install | - | 0.23s |
| Observation document per changed skill | about 150 KB (full snapshot) | 1.5 KB (`observe-delta`) |

The first delta in that copy was 131 KB because the empty home made the complete Codex observation remove 81 assets, so the delta correctly carried their prior evidence. pytest: 733 passed, 2 skipped. Behave: 4 scenarios passed.
