## Purpose

Expose skills, hooks, and extensible artifacts with explicit provider provenance while preserving each agent's native plugin isolation and activation semantics.

## ADDED Requirements

### Requirement: Global and plugin provider provenance

Skill and hook discovery SHALL distinguish global declarations from plugin-provided contributions. A resolved plugin contribution SHALL identify its exact plugin revision, contribution kind, and provider-local contribution identifier, with installation context separate from that reference. Missing revision evidence SHALL be reported as unresolved rather than assigned a fabricated revision. Contribution discovery SHALL NOT copy plugin-owned declarations into global assets.

#### Scenario: Identical names across providers

- **WHEN** a global skill and two installed plugins each declare a skill named review
- **THEN** listing retains all discoverable provider identities and installation contexts without merging them solely by name

#### Scenario: Unknown plugin revision

- **WHEN** an installed plugin exposes a hook but native revision evidence is incomplete
- **THEN** discovery can report the hook with its unresolved provider evidence but cannot issue an exact revision-bound reference for it

### Requirement: Provider-aware selection and native behavior

Public asset helpers SHALL support selecting global or plugin providers and narrowing plugin selection by canonical ID, agent kind, version, and installation context. Omitted provider filters SHALL not hide discoverable providers. Mutations SHALL reject ambiguous targets and unsupported independently managed plugin contributions before making changes. They SHALL NOT implicitly remove an entire plugin to remove one contribution. Native namespaces, precedence, coexistence, and activation restrictions SHALL remain authoritative.

#### Scenario: Target only a global hook

- **WHEN** a caller removes a global hook while a plugin supplies a similarly named hook
- **THEN** the global declaration is removed and the plugin installation and contribution remain unchanged

#### Scenario: Plugin contribution cannot be independently removed

- **WHEN** a caller selects a bundled skill for removal and the agent does not support independent removal
- **THEN** Zuat reports the unsupported operation without editing plugin contents or uninstalling the plugin

#### Scenario: Ambiguous helper request

- **WHEN** a mutation identifies only a name that matches multiple providers
- **THEN** Zuat requests an unambiguous provider selection without mutating any matching provider

### Requirement: Generic artifact extension registration

Callers SHALL be able to register a generic artifact extension by identifier and extension contract version. Extensions SHALL locate artifacts using installed plugin context without requiring Zuat to understand artifact-domain contents. Duplicate conflicting registrations SHALL be rejected explicitly. An extension registration SHALL NOT authorize plugin installation, native activation changes, or artifact content persistence.

#### Scenario: Registered extension resolves an artifact

- **WHEN** an extension is registered and an eligible installed plugin supplies its artifact
- **THEN** artifact resolution returns provider-bound references and transient resolved paths through the extension contract

#### Scenario: Unknown extension

- **WHEN** a caller requests resolution or policy changes for an unregistered artifact extension
- **THEN** Zuat reports an unknown extension without modifying plugin or policy state

### Requirement: Safe runtime artifact resolution

Artifact resolution SHALL use a verified installed plugin root from the agent's current native evidence. Returned paths SHALL resolve within that root, including after resolving symbolic links and traversal segments. Missing roots, escaping paths, unavailable plugins, and stale exact-revision references SHALL return explicit unresolved or rejected results. Available catalog entries alone SHALL NOT be treated as installed artifact providers.

#### Scenario: Escaping extension result

- **WHEN** an extension returns a path whose resolved target lies outside the verified plugin root
- **THEN** Zuat rejects that path and does not expose or ingest the external contents

#### Scenario: Plugin root moves

- **WHEN** a plugin revision remains installed but its native runtime directory changes
- **THEN** a fresh resolution uses the current verified root without depending on a persisted runtime path

#### Scenario: Stale revision reference

- **WHEN** a contribution reference targets version A but the installation now contains version B
- **THEN** exact resolution reports the stale reference rather than returning B's contents as A

### Requirement: Artifact policy and effective status

Artifact status SHALL report requested policy, effective resolution eligibility, and the reason for that outcome separately. Policies SHALL support `inherit`, `enabled`, and `disabled`; clearing a policy SHALL restore `inherit`. Policy SHALL be scoped by agent, canonical plugin ID, installation context, and artifact identifier, surviving version changes without losing revision-specific contribution provenance. Explicit native disablement SHALL always prevent effective activation; `enabled` SHALL NOT override it. Where native activation is unknown, eligibility SHALL follow the agent's verified capability rules and SHALL NOT claim native execution is enabled.

#### Scenario: Enabled policy cannot override native disablement

- **WHEN** a natively disabled plugin has artifact policy enabled
- **THEN** status reports the requested policy but effective resolution remains disabled with the native restriction as its reason

#### Scenario: Policy survives upgrade without leaking across scopes

- **WHEN** an installation with disabled artifact policy upgrades from A to B
- **THEN** its policy remains disabled, contribution references identify B, and another installation scope retains its own policy

#### Scenario: Clear policy

- **WHEN** a caller clears a plugin's artifact policy
- **THEN** subsequent status and resolution use inherited native eligibility rather than the cleared override

### Requirement: Resolution policy is not native mutation

Zuat artifact policy SHALL control Zuat's artifact resolution only unless a separately requested supported native operation changes native state. Policy changes SHALL append safe metadata-only domain history. Discovering, resolving, or suppressing a plugin contribution SHALL NOT rewrite its source files or imply that the agent stopped executing its native skill or hook.

#### Scenario: Disable Zuat artifact resolution

- **WHEN** a caller disables an artifact whose plugin remains natively enabled
- **THEN** Zuat omits that artifact from eligible resolution, records the policy transition, and leaves native plugin state and contents unchanged
