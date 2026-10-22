# Proposal

## Why

Powerspec integration testing against ZuAT 0.1.2 found that reinstalling deleted owned hooks can report success without restoring the declarations. The shared mapping containment predicate skips missing event keys, while older install checks disagree with semantic absence inspection.

## What Changes

- Require every requested mapping key and list member to be present for fragment containment.
- Permit reinstalling a semantically verified absent hook group with an existing valid receipt, without force or positional replacement.
- Verify recreated native content before reporting successful installation.
- Add an optional receipt-only update guard so consumers can reject concurrent content changes inside the provider operation instead of granting unrestricted forced replacement.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-asset-resolution`: Clarify verified installation after native hooks disappear and constrain explicitly requested receipt-only reconciliation.

## Impact

Shared document containment, hook preflight/materialization, focused helper and public lifecycle tests, and consumer documentation. Powerspec's pending `reconcile-zuat-hook-provisioning` change consumes the correction.
