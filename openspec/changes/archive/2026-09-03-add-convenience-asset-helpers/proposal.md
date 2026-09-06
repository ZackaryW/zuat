## Why

Zuat's transaction API can express bulk asset workflows, but common operations currently require callers to observe state, filter evidence, construct references, and invoke a second mutation. That ceremony is inconvenient and creates an avoidable race between selection and mutation.

## What Changes

- Add a small public selector model for filtering assets by agent, kind, scope, authority, and presence.
- Add `list_assets`, `adopt_all`, `uninstall_all`, and `restore_all` helpers to the public Python surface.
- Perform helper selection and any resulting mutation under one registry transaction while preserving the existing append-only operation journal.
- Make `restore_all` converge recorded pre-operation assets back into place, including recovery from partial or interrupted operations, without removing unrelated current assets.
- Add equivalent thin CLI commands whose handlers route exclusively through `zuat.pub`.
- Cover the helpers with red-first pytest tests and reserve Behave for genuinely cross-component workflows.

## Capabilities

### New Capabilities

- `convenience-asset-operations`: Transaction-safe asset selection and one-call bulk list, adopt, uninstall, and recovery helpers for Python and CLI callers.

### Modified Capabilities

None. The canonical specification catalog is currently empty; this capability composes the public command surface and append-only registry behavior defined by the active foundation change.

## Impact

- Public API: `zuat.pub` functions, `Zuat` service methods, and exported selector/result models.
- CLI: new helper commands implemented as thin adapters over `zuat.pub`.
- Core behavior: selector evaluation, bulk removal ordering for shared documents, and a journaled restore operation.
- Tests: focused service and CLI pytest coverage, plus a Behave scenario only where end-to-end recovery crosses resolver, registry, and native agent storage.
