# git-profile-registry Specification

## Purpose

Define a private append-only journal that gives Zuat durable observations, named desired-state profiles, domain history, and forward-only reversibility without exposing Git workflows.

## Requirements

### Requirement: Private registry isolation
Zuat SHALL keep its journal and profile state beneath a selected Zuat application-data root, separate from user project repositories and native agent configuration roots. A destination override for testing or automation SHALL isolate all Zuat-controlled registry state beneath that selected root.

#### Scenario: Initialize private state
- **WHEN** Zuat first operates with an empty selected application-data root
- **THEN** it initializes its private registry without modifying a user project repository or native agent root

### Requirement: Hidden Git implementation
Zuat MAY use Git internally to persist journal and profile state, but SHALL NOT expose private journal branches, indexes, staging areas, commit hashes, refs, working-tree status, or Git recovery operations through its supported Python or CLI contracts. Caller-selected source revisions and resolved source commits MAY be exposed as source provenance under the applicable source-aware capability; they SHALL NOT identify or control the private journal.

#### Scenario: Inspect public state
- **WHEN** a caller requests Zuat status, profiles, or history
- **THEN** Zuat returns domain assets, profile names, operation identifiers, and lifecycle outcomes without requiring or exposing Git concepts

#### Scenario: Perform a domain mutation
- **WHEN** a caller installs, uninstalls, switches, forces, or reverts through a supported interface
- **THEN** Zuat performs any required internal Git work automatically without asking the caller to stage or commit

### Requirement: Concrete human-browsable registry projection
Zuat SHALL persist the private registry as a concrete checked-out tree with one top-level directory for each supported agent's latest bounded observation, concrete desired assets beneath `profiles/<profile>/<agent>/`, ordered operation documents beneath `operations/`, a compact stable-identity `catalog.json`, and a plain-text `selected-profile`. Zuat SHALL NOT use an `observations/` wrapper, `events/` directory, or monolithic `state.json` as the primary representation. Operation documents and index metadata SHALL reference concrete assets rather than duplicate their payloads.

#### Scenario: Inspect a fresh Claude observation
- **WHEN** Zuat observes manageable Claude skills and hook fragments in a fresh private registry
- **THEN** their normalized content appears beneath the top-level `claude` tree, the changed observation has an ordered document beneath `operations`, and the stable identities appear in `catalog.json`

#### Scenario: Keep unknown content outside desired state
- **WHEN** a completed observation discovers manageable content that is not a member of the selected profile
- **THEN** the content appears in the applicable top-level agent tree and remains absent from the selected profile tree

#### Scenario: Materialize desired profile content
- **WHEN** an asset is adopted or installed into a profile
- **THEN** its concrete desired representation appears beneath that profile's agent tree with adjacent stable-reference metadata

#### Scenario: Review an internal change
- **WHEN** a maintainer compares two internal journal commits
- **THEN** the checked-out tree identifies the concrete asset, profile, catalog entry, selected profile, or operation record that changed without requiring a serialized state-document decoder

### Requirement: Append-only changed-observation journal
Zuat SHALL automatically append an internal journal entry when a completed observation contains a normalized manageable state that differs from the preceding completed observation. Observation entries SHALL include stable asset references, authority classifications, fingerprints, and completeness evidence. An observation alone SHALL NOT silently add unauthoritative assets to the selected desired-state profile.

#### Scenario: Record changed native state
- **WHEN** an observation detects a changed, added, or removed manageable asset
- **THEN** Zuat appends one observation event describing the change while leaving desired profile membership unchanged

#### Scenario: Deduplicate unchanged observation
- **WHEN** a completed observation is equivalent to the immediately preceding completed observation
- **THEN** Zuat creates no duplicate observation event

#### Scenario: Record incomplete observation
- **WHEN** observation is partial or indeterminate
- **THEN** Zuat journals that completeness outcome without treating unobserved content as deleted or authoritative

### Requirement: Append-only lifecycle journal
Every install, adoption, uninstall, forced reconciliation, profile creation, profile switch, and revert SHALL append a domain operation event containing a stable operation identifier, requested intent, relevant before-and-after asset evidence, force policy, and verified outcome. Existing journal events SHALL never be amended or deleted by a later domain operation.

#### Scenario: Record a successful install
- **WHEN** installation converges and verification succeeds
- **THEN** Zuat appends an install event containing the affected profile and asset references

#### Scenario: Record a rejected mutation
- **WHEN** a domain mutation is rejected by validation, conflict detection, or verification
- **THEN** Zuat appends an outcome that preserves the attempted intent and diagnostic evidence without claiming convergence

### Requirement: Named desired-state profiles
Zuat SHALL expose profiles only as user-selected names representing desired agent asset state. Creating a profile SHALL derive its desired state from an explicitly selected existing profile or the current selected profile, and switching profiles SHALL reconcile selected native agent surfaces to the target desired state.

#### Scenario: Create a profile
- **WHEN** a caller creates a profile from the current selected profile
- **THEN** Zuat records a distinct named desired state without changing native agent surfaces

#### Scenario: List profiles
- **WHEN** a caller lists profiles
- **THEN** Zuat returns profile names and identifies the selected profile without exposing internal Git references

#### Scenario: Switch profiles
- **WHEN** a caller switches to a valid target profile and native preflight succeeds
- **THEN** Zuat reconciles the selected agents, verifies their outcomes, selects the target profile, and appends a profile-switch event

#### Scenario: Block a conflicting switch
- **WHEN** profile switching would overwrite or remove conflicting unauthoritative state without force
- **THEN** Zuat rejects the switch and reports the blocking asset references without selecting the target profile

### Requirement: Forced decisions are durable
An operation that uses force SHALL record the explicit force decision and the unauthoritative or conflicting state it displaced. Force SHALL authorize only the requested operation and SHALL NOT establish a global policy for future conflicts.

#### Scenario: Record forced reconciliation
- **WHEN** a caller forces a conflicting install, uninstall, or profile switch
- **THEN** the appended operation event records force and the affected before-and-after asset evidence

#### Scenario: Encounter a later conflict
- **WHEN** a later operation encounters different conflicting unauthoritative state
- **THEN** Zuat requires a new explicit force decision

### Requirement: Forward-only revert
Zuat SHALL revert a completed domain operation by appending and applying a new inverse operation. Revert SHALL reference a stable domain operation identifier, verify current preconditions, preserve all earlier history, and require force if intervening native drift would otherwise be overwritten or removed.

#### Scenario: Revert a completed install
- **WHEN** a caller reverts an install operation and current state satisfies its inverse preconditions
- **THEN** Zuat applies the corresponding uninstall intent and appends a new revert event that references the original operation

#### Scenario: Revert after conflicting drift
- **WHEN** an inverse operation would overwrite or remove intervening conflicting unauthoritative state without force
- **THEN** Zuat rejects the revert and reports the conflict while preserving current state and all journal history

#### Scenario: Revert a revert
- **WHEN** a caller selects a completed revert operation for reversal
- **THEN** Zuat treats it as another forward inverse operation and appends a new event

### Requirement: Domain history and internal recovery
Zuat SHALL provide domain history ordered by journal sequence and addressable by stable operation identifiers. After interruption or storage recovery, Zuat SHALL safely classify internal consistency or preserve pending recovery evidence without asking users to manipulate Git state or recover observation snapshots manually. Unresolved outcomes SHALL remain partial or indeterminate. Native verification or restoration SHALL use the applicable operation-specific orchestration and original context, with explicit restoration where required; reopening alone SHALL NOT automatically replay or retry interrupted native mutations or claim they succeeded.

#### Scenario: Inspect history
- **WHEN** a caller requests operation history
- **THEN** Zuat returns ordered domain events with operation kind, profile, affected asset references, force policy, and outcome

#### Scenario: Resume after interruption
- **WHEN** Zuat starts after an interrupted mutation
- **THEN** it preserves pending evidence for operation-specific recovery or records an indeterminate recovery event requiring fresh observation, reports unresolved state, and exposes no partially accepted profile update as successful

### Requirement: Serialized profile transitions
Zuat SHALL serialize journal and profile mutations within one selected application-data root. A profile transition SHALL become selected only after the required native outcomes are verified; partial or indeterminate outcomes SHALL remain visible in history without being reported as successful convergence.

#### Scenario: Concurrent mutation attempt
- **WHEN** a second process attempts a journal or profile mutation while another mutation holds the registry lock
- **THEN** Zuat rejects or waits according to its bounded lock policy without interleaving the operations

#### Scenario: Verification fails during transition
- **WHEN** a native mutation cannot be verified as converged
- **THEN** Zuat records the failure or uncertain outcome and does not report the target profile transition as successful
