# agent-asset-resolution Specification

## Purpose

Define independent Codex, Claude, Kimi, and Pi asset models that discover every manageable native asset and provide verified Zuat-owned lifecycle behavior.

## Requirements

### Requirement: Independent agent trees
Zuat SHALL represent Codex, Claude, Kimi, and Pi in independent top-level agent trees. An operation on one agent tree SHALL affect only that agent unless the caller explicitly requests separate operations for additional agents.

#### Scenario: Change one agent asset
- **WHEN** an operation targets a Codex skill
- **THEN** Zuat observes or reconciles only the Codex asset and leaves similarly named assets for other agents unchanged

#### Scenario: Represent identical content for two agents
- **WHEN** Codex and Claude contain skills with identical content
- **THEN** Zuat assigns each skill an agent-specific reference and allows their lifecycle state to diverge independently

### Requirement: Agent-owned native behavior
Zuat SHALL use one common resolution contract while requiring a distinct implementation for each supported agent. Each agent implementation SHALL own its native asset kinds, locations, formats, scopes, validation, reconciliation, and verification behavior.

#### Scenario: Resolve a supported agent
- **WHEN** Zuat processes an asset for Codex, Claude, Kimi, or Pi
- **THEN** it selects that agent's implementation and returns a common Zuat domain result

#### Scenario: Reject an unsupported agent
- **WHEN** a caller identifies an unsupported agent
- **THEN** Zuat rejects the request without interpreting the asset using another agent's rules

### Requirement: Stable references for manageable assets
Zuat SHALL assign every observed manageable asset a stable Zuat reference. The reference SHALL identify the agent, asset kind, scope, and native locator, and each observation SHALL carry fingerprint evidence for the content found at that locator.

#### Scenario: Rediscover unchanged content
- **WHEN** Zuat observes the same manageable asset at the same native locator more than once
- **THEN** it returns the same stable asset reference and equivalent fingerprint evidence

#### Scenario: Rediscover changed content
- **WHEN** content changes at a previously observed native locator
- **THEN** Zuat preserves the stable asset reference and reports updated fingerprint evidence

#### Scenario: Discover an existing shared hook fragment
- **WHEN** a shared native settings document contains a manageable hook fragment that Zuat did not install
- **THEN** Zuat assigns that fragment its own stable reference and reports it as an observed asset

### Requirement: Complete bounded observation
For every supported agent, Zuat SHALL enumerate all manageable skills, hook fragments, extensions, and plugin declarations within that agent's supported native scopes regardless of whether Zuat previously installed them. Zuat SHALL report each asset as authoritative, unauthoritative, conflicting, partial, or indeterminate using available profile, ownership, and verification evidence.

#### Scenario: Observe pre-existing assets
- **WHEN** an agent home contains manageable assets with no Zuat ownership record
- **THEN** Zuat reports every such asset as unauthoritative rather than omitting it

#### Scenario: Observe mixed authority
- **WHEN** one native surface contains both profile-matching and independently created manageable assets
- **THEN** Zuat reports the profile-matching assets as authoritative and the remaining assets with their applicable non-authoritative classifications

#### Scenario: Observation cannot be completed
- **WHEN** a supported native surface cannot be read or classified completely
- **THEN** Zuat reports the affected scope as partial or indeterminate and does not claim a complete observation

### Requirement: Normalized manageable representation
Zuat SHALL represent independently manageable skills, hook fragments, extensions, and plugin declarations rather than copying complete native agent directories. Plugin records SHALL describe native references and lifecycle evidence rather than copying runtime content.

#### Scenario: Normalize hooks in shared configuration
- **WHEN** a shared native settings document contains multiple manageable hook fragments
- **THEN** Zuat represents each fragment independently and retains a locator that can reconcile that fragment without replacing the complete document

#### Scenario: Observe a plugin declaration
- **WHEN** native discovery reports an installed or configured plugin
- **THEN** Zuat records its native reference, source, scope, policy, and available version evidence without copying its runtime directory

### Requirement: Domain install and adoption
Installing an asset SHALL make its requested content part of the selected profile and reconcile the applicable native surface. When equivalent content already exists at the resolved native locator, installation SHALL adopt it without requiring force and SHALL make the resulting state authoritative.

#### Scenario: Install a new asset
- **WHEN** a caller installs a valid asset into a selected profile and no native conflict exists
- **THEN** Zuat adds the asset to the profile, reconciles the native surface, verifies the result, and reports it as authoritative

#### Scenario: Adopt equivalent native content
- **WHEN** a caller installs an asset whose requested content is equivalent to unauthoritative content already present at the resolved locator
- **THEN** Zuat adopts the existing content into the selected profile and reports it as authoritative without rewriting it unnecessarily

### Requirement: Domain uninstall
Uninstalling an asset SHALL remove it from the selected profile when present and reconcile its removal from the applicable native surface. Zuat SHALL preserve unrelated content in shared documents and SHALL verify that only the referenced asset was removed.

#### Scenario: Uninstall an authoritative asset
- **WHEN** a caller uninstalls an authoritative asset by stable reference
- **THEN** Zuat removes it from the selected profile and native surface while leaving unrelated agent content unchanged

#### Scenario: Uninstall unauthoritative content with force
- **WHEN** a caller explicitly forces uninstall of an unauthoritative asset by stable reference
- **THEN** Zuat removes that native asset, preserves unrelated content, and reports the forced verified outcome

### Requirement: Explicit forced reconciliation
Zuat SHALL require an explicit force option before overwriting or removing conflicting unauthoritative native content. A forced operation SHALL remain scoped to the requested stable asset references and SHALL report both the displaced observation and the verified replacement or removal.

#### Scenario: Reject an unforced conflict
- **WHEN** install or uninstall would overwrite or remove conflicting unauthoritative native content without force
- **THEN** Zuat rejects the mutation and returns the blocking asset references

#### Scenario: Force a conflicting install
- **WHEN** a caller explicitly forces installation over conflicting unauthoritative content
- **THEN** Zuat replaces only the referenced native asset, verifies the requested content, and reports the force decision

### Requirement: Bounded and safe native access
Zuat SHALL exclude credentials, sessions, unrelated configuration, generated caches, unverified plugin runtime material, and content reached through symbolic links from asset observations and mutations.

#### Scenario: Encounter a symbolic link
- **WHEN** observation encounters a symbolic link within a candidate manageable asset
- **THEN** Zuat rejects that candidate without following the link or ingesting its target

#### Scenario: Preserve unrelated native configuration
- **WHEN** Zuat observes or reconciles a manageable fragment inside shared native configuration
- **THEN** it leaves unrelated settings outside the asset representation and unchanged on the native surface

### Requirement: Per-agent verified outcomes
Zuat SHALL report reconciliation independently for each selected agent. Filesystem changes SHALL use recoverable replacement behavior, while external plugin operations SHALL report partial or indeterminate outcomes whenever successful convergence cannot be verified.

#### Scenario: Reconcile a subset of agents
- **WHEN** a caller applies a profile operation only to Codex
- **THEN** Zuat reports Codex's verified outcome without claiming that Claude, Kimi, or Pi changed

#### Scenario: Encounter uncertain plugin mutation
- **WHEN** a native plugin manager may have changed state but postcondition verification cannot establish convergence
- **THEN** Zuat reports the affected agent operation as partial or indeterminate rather than successful
