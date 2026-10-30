# antigravity-native-assets Specification

## Purpose
Define how Zuat observes and manages Google Antigravity skills and hooks, discovers its plugins read-only, and reports the lifecycle operations Antigravity does not support, using Antigravity's own native locations and formats.

## Requirements

### Requirement: Antigravity skills use its documented skill locations
Zuat SHALL install, inspect, update, restore, and remove Antigravity skills at `~/.gemini/config/skills/<name>` for user scope and `.agents/skills/<name>` under the explicit project root for project scope. It SHALL NOT write the legacy `~/.gemini/antigravity/skills`, the CLI-specific `~/.gemini/antigravity-cli/skills`, or the alternate `.agent`, `_agents`, and `_agent` project directories.

#### Scenario: Install a user skill
- **WHEN** a valid skill is installed for Antigravity at user scope under an explicit home
- **THEN** its files appear under `<home>/.gemini/config/skills/<name>` with Zuat ownership recorded, and no other agent's tree changes

#### Scenario: Install a project skill
- **WHEN** a valid skill is installed for Antigravity at project scope with an explicit project root
- **THEN** its files appear under `<project>/.agents/skills/<name>` and the install is isolated from other projects

#### Scenario: Project scope without a project root
- **WHEN** a project-scope Antigravity skill operation supplies no project root
- **THEN** Zuat reports the operation unsupported or invalid and writes nothing

#### Scenario: Existing skill in a non-target directory
- **WHEN** the same skill name already exists in the legacy user directory
- **THEN** Zuat leaves that copy unchanged and does not claim it as owned

### Requirement: Antigravity hooks are named entries in a keyed hooks document
Zuat SHALL manage Antigravity hooks in `~/.gemini/config/hooks.json` for user scope and `.agents/hooks.json` under the explicit project root for project scope. Each document is a JSON object whose top-level keys are hook names. A hook source SHALL be a JSON file whose stem is the hook name and whose only top-level key is that same name.

#### Scenario: Install a hook into an absent document
- **WHEN** a valid hook source named `powerspec` is installed and the user-scope document does not exist
- **THEN** the document is created with a single top-level `powerspec` entry equal to the source's content, with ownership recorded

#### Scenario: Source identity mismatch
- **WHEN** a hook source file's stem differs from its only top-level key, or it has more than one top-level key
- **THEN** Zuat rejects the source before reading or writing the native document

#### Scenario: Preserve unrelated hooks
- **WHEN** the document already contains other named hooks and `powerspec` is installed
- **THEN** every other named hook, and every setting the document holds, remains semantically unchanged

### Requirement: Keyed hook ownership is decided by hook name
Zuat SHALL inspect an Antigravity hook by the entry at its name, with no positional or array-fragment matching. An absent name is absent. An entry with valid ownership whose content equals the source is current, equals only the owned baseline is outdated, and differs from the baseline is conflict. An entry without ownership is unowned even when its bytes match the source.

#### Scenario: Current owned hook
- **WHEN** the `powerspec` entry equals the source and Zuat owns it
- **THEN** inspection reports current and an update performs no write

#### Scenario: Outdated owned hook
- **WHEN** the owned `powerspec` entry still equals its recorded baseline and the source differs
- **THEN** inspection reports outdated and an unforced update replaces only that entry

#### Scenario: Locally edited owned hook
- **WHEN** the owned `powerspec` entry differs from both the baseline and the source
- **THEN** inspection reports conflict and an unforced update refuses to replace it

#### Scenario: Unowned matching entry
- **WHEN** a `powerspec` entry exists without Zuat ownership, even byte-identical to the source
- **THEN** inspection reports unowned and install requires the existing explicit adoption path

### Requirement: Keyed hook mutations touch only the owned entry
Install, update, restoration, and removal of an Antigravity hook SHALL change only the entry at the owned name. Removing the last entry SHALL leave a valid empty JSON object. Restoration SHALL recover the previous entry and receipt; an interrupted mutation SHALL remain visible with a recovery identifier.

#### Scenario: Remove one of several hooks
- **WHEN** an owned `powerspec` hook is removed from a document that also contains another named hook
- **THEN** only the `powerspec` entry is deleted and the other entry is unchanged

#### Scenario: Remove the only hook
- **WHEN** the sole owned entry is removed
- **THEN** the document remains a valid JSON object with no entries

#### Scenario: Restore after update
- **WHEN** an update is restored by its operation identifier
- **THEN** the entry and ownership receipt return to their pre-update values

### Requirement: Ambiguous keyed hook documents are indeterminate
Zuat SHALL report an Antigravity hook as indeterminate, and SHALL NOT mutate it, when the document is not a JSON object, the entry at the hook name is not an object, the name appears more than once, or ownership evidence is invalid. Force SHALL NOT override this classification.

#### Scenario: Duplicate key
- **WHEN** the document contains two `powerspec` keys
- **THEN** inspection reports indeterminate with diagnostics and install, update, and force all refuse to write

#### Scenario: Non-object document
- **WHEN** the native hooks document is a JSON array
- **THEN** inspection reports indeterminate and the file is not modified

### Requirement: Antigravity plugin discovery is read-only
Zuat SHALL discover installed Antigravity user plugins from `~/.gemini/config/plugins/<name>/plugin.json` and the `plugins` map in `~/.gemini/config/config.json` without executing any Antigravity command. A plugin is disabled when its `config.json` entry says so, otherwise when its manifest declares itself disabled. Unreadable or malformed inventory SHALL make discovery incomplete with diagnostics.

#### Scenario: Discover an enabled plugin
- **WHEN** a plugin directory has a valid `plugin.json` and no `config.json` entry
- **THEN** Zuat reports it installed and enabled with its manifest version

#### Scenario: Config overrides the manifest
- **WHEN** a plugin declares itself disabled but `config.json` records it enabled
- **THEN** Zuat reports it enabled

#### Scenario: Malformed inventory
- **WHEN** `config.json` is not valid JSON
- **THEN** discovery is reported incomplete and potentially plugin-owned skill directories are not ingested as global skills

### Requirement: Antigravity plugin contributions are inventoried, not independently managed
Zuat SHALL list the skills under a discovered Antigravity plugin's `skills/` directory and the hooks named in its root `hooks.json` as that plugin's contributions. Zuat SHALL NOT mutate a contribution independently of its plugin.

#### Scenario: Inventory plugin contributions
- **WHEN** a discovered plugin contains `skills/a11y/SKILL.md` and a root `hooks.json`
- **THEN** the skill and each named hook are reported with the plugin provider

#### Scenario: Mutate a contribution
- **WHEN** a caller tries to update or remove a plugin-provided skill as an independent asset
- **THEN** Zuat rejects the request and leaves the plugin unchanged

### Requirement: Unsupported Antigravity operations are explicit
Zuat SHALL report Antigravity plugin install, update, remove, exact-revision restoration, and managed bundle bootstrap as unsupported, without falling back to loose skills or to another agent's behavior. An Antigravity target SHALL NOT change the independent result of any other selected agent.

#### Scenario: Plugin install
- **WHEN** a caller requests an Antigravity plugin install
- **THEN** the result is unsupported and no native state changes

#### Scenario: Bundle bootstrap with a neighbor
- **WHEN** a bundle bootstrap selects Antigravity and Claude
- **THEN** Antigravity is reported unsupported with no loose-skill fallback and Claude reports its own actual outcome

#### Scenario: Antigravity explicitly selected for bundle diagnostics
- **WHEN** a caller explicitly selects Antigravity for bundle diagnostics
- **THEN** diagnostics reports Antigravity unsupported without attempting loose-skill installation
