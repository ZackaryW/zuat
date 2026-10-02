# installed-skill-lookup Specification

## Purpose

Let callers locate the installed skill an explicit coding agent selects for an invocation context, using verified native selection behavior, without creating or changing any Zuat or native state.

## Requirements

### Requirement: Lookup is an explicit, read-only public query

Zuat SHALL provide a public skill lookup that accepts an explicit agent, a declared skill name, an invocation directory, an optional native home, and optional caller selection evidence. Lookup SHALL NOT require an existing Zuat registry. Lookup SHALL NOT create, initialize, or modify registry, journal, observation, ownership, or control state; SHALL NOT install, adopt, update, remove, repair, copy, or execute skills; SHALL NOT run native agent commands or fetch remote sources; and SHALL NOT modify native agent or consumer configuration. Repeated lookups of unchanged native state SHALL return equal results without persisted cache state.

#### Scenario: Lookup without a registry

- **WHEN** a caller looks up an installed user-level skill with a disposable home and no Zuat registry
- **THEN** the skill is located and every file and directory entry, including absent registry and control paths, is unchanged after the lookup

#### Scenario: Repeated lookup

- **WHEN** a caller performs the same lookup twice against unchanged native state
- **THEN** both results are equal and no lookup-created state exists afterward

### Requirement: Lookup reports one classified outcome

Each lookup SHALL return exactly one outcome: located, missing, unresolved, unsupported, or invalid. A located result SHALL identify the agent, declared skill name, canonical installed skill root, entrypoint, scope, provider, and how selection was established. Results that are not located SHALL NOT identify a selected root and SHALL include diagnostics naming the relevant identity and paths. Expected lookup outcomes SHALL be returned as results rather than raised as errors.

#### Scenario: Missing skill

- **WHEN** no searched location contains a skill with the requested declared name
- **THEN** the outcome is missing with a diagnostic naming the agent and requested skill

#### Scenario: Unsupported agent

- **WHEN** a caller supplies an agent identity Zuat does not support
- **THEN** the outcome is unsupported and no agent's skill locations are searched

### Requirement: Identity uses the declared skill name

Lookup SHALL match a skill by the name declared in its `SKILL.md` metadata, which MAY differ from its directory name. Lookup SHALL read only the metadata needed to establish identity and selection and SHALL NOT read or fingerprint other skill resources. A located result SHALL identify the complete installed skill root so its supporting resources remain accessible.

#### Scenario: Declared name differs from folder name

- **WHEN** a skill in folder `review-helper` declares the name `pspec-review` and the caller requests `pspec-review`
- **THEN** that skill is located with its folder as the installed root

### Requirement: Search follows the agent's native locations from the invocation directory

Each agent SHALL search its own documented skill locations relative to the explicit home and invocation directory, including project locations in the invocation directory and its ancestors up to the repository root where the agent searches them. Lookup SHALL NOT search other agents' locations unless the requested agent natively reads them. Project-level results SHALL reflect the invocation directory supplied for that lookup.

#### Scenario: Project skill from a subdirectory

- **WHEN** a project skill is installed at the repository root and the caller looks it up from a subdirectory of that repository
- **THEN** the project skill is located

#### Scenario: Two projects share one user installation

- **WHEN** two projects without project-level copies look up the same user-level skill from their own invocation directories
- **THEN** each lookup locates the shared user installation and reports no project-level candidate from the other project

### Requirement: Same-named copies are selected only by verified native behavior or evidence

When more than one searched location contains the requested skill, lookup SHALL select a copy only by caller selection evidence, by the requested agent's verified native selection rule, or by native configuration that excludes all but one copy. Otherwise the outcome SHALL be unresolved and list every candidate. Zuat's recorded installation scope or profile SHALL NOT influence selection. Native rules SHALL be: Claude prefers a user copy over a project copy; Kimi prefers a project copy over a user copy; Codex SHALL NOT choose between same-named copies unless its native configuration disables all but one; Pi SHALL report unresolved.

#### Scenario: Claude user and project copies

- **WHEN** Claude has the requested skill in both its user and project skill locations
- **THEN** the user copy is located with native-rule provenance

#### Scenario: Kimi user and project copies

- **WHEN** Kimi has the requested skill in both its user and project skill locations
- **THEN** the project copy is located with native-rule provenance

#### Scenario: Codex copies without evidence

- **WHEN** Codex has the requested skill in two searched locations and neither is disabled in native configuration
- **THEN** the outcome is unresolved and lists both candidate paths

#### Scenario: Codex copy disabled natively

- **WHEN** Codex has the requested skill in two searched locations and native configuration disables one of them
- **THEN** the enabled copy is located with native-configuration provenance

#### Scenario: Profile scope does not decide

- **WHEN** the selected Zuat profile records a project installation of a Codex skill that also exists at user level
- **THEN** the outcome remains unresolved

### Requirement: Caller selection evidence is validated

When a caller supplies the installed path the host selected, lookup SHALL locate that path only if it is a candidate for the requested agent and invocation context and declares the requested name, and SHALL report caller-evidence provenance. Otherwise the outcome SHALL be invalid and SHALL NOT substitute another candidate.

#### Scenario: Evidence selects a copy

- **WHEN** a Codex skill exists in two locations and the caller supplies the path of one of them
- **THEN** that copy is located with caller-evidence provenance

#### Scenario: Evidence outside the candidates

- **WHEN** the caller supplies a skill path that the requested agent does not search for that invocation directory
- **THEN** the outcome is invalid and no other copy is returned

### Requirement: Unverifiable selected installations are invalid

A skill directory that the agent could select under the requested name but whose `SKILL.md` is missing, unreadable, or malformed SHALL make the outcome invalid, identifying that path. Broken skills that cannot be the requested skill SHALL NOT affect the lookup.

#### Scenario: Malformed candidate

- **WHEN** the folder named for the requested skill has `SKILL.md` without valid metadata
- **THEN** the outcome is invalid and identifies that folder

#### Scenario: Unrelated broken skill

- **WHEN** an unrelated skill in the same location has malformed metadata and the requested skill is valid
- **THEN** the requested skill is located

### Requirement: Symbolic links and providers follow native support

Symlinked skill folders SHALL be resolved only for agents that natively support them, with the canonical target reported as the installed root and the native location retained as provenance. For other agents a symlinked candidate SHALL produce an unsupported outcome with a diagnostic. Plugin-provided skills SHALL NOT be reported as independent installations; lookup by plugin-qualified name SHALL be unsupported.

#### Scenario: Claude symlinked skill

- **WHEN** a Claude user skill folder is a symbolic link to a skill directory elsewhere
- **THEN** the skill is located with the link target as its root and the link location in its provenance

#### Scenario: Plugin-qualified name

- **WHEN** a caller requests a plugin-qualified skill name
- **THEN** the outcome is unsupported with a diagnostic

### Requirement: Unmodeled native locations are not ignored

When a native location the agent searches but Zuat does not model exists and could contain the requested skill, lookup SHALL NOT report a located result that such a location could change; the outcome SHALL be unresolved with a diagnostic naming that location.

#### Scenario: Codex admin location present

- **WHEN** Codex's admin skill location exists and contains a folder matching the requested skill, and one user copy exists
- **THEN** the outcome is unresolved and names the admin location
