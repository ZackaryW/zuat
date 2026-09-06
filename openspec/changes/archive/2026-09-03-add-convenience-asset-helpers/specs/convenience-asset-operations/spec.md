## Purpose

Provide concise, transaction-safe ways to inspect, adopt, remove, and recover groups of coding-agent assets without exposing registry or Git mechanics.

## ADDED Requirements

### Requirement: Public asset selection
Zuat SHALL expose a public asset selector that can filter observed evidence by agent and optionally by asset kind, scope, authority, and presence. Selection results SHALL be deterministic and SHALL contain the same evidence values returned by the regular status operation.

#### Scenario: List one agent's hooks
- **WHEN** a caller lists present hook assets for Claude
- **THEN** Zuat returns only Claude hook evidence in deterministic order

#### Scenario: List unauthoritative skills
- **WHEN** a caller lists present unauthoritative skill assets for an agent
- **THEN** Zuat excludes authoritative, missing, and non-skill evidence

### Requirement: Transaction-safe bulk helpers
Zuat SHALL expose one-call helpers for adopting all selected present assets and uninstalling all selected present assets. Each helper SHALL select and mutate under one registry transaction, SHALL use the registered agent resolver, and SHALL return the normal public operation result without exposing Git primitives.

#### Scenario: Adopt every selected skill
- **WHEN** a caller adopts all present skills matching an agent and scope
- **THEN** Zuat records those skills as authoritative in the active profile without requiring the caller to construct asset references

#### Scenario: Uninstall every selected hook
- **WHEN** a caller force-uninstalls all hooks matching an agent and scope
- **THEN** Zuat removes every selected hook, preserves non-selected content in shared native documents, and records one append-only lifecycle operation

#### Scenario: Empty bulk selection
- **WHEN** no present assets match an adopt-all or uninstall-all selector
- **THEN** Zuat returns a successful no-op result and does not append a lifecycle mutation

### Requirement: Convergent operation recovery
Zuat SHALL expose a restore-all helper that uses an operation's recorded pre-operation evidence as its recovery target. The helper SHALL restore matching assets that were present before the referenced operation, SHALL support successful, partial, failed, and interrupted operation records, and SHALL not remove unrelated current assets.

#### Scenario: Restore deleted assets from a successful operation
- **WHEN** a caller restores all assets from a completed uninstall operation
- **THEN** Zuat recreates each missing selected asset from archived evidence and preserves its recorded authority state

#### Scenario: Recover a partial operation
- **WHEN** a caller restores all assets from a partial or interrupted operation
- **THEN** Zuat observes current native state and repairs only missing, displaced, or authority-mismatched selected assets

#### Scenario: Existing content conflicts with recovery evidence
- **WHEN** a selected locator contains content whose fingerprint differs from the recorded pre-operation evidence and force is not enabled
- **THEN** Zuat rejects the restore without changing native state or the active profile

#### Scenario: Forced recovery archives displaced content
- **WHEN** a caller enables force while restoring over conflicting current content
- **THEN** Zuat archives the displaced evidence, restores the recorded content, and appends a restore operation referencing the source operation

### Requirement: Public and CLI parity
The helper operations SHALL be available from the supported Python surface and as thin CLI adapters. CLI handlers SHALL call only the public package interface and SHALL preserve structured result and exit-status conventions.

#### Scenario: Invoke a bulk helper from the CLI
- **WHEN** a user invokes a helper command with selector options
- **THEN** the CLI forwards the request through the public interface and renders its operation result without importing implementation modules

### Requirement: Append-only helper history
Every helper mutation SHALL be represented as a forward-appended domain operation. Zuat SHALL keep internal commits, refs, indexes, and hashes hidden from public helper inputs and outputs.

#### Scenario: Restore is recorded as a forward operation
- **WHEN** restore-all changes native or authoritative state
- **THEN** history contains a new restore operation linked to the source operation and no historical operation is rewritten or deleted
