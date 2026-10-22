# Proposal

## Why

Shared-hook reconciliation can lose usable ownership evidence when native declarations differ from a valid receipt, even when the installed declarations already exactly match the requested source. A separate install path can then append new callbacks beside unresolved existing ones and report success, so consumers need consistent target identification and a recoverable way to repair stale ownership without editing private receipts.

## What Changes

- Separate shared-hook target identification, recorded ownership, actual content, and source equality. Resolve uniquely identifiable groups without treating content equality as authority or guessing from array positions.
- Extend existing explicit forced `update_asset` reconciliation to repair a valid but stale receipt when the uniquely selected native group already matches the source; preserve native bytes, record the ownership transition, and support restoration and interrupted-operation recovery.
- Preserve relative declaration order as evidence. Reordering does not erase receipt identity or authorize automatic normalization; actual order changes remain conflicts unless an agent contract explicitly establishes equivalence.
- **BREAKING behavior tightening:** Apply consistent ambiguity checks to source-driven hook installation and adoption, rejecting unresolved identities that previously allowed appending potentially duplicate callbacks. Preserve adoption of uniquely matching unowned content and installation into verified absence; public signatures remain unchanged.
- Document consumer decisions using existing public inspection/install/update APIs, including a Powerspec follow-up for exact-match adoption, ambiguity handling, explicit repair authorization, and dependency pin updates.
- **BREAKING behavior tightening (confirmed during implementation):** Forced installs with explicit array locators follow verified ownership identity instead of moving hooks back to recorded positions or selecting duplicate candidates by index.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `source-aware-asset-lifecycle`: Identify shared-hook groups from baseline/source evidence, retain distinct ownership and content facts, and verify recoverable receipt-only forced reconciliation.
- `agent-asset-resolution`: Require source-driven shared-hook install/adoption to establish an unambiguous target and reject ambiguous or overlapping declarations before native mutation.

## Impact

- ZuAT public orchestration in `src/zuat/pub/assets.py` and `lifecycle.py`, inspection results in `models.py`, native resolver support and shared-hook mechanics, and existing recovery/projection paths.
- Existing public method signatures and classification names remain; explicit forced update gains receipt-repair behavior and additive result evidence. Invalid receipts, uncertain providers, ambiguous identities, and cross-project targets remain non-authorizing.
- Tests in `tests/pub/assets`, targeted process-recovery tests, and README/example guidance. No new runtime dependency, CLI command, private-state migration, global hook rewrite, or release publication is included.
- Powerspec implementation and repair of the user's live hooks are follow-up actions, not part of this ZuAT planning change. Existing untracked `openspec/.pspec/` configuration remains untouched.
