# Spec Delta

## ADDED Requirements

### Requirement: Shared-hook group identity is distinct from content and authority

Source-aware inspection SHALL resolve a shared-hook declaration group as a complete, uniquely selected group within the requested agent, scope, provider, and destination. It SHALL distinguish a valid recorded ownership baseline from the actual selected content and the intended source. When a valid receipt's baseline cannot identify the complete current group but the complete supplied source uniquely identifies it without competing baseline members or another owner's claim, inspection SHALL retain that receipt's identity and baseline evidence and report a conflict with matching source content, rather than losing the ownership evidence or silently granting current authority. Invalid receipts, duplicate candidates, incomplete or overlapping groups, and competing ownership SHALL remain non-authorizing and SHALL be diagnosed. Inspection SHALL NOT repair evidence or mutate native content.

#### Scenario: Native content matches the new source but the receipt is stale
- **WHEN** a valid receipt describes earlier handlers, the requested source uniquely matches the complete installed group, and no competing baseline members or ownership claims exist
- **THEN** inspection reports conflict, retains the valid receipt and baseline evidence, and reports that installed content matches the supplied source
- **AND** neither native configuration nor ownership is changed

#### Scenario: Unrelated insertion preserves identity
- **WHEN** another tool adds a distinct declaration beside an unchanged owned group
- **THEN** inspection retains the owned group's identity and classification without including the neighboring declaration in that group's content

#### Scenario: Relative order changes without changing declarations
- **WHEN** all owned declarations remain uniquely identifiable but their relative order changes
- **THEN** inspection retains their ownership identity and reports the observed order difference as a conflict unless the selected native contract explicitly establishes order equivalence
- **AND** it neither sorts declarations nor grants permission to overwrite them

#### Scenario: Group is duplicated or only partly identifiable
- **WHEN** multiple copies satisfy a requested declaration or neither the baseline nor source identifies a unique complete group
- **THEN** inspection reports indeterminate identity with a diagnostic and does not infer absence or choose an array position

#### Scenario: Old and new groups both remain
- **WHEN** source content exists but baseline declarations outside that source group or competing ownership claims prevent unique reconciliation
- **THEN** inspection reports the conflict or ambiguity without selecting the new group as proof that the old installation was replaced

### Requirement: Explicit shared-hook receipt repair is recoverable

Explicit forced targeted update SHALL reconcile a valid but stale shared-hook receipt when the target group is uniquely identified and its native content already matches the intended source. It SHALL preserve the native document's bytes, modification time, and unrelated entries while publishing verified ownership and selected-profile evidence. It SHALL return an operation identifier and distinguish a control-state change from native-content replacement. The same request without force SHALL reject the stale-baseline conflict. Repeating the request after successful repair SHALL report current state and perform no further mutation. Force SHALL NOT bypass invalid receipts, competing ownership, unresolved groups, provider restrictions, or scope/path validation.

Repair SHALL capture actual pre-operation content, prior ownership, and prior selected-profile evidence before changing authority. Restoration SHALL recover those distinct prior states through forward history rather than treating the new source as the old baseline. Failure or interruption after changing authority SHALL retain enough evidence for verified compensation or explicit restoration after reopening; unverified repair SHALL NOT be reported as success. Native state and selection evidence SHALL be revalidated at mutation time and before successful publication.

#### Scenario: Repair changes authority without rewriting correct hooks
- **WHEN** a caller explicitly forces targeted update of a uniquely identified source-matching group with a valid stale receipt
- **THEN** repair leaves the native file bytes and modification time unchanged, publishes the new ownership baseline, and returns a recoverable operation identifier
- **AND** subsequent inspection reports current and a repeated update does not append another mutation event

#### Scenario: Ordinary update cannot silently repair authority
- **WHEN** installed hooks match the supplied source but differ from their valid recorded baseline and update is requested without force
- **THEN** update rejects the conflict without changing native content, ownership, or the selected profile

#### Scenario: Restore a receipt-only repair
- **WHEN** a successful receipt repair is restored using its operation identifier
- **THEN** the actual pre-repair hooks, stale receipt, and previous selected-profile evidence are restored distinctly and unrelated hooks are preserved
- **AND** source-aware inspection again reflects the pre-repair conflict instead of falsely reporting current authority

#### Scenario: Repair is interrupted before publication completes
- **WHEN** receipt repair stops after writing ownership but before verified completion and the service is reopened
- **THEN** the unresolved operation remains visible with its recovery identifier and explicit restoration recovers the prior evidence without claiming convergence

#### Scenario: Candidate changes after inspection
- **WHEN** the native group, its ownership, its provider eligibility, or the intended source changes before repair is committed
- **THEN** repair rejects or reports a recoverable failure instead of publishing stale evidence, preserving unrelated concurrent edits
