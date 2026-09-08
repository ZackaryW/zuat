## Purpose

Define one stable public Python orchestration surface and an optional Click CLI that expose domain assets and lifecycle operations without leaking Git or internal package layers.

## ADDED Requirements

### Requirement: Importable base package
The base Zuat distribution SHALL expose its public Python operations without importing Click. Agent modeling and registry operations needed by Python callers SHALL remain available when the optional CLI dependency is absent.

#### Scenario: Import without CLI dependencies
- **WHEN** the base distribution is installed without the `cli` extra
- **THEN** importing `zuat` and `zuat.pub` succeeds without importing Click

### Requirement: Optional Click command
Installing `zuat[cli]` SHALL provide a Click-based `zuat` console command. Invoking the packaged command without the optional dependency SHALL produce concise installation guidance and SHALL NOT expose an optional-dependency traceback.

#### Scenario: Invoke the installed CLI extra
- **WHEN** the distribution is installed with `zuat[cli]`
- **THEN** invoking `zuat --help` displays the Click command surface

#### Scenario: Invoke without the CLI extra
- **WHEN** the base distribution is installed without `zuat[cli]` and the packaged command is invoked
- **THEN** the command tells the caller to install `zuat[cli]` without displaying a Click import traceback

### Requirement: Public orchestration boundary
All supported Python operations SHALL be exposed through `zuat.pub`. CLI handlers SHALL invoke only that public surface and SHALL NOT call internal utilities, agent resolvers, or registry adapters directly. Internal utilities SHALL remain reusable mechanics rather than a second supported command surface.

#### Scenario: Execute a CLI operation
- **WHEN** a caller invokes any supported CLI lifecycle command
- **THEN** the handler delegates the request through the corresponding public `zuat.pub` operation

#### Scenario: Execute the same Python operation
- **WHEN** a Python caller invokes the corresponding public operation directly
- **THEN** it receives the same domain result and error semantics as the CLI handler before presentation formatting

### Requirement: Domain lifecycle operations
The public surface SHALL provide observation or status, install, uninstall, profile listing and creation, profile switching, domain history, and forward-only revert. It SHALL NOT provide public stage, commit, branch, raw Git status, raw revision, or observation-snapshot recovery operations for the private journal.

#### Scenario: Inspect command availability
- **WHEN** a caller inspects the public Python or CLI surface
- **THEN** the complete asset and profile lifecycle is available using domain terminology only

#### Scenario: Attempt to use a removed Git workflow
- **WHEN** a caller looks for public staging, committing, branch checkout, or snapshot recovery
- **THEN** those operations are absent from the supported public contract

### Requirement: Explicit mutation inputs
Mutating operations SHALL be noninteractive and require all material choices as explicit inputs, including the target agent or stable asset reference, selected profile when applicable, operation identifier for revert, and whether conflicting unauthoritative state may be forced.

#### Scenario: Reject incomplete mutation input
- **WHEN** a mutating command omits a required asset reference, agent, profile, operation identifier, or conflict decision
- **THEN** the public surface rejects the request before registry or native mutation

#### Scenario: Force through the public surface
- **WHEN** a caller supplies force for a supported conflicting lifecycle operation
- **THEN** the public layer passes that explicit decision to orchestration and reports the forced outcome

### Requirement: Deterministic domain results
Asset and profile lifecycle operations SHALL return structured domain results identifying the operation, selected profile, affected stable asset references, authority or lifecycle transitions, native verification outcomes, and blocking diagnostics as applicable to the operation. Recorded lifecycle results SHALL use stable Zuat operation identifiers. Read-only queries, bundle operations, and extension APIs SHALL follow their own typed capability contracts without requiring inapplicable lifecycle fields or mutation side effects. Public results SHALL NOT expose private journal Git hashes, refs, indexes, branches, or working-tree states; caller-selected source revisions and resolved source commits MAY appear as source provenance under the applicable source-aware contract.

#### Scenario: Return an observation result
- **WHEN** a caller requests status after native observation
- **THEN** the result reports each discovered asset reference, authority classification, fingerprint evidence, and observation completeness

#### Scenario: Report a blocked mutation
- **WHEN** a lifecycle operation is blocked by a native conflict
- **THEN** Python and CLI callers receive a deterministic non-success result identifying the blocking asset references and force requirement without an implementation traceback

### Requirement: Deterministic CLI presentation
The CLI SHALL provide concise human-readable output and an explicit JSON form suitable for automation. JSON mode SHALL emit exactly one structured result envelope to standard output and SHALL direct diagnostics to standard error.

#### Scenario: Emit an automation result
- **WHEN** a CLI operation is invoked with JSON output
- **THEN** exactly one domain result envelope is written to standard output and diagnostics are written to standard error

#### Scenario: Present domain history
- **WHEN** a caller requests history in human-readable mode
- **THEN** the CLI presents operation identifiers, kinds, profiles, affected assets, force decisions, and outcomes without Git-specific fields
