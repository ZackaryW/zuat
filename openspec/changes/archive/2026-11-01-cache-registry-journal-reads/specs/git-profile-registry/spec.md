# Spec Delta

## ADDED Requirements

### Requirement: Incremental journal reads
Within one open registry, Zuat SHALL decode each operation document at most once while that document is unchanged, so repeated history reads during one operation do not re-decode the whole journal. Each history read SHALL still reflect the operation documents currently on disk, including ones appended by another process or registry handle, and SHALL still reject a non-contiguous sequence.

#### Scenario: Repeated reads reuse decoded events
- **WHEN** history is read twice through the same open registry and no operation document changed in between
- **THEN** the second read returns the same events without decoding any operation document again

#### Scenario: Only appended documents are decoded
- **WHEN** a new operation is appended after history was read through the same open registry
- **THEN** the next history read decodes only the new operation document and returns every event in sequence order

#### Scenario: External appends are visible
- **WHEN** another registry handle or process appends an operation document after this handle has read history
- **THEN** this handle's next history read includes the appended event

#### Scenario: Gaps are still rejected
- **WHEN** an operation document is removed so the on-disk sequence is no longer contiguous
- **THEN** the next history read fails with a registry error instead of returning cached events

### Requirement: Catalog lookup without journal replay
Looking up a stable asset reference by identifier SHALL resolve against the persisted catalog alone and SHALL NOT replay the operation journal.

#### Scenario: Known reference resolves from the catalog
- **WHEN** an asset reference identifier present in the catalog is looked up
- **THEN** the matching reference is returned without reading any operation document

#### Scenario: Unknown reference is rejected
- **WHEN** an identifier absent from the catalog is looked up
- **THEN** a registry error reports the unknown asset reference
