# Spec Delta

## MODIFIED Requirements

### Requirement: Domain install and adoption
Installing an asset SHALL make its requested content part of the selected profile and reconcile the applicable native surface. When equivalent content already exists at the resolved native locator, installation SHALL adopt it without requiring force and SHALL make the resulting state authoritative. For independently managed shared hooks, source-driven installation and adoption SHALL establish complete provider and target-identity evidence before native mutation. Verified absence SHALL permit installation; uniquely matching unowned content SHALL permit adoption without rewriting the native document. Indeterminate identity, duplicate or overlapping candidates, or unresolved differing declarations that could represent the requested group SHALL cause rejection rather than an append fallback. Force SHALL NOT resolve ambiguous identity. A valid stale receipt SHALL remain a conflict requiring explicit targeted reconciliation rather than being treated as missing ownership.

A valid ownership receipt SHALL NOT establish native presence. If the entire owned hook group is verifiably absent, installation SHALL recreate the requested group without force, preserve unrelated declarations and settings, and verify native presence before reporting success. Missing requested event keys or malformed event values SHALL NOT count as equivalent content. Partial or ambiguous groups SHALL remain non-authorizing.

#### Scenario: Install a new asset
- **WHEN** a caller installs a valid asset into a selected profile and no native conflict exists
- **THEN** Zuat adds the asset to the profile, reconciles the native surface, verifies the result, and reports it as authoritative

#### Scenario: Adopt equivalent native content
- **WHEN** a caller installs an asset whose requested content is equivalent to unauthoritative content already present at the resolved locator
- **THEN** Zuat adopts the existing content into the selected profile and reports it as authoritative without rewriting it unnecessarily

#### Scenario: Adopt an exact unowned hook group
- **WHEN** the complete independent group uniquely matches the source, has no ownership receipt or competing claim, and the caller explicitly installs it
- **THEN** Zuat records verified ownership and selected-profile evidence without changing native file bytes or modification time
- **AND** a subsequent inspection reports current

#### Scenario: Legacy declarations cannot be resolved from a new source
- **WHEN** an unowned shared configuration contains multiple differing declarations for the requested events and the supplied source cannot uniquely identify the requested group
- **THEN** source-driven install rejects the ambiguity, even with force, and preserves the native hooks and existing ownership
- **AND** it does not append a second group or publish successful installation evidence

#### Scenario: Duplicate matches or competing owners
- **WHEN** intended declarations match duplicate native entries or overlap another independently owned group
- **THEN** install rejects the unresolved identity or ownership conflict without adopting, removing, or duplicating any group's callbacks

#### Scenario: Unrelated event does not block a new group
- **WHEN** the requested hook group is verifiably absent and existing declarations belong to other native events
- **THEN** install adds only the requested group and preserves the unrelated declarations and settings

#### Scenario: Explicit array locators do not override ownership identity
- **WHEN** independently owned hooks move to different array positions and installation supplies their previous locators with force
- **THEN** installation follows the uniquely verified ownership identities without moving hooks back to those positions
- **AND** if edits or duplicate candidates make identity unresolved, installation rejects the request without choosing an array occupant

#### Scenario: Reinstall deleted owned hooks
- **WHEN** a valid receipt remains but the entire owned group is verifiably absent from the native document
- **THEN** unforced install restores exactly the requested declarations, preserves unrelated content, and subsequent inspection reports current
- **AND** repeating installation adds no duplicate declarations

#### Scenario: Missing event keys cannot verify installation
- **WHEN** native configuration omits a requested event key or supplies an incompatible event value
- **THEN** the missing declarations are not considered present and installation cannot report current based on that check

### Requirement: Explicit forced reconciliation
Zuat SHALL require an explicit force option before overwriting or removing conflicting unauthoritative native content. A forced operation SHALL remain scoped to the requested stable asset references and SHALL report both the displaced observation and the verified replacement or removal.

Callers SHALL be able to constrain a targeted update to receipt-only repair. This opt-in constraint SHALL require a valid owned shared-hook group matching the supplied source inside the update operation, preserving all existing force, identity, provider, and path restrictions. It SHALL reject nonmatching, missing, unowned, ambiguous, or unsupported targets without replacing native content. A current owned matching group SHALL remain a no-op. Omitting the constraint SHALL preserve existing update semantics.

#### Scenario: Reject an unforced conflict
- **WHEN** install or uninstall would overwrite or remove conflicting unauthoritative native content without force
- **THEN** Zuat rejects the mutation and returns the blocking asset references

#### Scenario: Force a conflicting install
- **WHEN** a caller explicitly forces installation over conflicting unauthoritative content
- **THEN** Zuat replaces only the referenced native asset, verifies the requested content, and reports the force decision

#### Scenario: Receipt-only guard rejects concurrent restoration
- **WHEN** a caller requests receipt-only repair after another writer restores the older owned native group
- **THEN** update rejects the now-nonmatching content without replacing it or advancing its ownership

#### Scenario: Guarded receipt repair remains recoverable
- **WHEN** a valid stale receipt identifies a unique shared-hook group matching the source and the caller requests forced receipt-only repair
- **THEN** update repairs ownership without rewriting native bytes, returns a recovery identifier, and repeating the request is a no-op

#### Scenario: State changes during guarded repair
- **WHEN** native state changes during capture or before replacement
- **THEN** update rejects or reports recoverable failure while preserving the concurrent native content
