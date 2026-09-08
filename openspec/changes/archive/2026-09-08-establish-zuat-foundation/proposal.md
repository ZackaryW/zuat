## Why

Zuat needs a domain-oriented foundation for managing heterogeneous coding-agent assets without exposing its storage machinery. A private append-only Git journal provides durable history, profiles, and reversibility while users work only with assets and lifecycle operations.

## What Changes

- Introduce a private Git-backed journal that automatically records changed observations and every install, uninstall, forced reconciliation, profile switch, and revert as a forward-appending commit.
- Keep private journal branches, indexes, commits, hashes, and refs entirely behind Zuat's public Python and CLI surfaces; caller-selected source provenance is a separate domain contract.
- Observe every manageable Codex, Claude, Kimi, and Pi asset, including existing fragments in shared native hook documents, and assign each a stable Zuat reference with agent, kind, scope, native locator, and fingerprint evidence.
- Distinguish authoritative profile state from unauthoritative native observations without preventing Zuat from managing either.
- Make `install` adopt or apply an asset into the selected profile and native surface, and make `uninstall` remove it from both through verified agent-specific lifecycles.
- Require an explicit force option when reconciliation overwrites or removes conflicting unauthoritative native state, and record that force decision in the journal.
- Implement revert as a new inverse operation and journal commit; never rewrite or erase operation history.
- Keep profiles user-visible as named desired states while hiding their internal Git representation.
- Establish `zuat.pub` as the supported public Python surface used by every optional Click handler, and reserve `zuat.utils` for internal reusable mechanics.
- **BREAKING**: Remove public staging, committing, Git working-tree status, branch terminology, snapshot recovery, and raw Git history from the Python and CLI contracts.

## Capabilities

### New Capabilities

- `git-profile-registry`: Private append-only operation journal, named profile state, automatic observation recording, forward-only revert, and internal recovery semantics.
- `agent-asset-resolution`: Independent agent trees, stable asset references, full manageable observation, and verified install, uninstall, force, and reconciliation behavior for Codex, Claude, Kimi, and Pi.
- `public-command-surface`: Domain-oriented Python operations and an optional noninteractive Click CLI that expose assets and lifecycle outcomes without private journal Git concepts. Read-only queries, bundles, and extensions retain their own typed contracts rather than inheriting a mandatory mutation pipeline.

### Modified Capabilities

None.

## Impact

- Adds package boundaries under `src/zuat/cli`, `src/zuat/pub`, `src/zuat/utils`, `src/zuat/specs`, and `src/zuat/gitcore`.
- Adds GitPython and PyYAML as base dependencies and Click only in the optional `cli` extra.
- Changes the `zuat` console entry point to an optional Click-backed command with graceful missing-extra guidance.
- Replaces the existing stage-and-commit public workflow with automatic journaling and domain operations for observation, installation, removal, profiles, history, and revert.
- Requires stable references for discovered skills, shared hook fragments, extensions, and plugin declarations, including content that Zuat did not install.
- Introduces application-data storage for the private journal and Zuat materialization metadata without placing registry state in user projects or native agent homes.
