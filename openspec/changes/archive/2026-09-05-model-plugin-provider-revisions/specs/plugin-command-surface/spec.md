## Purpose

Provide simple public plugin discovery, lifecycle, and artifact operations with verified agent-native outcomes and explicit unsupported capabilities.

## ADDED Requirements

### Requirement: Public plugin operations

The supported Python interface SHALL provide installed plugin discovery, explicit available-catalog discovery, install, update, remove, artifact extension registration, artifact resolution, artifact status, and artifact policy set and clear operations. The optional CLI SHALL expose plugin discovery, lifecycle, artifact status, and artifact policy operations through the same public interface. Neither surface SHALL require callers to construct internal reconciliation plans or manipulate Git state. Artifact extension registration SHALL be available to Python hosts without requiring a CLI mechanism that loads arbitrary Python code.

#### Scenario: Plugin lifecycle through the public interface

- **WHEN** a caller installs a supported plugin, queries it, updates it, and removes it through public operations
- **THEN** each result exposes typed installation and revision evidence with the verified domain outcome

#### Scenario: CLI and Python parity

- **WHEN** equivalent plugin lifecycle requests are issued through Python and the installed CLI extra
- **THEN** they use the same public orchestration and produce equivalent domain outcomes

### Requirement: Installed and available discovery are distinct

Discovery SHALL list installed plugins by default. An explicit available-catalog request SHALL query supported configured native catalogs and distinguish available entries from installed state. Discovery SHALL NOT install or activate plugins. Unsupported catalog discovery, missing managers, malformed inventory, and failed queries SHALL be reported distinctly from a successful empty inventory; partial installed results SHALL not imply a successful catalog query.

#### Scenario: Available plugin is not installed

- **WHEN** explicit catalog discovery finds a plugin absent from installed state
- **THEN** the result labels it available without adding it to installed observations or profiles

#### Scenario: Empty inventory versus failure

- **WHEN** installed discovery fails because its native manager cannot be invoked
- **THEN** the result reports discovery failure rather than a successful empty plugin list

### Requirement: Explicit trust for direct installation sources

Installation SHALL accept supported native references and optional source routing separately from exact revision identity. Direct URL, Git, and local sources, including relative local paths and supported non-HTTP Git forms, SHALL require explicit source trust before native execution. Ambiguous or unsupported source forms SHALL be rejected rather than treated as trusted catalog IDs. Trust SHALL NOT be inferred from forced reconciliation or a matching display name, and credentials SHALL NOT enter durable records.

#### Scenario: Relative local source without trust

- **WHEN** installation targets a direct relative filesystem source without explicit trust
- **THEN** Zuat rejects it before invoking the native mutation

#### Scenario: Trusted source resolves to canonical identity

- **WHEN** a supported trusted direct source is installed and native rediscovery supplies canonical ID and version evidence
- **THEN** the result and durable revision reference use the canonical identity rather than treating the source locator as its version

### Requirement: Independent project configuration trust

Public Python and CLI operations SHALL accept explicit project-configuration trust, disabled by default, independently of plugin-source trust and forced reconciliation. Native operations that require project trust SHALL reject its absence before mutation. Discovery that excludes an untrusted project's plugins SHALL report incomplete scope coverage rather than plugin absence. Project trust SHALL apply only to the explicitly selected project and SHALL NOT be persisted as permission for later operations. A source-targeted update that cannot isolate the requested installation SHALL be rejected before mutation.

#### Scenario: Force and source trust do not approve a project

- **WHEN** a caller provides force and plugin-source trust but omits required project trust
- **THEN** project plugin mutation is rejected without native execution

#### Scenario: Untrusted project inventory is incomplete

- **WHEN** native discovery excludes project configuration because project trust is false
- **THEN** Zuat reports incomplete project coverage and does not record previously observed project plugins as removed

#### Scenario: Explicit project trust

- **WHEN** a caller explicitly trusts project A for a supported operation
- **THEN** the native request uses project A and does not approve project B or future requests

### Requirement: Agent-specific operation capabilities

Each agent SHALL determine supported plugin operations, installation scopes, source forms, activation evidence, and exact-revision acquisition. Requests SHALL be validated against those capabilities before mutation. Project-scoped operations SHALL execute against the selected project context and agent configuration root, not an incidental process directory or another agent's state. Unsupported capabilities SHALL be explicit and SHALL NOT fall back to copying plugin sources or editing native manager internals.

#### Scenario: Discovery-only agent

- **WHEN** a lifecycle mutation targets an agent with discovery-only plugin support
- **THEN** Zuat reports the unsupported mutation and leaves its inventory and source state unchanged

#### Scenario: Scope restriction

- **WHEN** install or removal targets a native managed scope that disallows that operation
- **THEN** Zuat rejects the operation before invoking any native mutation, even if another operation is supported in that scope

#### Scenario: Project isolation

- **WHEN** an operation targets project A while the process was started in project B
- **THEN** only project A's supported installation context is used and project B remains unchanged

### Requirement: Verified targeted lifecycle operations

Install, update, and remove SHALL verify their requested postconditions through fresh native discovery. Update SHALL target an existing canonical plugin identity in the selected installation context and report its before and after revision evidence. Removal SHALL verify absence in that context. A plugin need not be natively active to be confirmed installed, and unknown versions SHALL not be reported as verified version changes. These operations SHALL NOT intentionally mutate unrelated plugin installations or global declarations.

#### Scenario: Installed but disabled

- **WHEN** an installation request is followed by authoritative evidence that the plugin is installed but natively disabled
- **THEN** the result reports verified installation and separately reports disabled activation without claiming the plugin is running

#### Scenario: Update cannot establish revision

- **WHEN** an update command completes but native evidence cannot establish the resulting version
- **THEN** Zuat reports the observed installation and unresolved revision outcome without claiming a verified upgrade or exact recovery point

#### Scenario: Remove one scope

- **WHEN** a plugin is removed from a selected project installation while also installed for the user
- **THEN** removal verifies project absence and preserves the user installation and unrelated global skills and hooks

### Requirement: Optional CLI and self-contained runtime

Plugin Python operations SHALL work without the CLI dependency installed. Installing `zuat[cli]` SHALL enable the CLI; invoking the console entry point without that extra SHALL provide concise installation guidance without an import traceback. The plugin implementation SHALL be self-contained and SHALL NOT depend on agent-router packages, legacy state readers, or backward-compatibility shims.

#### Scenario: Python-only installation

- **WHEN** a caller imports the public interface and uses plugin discovery without the CLI extra
- **THEN** the operation does not require Click or an agent-router package

#### Scenario: Missing CLI extra

- **WHEN** the console command is invoked without its optional dependency
- **THEN** it exits with concise guidance to install the CLI extra without an import traceback
