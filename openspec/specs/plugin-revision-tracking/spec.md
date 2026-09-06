# plugin-revision-tracking Specification

## Purpose

Track installed plugin revisions and their lifecycle without storing plugin source content, while making profile and recovery outcomes verifiable.

## Requirements

### Requirement: Exact plugin revision identity

An exact plugin revision SHALL be identified by `(agent_kind, plugin_id, version)`. The plugin ID SHALL retain its canonical native namespace, and the version SHALL be an opaque value obtained from native revision evidence, not inferred from a display name or fabricated from source contents. Installation scope and project context SHALL be recorded separately from revision identity. Missing identity or version evidence SHALL remain explicitly unresolved and SHALL NOT be represented as an exact revision.

#### Scenario: Shared revision in separate installations

- **WHEN** the same agent and canonical plugin ID at the same version is installed in two supported scopes
- **THEN** both installations reference the same revision and retain independently addressable installation state

#### Scenario: Distinct agents and versions

- **WHEN** installed plugins share a display name but differ in agent kind, canonical plugin ID, or version
- **THEN** they are not conflated into one exact revision

#### Scenario: Missing version

- **WHEN** native inventory confirms installation without a version
- **THEN** the installation is discoverable with unresolved revision evidence and cannot be advertised as exactly restorable

### Requirement: Reference-only durable plugin records

Every Zuat-managed durable representation of plugin state SHALL contain only validated revision references and allowlisted installation, provider, policy, provenance, and operation metadata. This restriction SHALL apply to observations, profiles, journal history, recovery records, auxiliary state, and payload archives, including failed operations. Plugin source trees, bundled skill and hook bodies, artifact contents, runtime paths, raw native-manager output, and credentials SHALL NOT be persisted. Resolved local paths SHALL remain transient. A source locator, if retained for reacquisition, SHALL be credential-free, non-runtime metadata rather than copied content.

#### Scenario: Snapshot mixed providers

- **WHEN** a snapshot observes a global skill and a plugin that bundles a skill and a hook
- **THEN** the global skill content is recoverable from its snapshot while all durable plugin records contain references and allowed metadata only

#### Scenario: Native output contains sensitive payloads

- **WHEN** native discovery or mutation output contains plugin bodies, runtime paths, or credentials
- **THEN** persisted success, failure, and recovery records exclude those values and retain only safe diagnostics and allowed state

### Requirement: Ownership remains separate from observation

Zuat SHALL observe both registered and externally installed plugins without requiring a staging operation. Observation SHALL retain installation provenance and authority independently of revision identity. Forced reconciliation SHALL permit explicitly requested changes to unauthoritative installations where native capabilities allow them, but SHALL NOT grant source trust or bypass native restrictions.

#### Scenario: External installation

- **WHEN** a plugin installed outside Zuat is discovered
- **THEN** its installation and available revision evidence are recorded with external or unknown provenance without silently claiming Zuat ownership

#### Scenario: Forced operation is not trust

- **WHEN** forced reconciliation would install from an untrusted direct source
- **THEN** the operation is rejected before mutation unless the separate explicit trust requirement is satisfied

### Requirement: Append-only plugin transitions

Plugin install, update, removal, profile reconciliation, and restoration SHALL preserve forward-appended domain history containing safe before and after state references. Updating a plugin SHALL record the revision transition for its installation rather than overwrite the prior revision record. Restoring prior state SHALL append a new operation rather than rewrite history. Public results SHALL use domain operation identifiers and outcomes without requiring Git concepts.

#### Scenario: Update followed by restoration

- **WHEN** an installation moves from version A to version B and is later successfully restored to A
- **THEN** history retains both transitions in order and the restoration references the earlier operation without erasing B

### Requirement: Exact profile and restore resolution

Profiles and restoration SHALL resolve plugin pointers through supported native lifecycle operations, not archived plugin bodies. Before mutation, Zuat SHALL check required scope, trust, and exact-revision capabilities. Unresolved version evidence, an unavailable exact revision, or unsupported exact acquisition SHALL produce an explicit non-success result; Zuat SHALL NOT silently choose the latest version. Successful exact restoration SHALL require rediscovery of the requested revision and requested installation state.

#### Scenario: Exact revision available

- **WHEN** a profile requires version A and the native manager can acquire and verify A
- **THEN** reconciliation installs A and records the verified resulting installation without copying plugin sources into Zuat state

#### Scenario: Only latest version available

- **WHEN** restoration requests A but the manager only supports installing its current latest version B
- **THEN** Zuat reports exact restoration as unsupported or unavailable without installing B as a substitute

#### Scenario: Restoration needs fresh project trust

- **WHEN** a recorded plugin revision belongs to a scope requiring project trust and the current restoration request does not grant it
- **THEN** Zuat rejects restoration before mutation and does not infer permission from the earlier successful operation

### Requirement: Honest partial outcomes and recovery

Native command success SHALL NOT alone establish lifecycle success. Zuat SHALL rediscover the targeted installation and report verified, partial, failed, or indeterminate outcomes according to the observed postcondition. Installation presence, revision certainty, and native activation SHALL remain separate facts. Incomplete operations SHALL retain reference-only recovery evidence and SHALL NOT publish an unverified target profile as successfully applied.

#### Scenario: Command succeeds but rediscovery fails

- **WHEN** a native mutation exits successfully but its resulting installation cannot be rediscovered reliably
- **THEN** the operation reports an unverified outcome and retains safe recovery evidence without claiming convergence

#### Scenario: Restart after interrupted update

- **WHEN** Zuat restarts after an update was issued but before its result was recorded
- **THEN** recovery compares current native state with the recorded before and intended revision pointers and appends the observed outcome without replaying plugin source content
