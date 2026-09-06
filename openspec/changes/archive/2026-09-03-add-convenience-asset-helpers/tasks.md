## 1. Public Selection Contract

- [x] 1.1 Add red pytest coverage for deterministic asset filtering by agent, kind, scope, authority, and presence; verify the focused tests fail because the selector/helper surface is absent
- [x] 1.2 Implement and export the immutable selector plus `list_assets`; verify the focused selection tests pass without importing Click

## 2. Bulk Lifecycle Helpers

- [x] 2.1 Add red pytest coverage for adopt-all, uninstall-all, empty selections, transaction stability, and shared-document preservation; verify failures identify missing helper behavior
- [x] 2.2 Implement adopt-all and uninstall-all as transaction-held adapters over primitive lifecycle operations; verify the focused helper tests pass
- [x] 2.3 Make indexed shared-document removals order-safe; verify a bulk hook test removes every selected hook while preserving non-selected hooks and settings

## 3. Recovery Helper

- [x] 3.1 Add red pytest coverage for successful-operation recovery, partial/interrupted recovery, authority preservation, conflict rejection, and forced displacement archival; verify failures identify missing restore-all behavior
- [x] 3.2 Implement journaled presence recovery from archived pre-operation evidence without removing unrelated assets; verify the focused recovery tests pass

## 4. CLI Adapters

- [x] 4.1 Add red pytest coverage proving helper CLI commands route only through `zuat.pub`, preserve structured output, and map status to exit codes; verify the focused tests fail before command implementation
- [x] 4.2 Implement list-assets, adopt-all, uninstall-all, and restore-all CLI adapters; verify the focused CLI tests pass and base-package import still works without Click

## 5. End-to-End Verification

- [x] 5.1 Add a Behave scenario only for partial-operation restore across journal, resolver, profile, and native storage; verify it fails for the intended missing behavior before implementation and passes afterward
- [x] 5.2 Run the complete pytest and Behave suites and verify no regressions
- [x] 5.3 Run strict OpenSpec validation for `add-convenience-asset-helpers` and verify every artifact and task is coherent
