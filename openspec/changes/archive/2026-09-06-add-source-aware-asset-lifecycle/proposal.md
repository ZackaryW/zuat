## Why

Zuat already supplies recoverable asset operations, but consumers such as ZPP cannot yet inspect an installed skill or hook against its packaged source through the public interface or explicitly update it with source-aware outcomes. Ordinary project assets also lack the installation-context isolation already present for plugins, preventing safe reuse of one registry across projects.

## What Changes

- Add a public, typed, source-aware inspection operation for independently managed skills and hooks. Distinguish absence, current content, an available source update, local modification, unowned content, unsupported requests, and unresolved inspection without claiming ownership from a matching name or content.
- Add a focused public update operation that revalidates its target, snapshots the actual previous state, replaces only the selected asset, verifies the outcome, and returns a domain operation reference usable for restoration. Reuse existing install, remove, journal, profile and restore operations rather than expose reconciliation plans.
- **BREAKING** Bind ordinary project skill/hook identities, ownership, projections, history, recovery and restoration to the selected project context. Preserve user-scoped sharing and existing plugin pointer isolation; reject ambiguous earlier project records without automatic conversion or deletion.
- Keep independently verified asset inspection usable when unrelated plugin discovery fails, without treating unknown provider state as absence or permitting plugin content to enter global snapshots.
- Preserve Zuat's explicit adoption/force model. Consumer-specific repair policy, old agent-router ownership handover and `.gitignore` policy remain outside this change.

## Capabilities

### New Capabilities

- `source-aware-asset-lifecycle`: Public source-aware skill/hook inspection and verified, rollback-capable targeted updates.
- `project-asset-isolation`: Independent ordinary asset identity, observation, ownership, profiles and recovery for multiple projects sharing one registry.

### Modified Capabilities

None. The existing three plugin capabilities remain authoritative and unchanged. The active foundation change is historical implementation context, not a source of additional requirements to promote here.

## Impact

- `src/zuat/pub/`: typed inspection results, thin source-aware inspection/update entry points and explicit runtime context on relevant helpers.
- `src/zuat/specs/`: agent-owned target inspection, scope validation, shared-hook identity and targeted update verification.
- `src/zuat/utils/` and `gitcore/`: reusable inspection mechanics and context-aware ordinary-asset persistence integrated with existing append-only operations.
- Tests and documentation: failing-first state-transition tests, two-project isolation, restart/restore and packaged Python-only usage.
- No agent-router dependency, aliases or legacy readers. No new native plugin capabilities, broad CLI expansion, or changes to the ZPP repository. Actual ZPP integration and acceptance remain a subsequent change.
