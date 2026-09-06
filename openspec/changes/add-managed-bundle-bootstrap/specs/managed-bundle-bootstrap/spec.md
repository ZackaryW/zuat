## Purpose

Let applications build portable skill repositories into registered plugins and explicitly bootstrap or replace them on supported agents without managing private files or a desired-state reconciliation system.

## ADDED Requirements

### Requirement: Build registered plugins from skill sources

The public interface SHALL build a named bundle from a local directory or an explicitly selected Git source and revision, recursively discovering valid skills and preserving their support files. Builds SHALL use isolated source material, deterministic content evidence, collision-safe identities and bounded validation. Invalid frontmatter, duplicate normalized skill names, escaping paths, links, reparse points and unsupported special files SHALL fail without changing source files or replacing an existing valid build. Building SHALL NOT install or execute source-provided code. Equivalent content and rendering inputs SHALL reuse the existing build rather than create another revision.

#### Scenario: Build without installation

- **WHEN** a source contains nested skills and their support files and the caller requests a build
- **THEN** a registered immutable build contains those skills and compatible plugin metadata without modifying the source or invoking native installation

#### Scenario: Invalid or colliding source

- **WHEN** the selected source is unsafe, has colliding skill identities, or attempts to claim another source's bundle name
- **THEN** build fails while preserving existing registrations and valid outputs

#### Scenario: Repeated equivalent build

- **WHEN** the same source is rebuilt with identical content and rendering inputs
- **THEN** the same build revision is returned without replacing its files

### Requirement: Private registry with public handles

Bundles SHALL be registered in a private `.zuat` store, defaulting to the user's home with an explicit bundle-root override. Public operations SHALL provide build, get/list, runtime build resolution, bootstrap and remove access through typed identifiers and results so applications and extensions need not construct paths or edit registry files. Bundle identity, build revision and per-agent installation records SHALL be separate. A native installed revision SHALL remain identified by agent kind, canonical plugin ID and observed version, separately from the build's proposed metadata. Reopening a selected store SHALL preserve registrations; malformed state SHALL fail explicitly rather than trigger reset or adoption. Existing Git registry locations SHALL remain unchanged.

#### Scenario: Extension uses an alternate store

- **WHEN** an application builds a bundle under an explicit root and a later service instance retrieves and resolves that build by its public handle
- **THEN** it obtains the same registration and validated transient output path without inspecting private files or touching the default store

#### Scenario: Build is not installed evidence

- **WHEN** a build proposes a native plugin name and version but no native installation has been verified
- **THEN** registry queries show the build as available without claiming an installed exact plugin revision or native activation

#### Scenario: Missing build output

- **WHEN** a registered build's output has been deleted or no longer matches its recorded content
- **THEN** runtime resolution or bootstrap reports it unavailable or invalid without silently rebuilding, substituting another revision or installing it

### Requirement: Explicit agent bootstrap

Bootstrap SHALL attempt installation of a selected registered build on explicitly selected agents, or supported available agents when selection is omitted. Each selected target SHALL have an independent result. Required managed-catalog setup SHALL be performed automatically through supported native mechanisms without changing unrelated entries. Direct-source installation SHALL require explicit source trust, independently of force. Unsupported managers, source forms and scopes SHALL produce explicit non-success outcomes; bootstrap SHALL NOT silently fall back to loose-skill installation or editing native manager internals. The initial bundle lifecycle SHALL be user-scope only. Success SHALL require fresh native evidence of the target installation, keeping version certainty and activation separate. A matching installed build SHALL be a no-change outcome based on current evidence, not only on a cached successful result.

#### Scenario: Bootstrap supported targets

- **WHEN** a caller bootstraps a trusted build on supported available agents
- **THEN** the required managed catalog and installation are established, verified and reported separately for each agent

#### Scenario: Unsupported target and successful neighbor

- **WHEN** one explicitly selected agent lacks supported plugin bootstrap while another can install the build
- **THEN** the result reports the unsupported target and the other target's actual outcome without a grouped-skill fallback or undoing successful work

#### Scenario: Force without source trust

- **WHEN** bootstrap requests force but omits required trust for the generated local source
- **THEN** it rejects before destructive replacement or installation

#### Scenario: Agent still uses an earlier build

- **WHEN** source content is unchanged but a selected agent is absent or still uses an earlier build
- **THEN** an explicit bootstrap uses that agent's current evidence and attempts the requested install or update instead of skipping because compilation was unchanged

### Requirement: Bounded forced replacement without reconciliation

For an existing selected managed installation, bootstrap SHALL attempt a supported targeted update or report that update is unsupported. Without force, it SHALL NOT delete the installation as a fallback. With explicit force, an unsupported or failed update SHALL permit removal of only the unambiguously registered installation, verification of its absence, and one replacement installation attempt. Force SHALL NOT bypass identity, containment, source trust or native capability checks, or authorize broad directory deletion. Failure after removal SHALL report the target as absent or indeterminate according to observed evidence and retain enough registration information for a later explicit call. No bundle operation SHALL promise automatic retry, continuous convergence, compensating rollback or a cross-agent transaction.

#### Scenario: Update failure without force

- **WHEN** a supported update fails and force is false
- **THEN** bootstrap reports the observed failed or indeterminate outcome without invoking fallback removal

#### Scenario: Forced replacement succeeds

- **WHEN** update is unsupported or fails for an unambiguously registered target and explicit force and required trust are supplied
- **THEN** bootstrap removes only that target, verifies absence, attempts installation once and reports its verified result while preserving unrelated assets

#### Scenario: Replacement installation fails

- **WHEN** forced removal succeeds but replacement installation fails
- **THEN** bootstrap reports the resulting absent or indeterminate installation and retains the bundle registration without restoring the previous build or scheduling retries

#### Scenario: Ambiguous or foreign target

- **WHEN** a matching name refers to an unregistered or ambiguous native installation
- **THEN** bundle force rejects destructive replacement rather than taking ownership or deleting by name alone

### Requirement: Explicit removal and truthful stored outcomes

Bundle removal SHALL target only its registered installations for the selected agents, verify absence, and preserve unrelated plugins, global declarations and other bundle registrations. Failed, interrupted or unverified operations SHALL remain distinguishable from success after reopening the store; reopening or listing SHALL NOT automatically resume mutation. The bundle SHALL remain registered while any target remains installed or unresolved; it SHALL be unregistered only after all registered targets are verified absent. Listing SHALL distinguish last recorded outcomes from freshly verified native state. Removing registration SHALL NOT rewrite existing journal history or promise retained builds are rollback points.

#### Scenario: Partial removal

- **WHEN** removal succeeds for one registered agent but fails for another
- **THEN** the bundle stays registered with distinct target outcomes and the failed target is not represented as absent

#### Scenario: Restart after interruption

- **WHEN** execution stops during a bootstrap attempt and the registry is reopened
- **THEN** queries report an interrupted or unverified attempt without repeating native commands or claiming successful installation

### Requirement: Self-contained extension-facing operations

Public bundle operations SHALL work without the optional CLI or predecessor packages. The optional CLI SHALL expose build, list/status, bootstrap and remove using the same public operations, including explicit agents, source trust, force and bundle-root selection where applicable. Python hosts and explicitly invoked Zuat extensions SHALL be able to compose public bundle operations with artifact resolution without constructing internal plans, loading arbitrary extension code through the CLI, or depending on the `.zuat` layout. Registering an extension SHALL NOT implicitly build or bootstrap a bundle or grant trust; those operations SHALL remain explicit public calls.

#### Scenario: Base-only consumer

- **WHEN** a caller builds, retrieves and bootstraps a bundle using the installed base package and an isolated supported native boundary
- **THEN** the workflow works without Click, Typer, agent-bundler or agent-router and without manual private-state access

#### Scenario: Equivalent CLI operation

- **WHEN** the CLI extra is installed and equivalent bundle requests are issued through Python and the CLI
- **THEN** both expose equivalent per-agent domain outcomes and neither exposes internal Git controls

#### Scenario: Extension composes bundle operations explicitly

- **WHEN** a host explicitly invokes extension code that builds and bootstraps a bundle through public APIs with a selected store and agent set
- **THEN** it receives ordinary bundle handles and per-agent results under the same trust and force rules, without accessing private registry files or treating extension registration as installation permission
