## Purpose

Let callers inspect independently managed skills and hooks against intended source content and update them safely with verifiable, recoverable outcomes.

## ADDED Requirements

### Requirement: Source-aware inspection separates content from ownership

The public Python interface SHALL inspect one independently managed skill or hook against supplied source content in an explicit agent and installation scope. Results SHALL distinguish absent, current, outdated, conflicting local changes, unowned, unsupported, and indeterminate states and expose source-match and ownership evidence separately. Current SHALL require valid ownership and matching installed/source content. Outdated SHALL mean installed content still matches its owned baseline but differs from the supplied source. An unowned content match SHALL NOT imply ownership. Invalid or mismatched ownership evidence SHALL NOT authorize replacement.

#### Scenario: New packaged revision

- **WHEN** an owned installation still matches its recorded baseline but the supplied source has changed
- **THEN** inspection reports outdated, with the observed and intended content evidence distinguishable

#### Scenario: Local modification

- **WHEN** an owned installation differs from its recorded baseline
- **THEN** inspection reports a conflict rather than treating local changes as a routine packaged update, even when the new source matches the local content

#### Scenario: Matching unowned content

- **WHEN** native content matches the supplied source but has no valid ownership evidence
- **THEN** inspection reports unowned content with a source match and does not adopt it

#### Scenario: Absent or unsupported target

- **WHEN** the requested destination is absent or the agent does not support the requested asset and scope
- **THEN** inspection distinguishes absence from unsupported capability without claiming installation

### Requirement: Inspection does not mutate native assets or authority

Inspection SHALL NOT write native configuration, install, update, adopt, or remove an asset. It SHALL use selected-agent evidence and report malformed or insufficient evidence as unresolved rather than absence. Unrelated plugin-manager failure SHALL NOT prevent inspecting a target whose independent ownership and destination can be established safely. If independent-provider status cannot be established, the result SHALL remain indeterminate and plugin-owned bodies SHALL NOT be ingested into global snapshots.

#### Scenario: Owned target with unavailable plugin manager

- **WHEN** plugin discovery fails but the requested independent asset has a verified destination and valid ownership evidence
- **THEN** source-aware inspection reports the asset's established state without invoking plugin mutation or claiming complete plugin inventory

#### Scenario: Ambiguous provider

- **WHEN** a candidate might be plugin-owned and the available evidence cannot establish independent management
- **THEN** inspection reports indeterminate provider evidence without adopting or archiving the candidate contents

### Requirement: Explicit targeted update

The public Python interface SHALL update one existing independently managed skill or hook using supplied source content and an unambiguous installation target. Update SHALL revalidate native state and authority at mutation time, reject absent targets rather than implicitly install them, and reject conflicting or unowned replacement unless explicit forced reconciliation is requested. Force SHALL NOT bypass scope, provider, path safety or source validation. No-change results SHALL preserve installed content and report that no replacement occurred.

#### Scenario: Ordinary owned update

- **WHEN** a caller updates an outdated owned asset without force
- **THEN** only the selected installation is replaced and success requires verification against the new source

#### Scenario: State changes after inspection

- **WHEN** a caller inspected an outdated asset but its native content changes before update
- **THEN** an unforced update rejects the newly conflicting target without replacing it

#### Scenario: Force does not select an ambiguous hook

- **WHEN** multiple native declarations match the requested hook target or a bundled contribution is selected
- **THEN** update rejects the request before mutation even when force is true

#### Scenario: No-op and missing target

- **WHEN** update targets current content or a missing installation
- **THEN** current content is left unchanged with a no-change result, while the missing target receives a non-success result directing the caller to installation

### Requirement: Updates preserve recoverable forward history

Before replacing native content, update SHALL preserve the selected target's actual prior content and ownership evidence, including local or unowned content explicitly selected for forced replacement. Verified update SHALL publish the new managed state and a domain operation identifier usable by existing restoration operations. Restoration SHALL append a new transition, preserve prior history, and verify restored native state. Mutation, verification, or compensation failures SHALL expose honest partial or failed outcomes and retain actionable recovery evidence rather than publish unverified success. Callers SHALL NOT need Git identifiers, staging commands or internal plans.

#### Scenario: Update and restore

- **WHEN** an asset is updated from A to B and the caller restores the returned operation
- **THEN** native content returns to A through a new verified transition, and both transitions remain in history

#### Scenario: Forced repair retains local content

- **WHEN** a caller explicitly replaces locally modified content with a packaged revision and later restores the operation
- **THEN** restoration recovers the actual pre-update local content rather than substituting the last packaged baseline

#### Scenario: Interrupted update

- **WHEN** execution stops after native replacement but before verified completion is recorded
- **THEN** reopening retains the pending operation and recovery establishes the observed state without erasing earlier history or claiming an unverified target is applied

### Requirement: Native and provider boundaries survive targeted operations

Skill updates SHALL replace the complete selected owned projection, including removing obsolete files, without altering neighboring assets. Shared-hook updates SHALL replace only the selected owned declaration and preserve unrelated hooks and configuration. Plugin installations and their contributions SHALL remain on the reference-only lifecycle path and SHALL NOT be copied or independently edited by ordinary asset updates. Source-aware operations SHALL be available without the optional CLI dependency.

#### Scenario: Shared configuration neighbors

- **WHEN** one managed hook is updated in a settings document containing unrelated hooks and settings
- **THEN** the selected declaration changes, unrelated values remain intact, and restoring the update preserves those unrelated values

#### Scenario: Removed source file

- **WHEN** a new skill revision omits a file from its previous installed projection
- **THEN** update removes that obsolete file from the selected skill while retaining neighboring skill directories

#### Scenario: Python-only consumer

- **WHEN** a caller uses source-aware inspection, update and restoration from a base-only installation
- **THEN** those operations work without requiring the optional CLI or agent-router
