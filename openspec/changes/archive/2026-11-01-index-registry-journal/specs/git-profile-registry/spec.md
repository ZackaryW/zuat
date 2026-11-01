# Spec Delta

## ADDED Requirements

### Requirement: Delta observation events
A new observation event SHALL record only evidence that differs from the folded prior observation: added or changed evidence after the observation, prior evidence of changed or removed assets, and identifiers of removed assets. It SHALL NOT repeat unchanged evidence. Removal SHALL be recorded only for complete observations, within the observed agents and context.

#### Scenario: Unchanged assets are not repeated
- **WHEN** a complete observation of 30 assets differs from the prior observation by one changed fingerprint
- **THEN** the appended observation event carries evidence for that one asset only

#### Scenario: Removal is recorded for complete observations
- **WHEN** a complete observation no longer contains an asset of an observed agent and context that the prior observation contained
- **THEN** the event records that asset's identifier as removed together with its prior evidence

#### Scenario: Partial observation never removes
- **WHEN** a partial observation omits a previously observed asset
- **THEN** the event records no removal and the folded latest observation still contains that asset

### Requirement: Legacy observation compatibility
Zuat SHALL fold existing full-snapshot observation events and new delta observation events into the same latest observation. New delta events SHALL use a distinct operation kind, so earlier Zuat versions reject them with an error instead of misreading them.

#### Scenario: Mixed journal folds consistently
- **WHEN** a journal contains full-snapshot observation events followed by delta observation events
- **THEN** the latest observation equals what folding the equivalent full snapshots would produce

#### Scenario: Delta events are distinguishable in history
- **WHEN** domain history is read after a delta observation was appended
- **THEN** that event reports the delta observation kind and its delta evidence

### Requirement: Derived journal index
Zuat SHALL maintain a private, derived journal index outside the browsable registry tree. It SHALL answer next sequence, operation lookup and existence, latest observation identity, latest observation, and latest artifact policy without decoding operation documents. The journal SHALL remain the only source of truth.

#### Scenario: Index answers without decoding
- **WHEN** a fresh registry handle looks up the latest observation and an operation by identifier while the index is current
- **THEN** both answers are returned without decoding any operation document other than the one requested

#### Scenario: Index stays outside the browsable tree
- **WHEN** a maintainer inspects the checked-out registry tree or its internal commits
- **THEN** no index document appears among the projected files

### Requirement: Self-healing journal index
Every index read SHALL validate the index against the operation documents on disk. A stale index SHALL catch up by folding only the newer documents. A missing, corrupt, or inconsistent index SHALL be rebuilt from the journal. Neither path SHALL change journal history.

#### Scenario: Catch up after an external append
- **WHEN** another handle or an earlier Zuat version appended operations that the index does not yet cover
- **THEN** the next query folds only those operations and returns results that include them

#### Scenario: Rebuild a damaged index
- **WHEN** the index document is deleted, unreadable, or its watermark does not match the journal
- **THEN** the next query rebuilds the index from the journal and returns the same answers a full replay would produce

#### Scenario: Gaps are still rejected
- **WHEN** an operation document is missing so the journal sequence is not contiguous
- **THEN** index validation fails with a registry error rather than serving index answers
