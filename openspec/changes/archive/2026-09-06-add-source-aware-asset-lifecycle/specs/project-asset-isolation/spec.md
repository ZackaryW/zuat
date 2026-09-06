## Purpose

Keep ordinary skills and hooks independently addressable and recoverable across projects that share one Zuat registry, without fragmenting user-scoped state.

## ADDED Requirements

### Requirement: Installation identity includes project context

Project-scoped skills and hooks SHALL retain their selected project context independently of agent, kind, name and content. Equal names and content in different projects SHALL NOT share asset identity, ownership or storage projections. Equivalent normalized references to one project SHALL identify the same context. User-scoped installations SHALL remain shared for the same agent home regardless of the selected project. Unsupported project scopes SHALL remain unsupported.

#### Scenario: Equal assets in two projects

- **WHEN** projects A and B contain the same named skill and hook with identical content under one registry
- **THEN** each project has independently addressable asset references, ownership and stored content

#### Scenario: Equivalent project path and shared user asset

- **WHEN** a caller reopens the same project through an equivalent normalized path or changes the selected project while inspecting a user-scoped asset
- **THEN** the equivalent project keeps its identity and the user-scoped asset is not duplicated by project selection

### Requirement: Observation and selection preserve other contexts

Observing, listing, adopting, installing, updating or removing assets in a selected project SHALL NOT reinterpret another project's assets as absent or change its ownership, profiles or native state. Explicit references from a different project SHALL be rejected rather than rebound to the selected project. Missing required project context SHALL fail before mutation. Independent project coverage SHALL remain distinguishable from shared user coverage.

#### Scenario: Observe an empty second project

- **WHEN** project A has registered assets and project B is observed with no corresponding assets
- **THEN** A's observations and ownership remain intact without recording its assets as removed

#### Scenario: Foreign reference or missing context

- **WHEN** an operation addresses A's project asset while configured for B or without a project root
- **THEN** it rejects before native writes and leaves both projects unchanged

### Requirement: Profiles and restoration respect installation context

Profiles, operation history and recovery evidence SHALL preserve project association for ordinary assets. Profile application, removal, revert and restoration SHALL operate only on assets applicable to the explicit runtime context plus intentionally selected shared user assets. Other contexts stored in a profile SHALL be preserved, not applied to the selected project. An explicitly selected cross-context operation SHALL fail preflight. Restoring or recovering project operations SHALL require their original context and SHALL NOT infer it from the incidental working directory.

#### Scenario: Update A and restore after restart

- **WHEN** an asset in A is updated, the service restarts, and its operation is restored with A selected
- **THEN** A's prior content and authority are restored with forward history while B's equal-named asset remains unchanged

#### Scenario: Mixed-context profile

- **WHEN** a profile contains assets for A and B and is applied with A selected
- **THEN** only applicable selected assets are reconciled, B's records are retained, and the result does not claim B was verified or applied

#### Scenario: Recovery in the wrong project

- **WHEN** a pending project-A operation is reopened with project B selected
- **THEN** recovery reports the missing original context and retains the pending evidence without mutating either project

### Requirement: Ambiguous earlier project state is not silently adopted

Earlier ordinary project records lacking sufficient context SHALL NOT be attributed to a project by guessing from names, current directory or selected profile. Zuat SHALL reject incompatible ambiguous state with actionable fresh-registry guidance, without deleting, rewriting or automatically converting prior history. Valid user-scoped and plugin-context behavior SHALL not require legacy compatibility readers.

#### Scenario: Earlier context-free project record

- **WHEN** a registry operation encounters an ordinary project record whose installation context cannot be established
- **THEN** it reports incompatible state before native mutation, preserves existing files and history, and directs the caller to a fresh registry
