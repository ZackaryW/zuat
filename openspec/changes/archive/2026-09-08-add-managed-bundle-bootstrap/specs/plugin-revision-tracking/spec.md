## MODIFIED Requirements

### Requirement: Reference-only durable plugin records

Every Zuat-managed durable representation of observed or installed plugin state SHALL contain only validated revision references and allowlisted installation, provider, policy, provenance, and operation metadata. This restriction SHALL apply to observations, profiles, journal history, recovery records, auxiliary tracking state, and payload archives, including failed operations. Plugin source trees, bundled skill and hook bodies, artifact contents, runtime paths, raw native-manager output, and credentials SHALL NOT be persisted in those representations. Resolved native runtime paths SHALL remain transient. A source locator, if retained for reacquisition, SHALL be credential-free provenance rather than copied content.

A separately isolated bundle compiler store SHALL be permitted to hold validated caller-selected build inputs, generated plugin outputs and the private source bindings required to rebuild them. This exception SHALL NOT permit capturing installed third-party plugin contents, placing build bodies or local source paths in journal/profile/recovery records, or treating a build as observed installation evidence. Publicly resolved build paths SHALL remain transient, with durable bundle references expressed by identity and revision. Local source bindings SHALL remain private to the compiler store and credentials SHALL not be persisted there.

#### Scenario: Snapshot mixed providers

- **WHEN** a snapshot observes a global skill and a plugin that bundles a skill and a hook
- **THEN** the global skill content is recoverable from its snapshot while all durable plugin records contain references and allowed metadata only

#### Scenario: Native output contains sensitive payloads

- **WHEN** native discovery or mutation output contains plugin bodies, runtime paths, or credentials
- **THEN** persisted success, failure, and recovery records exclude those values and retain only safe diagnostics and allowed state

#### Scenario: Build outputs remain outside tracking history

- **WHEN** Zuat compiles a caller-selected skill repository and bootstraps the resulting plugin
- **THEN** generated files remain in the isolated compiler store while observations, profiles, history and failure evidence contain only allowed references and metadata

#### Scenario: Compiler exception does not authorize plugin capture

- **WHEN** discovery encounters an independently installed third-party plugin
- **THEN** neither the compiler store nor lifecycle tracking captures its source tree as a consequence of discovery
