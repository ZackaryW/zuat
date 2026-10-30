# Spec Delta

## MODIFIED Requirements

### Requirement: Same-named copies are selected only by verified native behavior or evidence

When more than one searched location contains the requested skill, lookup SHALL select a copy only by caller selection evidence, by the requested agent's verified native selection rule, or by native configuration that excludes all but one copy. Otherwise the outcome SHALL be unresolved and list every candidate. Zuat's recorded installation scope or profile SHALL NOT influence selection. Native rules SHALL be: Claude prefers a user copy over a project copy; Kimi and Antigravity prefer a project copy over a user copy; Codex SHALL NOT choose between same-named copies unless its native configuration disables all but one; Pi SHALL report unresolved.

#### Scenario: Claude user and project copies

- **WHEN** Claude has the requested skill in both its user and project skill locations
- **THEN** the user copy is located with native-rule provenance

#### Scenario: Kimi user and project copies

- **WHEN** Kimi has the requested skill in both its user and project skill locations
- **THEN** the project copy is located with native-rule provenance

#### Scenario: Antigravity user and project copies

- **WHEN** Antigravity has the requested skill in both its user and project skill locations
- **THEN** the project copy is located with native-rule provenance

#### Scenario: Antigravity copies in several user directories

- **WHEN** Antigravity has the requested skill in two of its user directories, such as the unified and legacy ones, and no project copy
- **THEN** the outcome is unresolved and lists both candidate paths

#### Scenario: Antigravity copies at several project levels

- **WHEN** Antigravity has the requested skill in the project directories of two ancestor levels of the invocation directory
- **THEN** the outcome is unresolved and lists both candidate paths

#### Scenario: Codex copies without evidence

- **WHEN** Codex has the requested skill in two searched locations and neither is disabled in native configuration
- **THEN** the outcome is unresolved and lists both candidate paths

#### Scenario: Codex copy disabled natively

- **WHEN** Codex has the requested skill in two searched locations and native configuration disables one of them
- **THEN** the enabled copy is located with native-configuration provenance

#### Scenario: Profile scope does not decide

- **WHEN** the selected Zuat profile records a project installation of a Codex skill that also exists at user level
- **THEN** the outcome remains unresolved

### Requirement: Unmodeled native locations are not ignored

When a native location the agent searches but Zuat does not model exists and could contain the requested skill, lookup SHALL NOT report a located result that such a location could change; the outcome SHALL be unresolved with a diagnostic naming that location.

#### Scenario: Codex admin location present

- **WHEN** Codex's admin skill location exists and contains a folder matching the requested skill, and one user copy exists
- **THEN** the outcome is unresolved and names the admin location

#### Scenario: Antigravity declared skill directory

- **WHEN** an Antigravity `skills.json` visible from the invocation directory declares a directory containing a folder matching the requested skill, and one project copy exists
- **THEN** the outcome is unresolved and names the declared directory

#### Scenario: Antigravity declaration cannot be read

- **WHEN** an Antigravity `skills.json` visible from the invocation directory is not valid JSON
- **THEN** the outcome is unresolved with a diagnostic naming that file rather than a located result
