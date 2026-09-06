## Context

See `proposal.md` for motivation. The existing public service already owns observation, lifecycle planning, resolver dispatch, profile persistence, and append-only journaling. Its primitive requests are intentionally expressive, but callers currently have to compose common bulk flows themselves. Shared native documents such as Claude's settings file also make ordering significant when multiple indexed hook fragments are removed.

## Goals / Non-Goals

**Goals:**

- Add a small convenience layer without creating a second lifecycle engine.
- Keep asset selection stable across observation and mutation.
- Recover recorded pre-operation assets even when the source operation did not complete successfully.
- Preserve exact agent-native resolver behavior and profile authority semantics.

**Non-Goals:**

- Expose Git concepts, staging, commits, branches, or registry layout.
- Add a general query language or arbitrary predicates.
- Make `restore_all` an inverse of every possible state transition; `revert` remains the exact inverse of a completed operation.
- Remove unrelated or newly created assets during recovery.

## Decisions

### Use one selector value across Python and CLI adapters

Add an immutable public selector containing a required agent and optional kind, scope, authority, and presence filters. Module-level helpers accept concise keyword arguments and construct the selector; stateful service methods accept the same selector semantics. This avoids proliferating operation-specific filter models while keeping validation in one place.

An unstructured mapping was considered, but rejected because typoed field names and stringly typed authority values would weaken the public contract.

### Hold one registry transaction across selection and mutation

Bulk helpers enter the existing re-entrant registry operation boundary, observe native state, select evidence, and invoke the existing lifecycle path before releasing the boundary. The lifecycle operation may re-observe for verification, but no competing Zuat process can interleave between selection and mutation.

Calling `status()` and then a public mutation as two independent steps was rejected because selected locators can drift between those calls.

### Delegate adopt-all and uninstall-all to primitive lifecycle operations

After stable selection, adopt-all constructs install inputs from observed native sources and delegates to install; uninstall-all delegates selected references to uninstall. Helper results relabel the public operation name while retaining normal status, evidence, diagnostics, and operation identifiers. Empty selection is a successful no-op and has no lifecycle journal entry.

For indexed fragments in a shared document, uninstall planning orders removals from the highest index to the lowest within each collection. This retains the existing resolver contract while preventing earlier removals from shifting later locators.

### Define restore-all as presence recovery, not exact inversion

Restore-all targets the source operation's `before` evidence entries that were present and match the selector. It compares those entries with fresh observation and repairs missing content, displaced content when forced, and profile-authority mismatches. It never removes a current asset merely because that asset was absent from the source operation's `before` state; callers use `revert` for exact inversion.

Archived payloads remain the restoration source. A temporary desired-state profile feeds the existing resolver planners and materializers, while projection into the real profile preserves each evidence entry's recorded authoritative or unauthoritative status. A successful mutation appends a distinct restore domain event carrying the source operation identifier. This design supports partial, failed, and interrupted source events because it relies on recorded `before` evidence rather than requiring a successful outcome.

Delegating only to `revert` was rejected because revert intentionally accepts completed operations and computes their full inverse, which cannot recover a partially applied deletion safely.

### Keep command handlers as adapters

The CLI adds list-assets, adopt-all, uninstall-all, and restore-all commands. Each parses selector options and calls only module-level functions from `zuat.pub`; no command imports resolver, registry, or utility modules. Click remains isolated behind the existing optional CLI extra.

## Risks / Trade-offs

- [A native process edits a selected asset while Zuat holds its registry lock] → Re-observe after materialization and report partial failure if verification differs; the lock serializes Zuat instances but cannot lock third-party agent processes.
- [Bulk indexed removals corrupt shared documents through locator shifts] → Sort removals descending within each indexed native collection and test preservation of non-selected fragments.
- [Archived payload for a recovery target is unavailable] → Reject before materialization with an actionable diagnostic and leave profile/native state unchanged.
- [The helper surface hides too much control] → Return the same detailed operation result and evidence types as primitive operations, while keeping primitive APIs available.

## Migration Plan

This is additive for Python and CLI callers. Introduce the selector and service behavior behind red-first tests, export module-level helpers, then add CLI adapters. Existing primitive operations and journal records require no migration. Rollback removes the additive commands and functions; previously written restore events remain valid history records.
