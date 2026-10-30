# Tasks

## 1. Verify native assumptions (spike, before code)

- [x] 1.1 On a machine with agy, in a throwaway home and project, check whether the IDE and the CLI each load a skill from `~/.gemini/config/skills` and from `<project>/.agents/skills`; record the result in `design.md` D4 and verify by updating D4 and the matching spec scenarios if the CLI does not read `config/skills`
- [x] 1.2 Check that a named entry in `~/.gemini/config/hooks.json` and in `<project>/.agents/hooks.json` is loaded and that a second, unrelated named entry coexists; record in `design.md` D8 and verify D8 is confirmed or project hooks are set to unsupported in the specs
- [x] 1.3 (manifest precedence and list shape verified; the `config.json` override left documented-only, see `design.md`) Check `config.json` `plugins.<dir>.enabled` against `plugin.json` `disabled` precedence and plugin directory-name identity with `agy plugin list --json`; verify the plugin requirement scenarios match the observed result

## 2. Extract the hook-document strategy (no behavior change)

- [x] 2.1 Add characterization tests pinning current Codex, Claude, and Kimi shared-hook inspect/install/update/remove/restore outcomes; verify they pass on the unchanged code
- [x] 2.2 Introduce the hook-document strategy interface and move the existing fragment logic (`exact_group`, `selected_fragment`, `resolve_hook_group`, shared-hook observe/apply) behind it, selected by `ResolverSupport` from the resolver; verify the 2.1 tests and the full existing pytest and Behave suites still pass unchanged and no shared module references an agent identity

## 3. Keyed hook strategy

- [x] 3.1 Write failing pytest tests for the keyed classifications (absent, current, outdated, conflict, unowned, indeterminate for non-object document, non-object entry, and duplicate key) using a temporary home; verify they fail for the missing behavior
- [x] 3.2 Implement the keyed strategy with an `object_pairs_hook` duplicate-key parse and the `<name>.json` single-key source loader; verify the 3.1 tests pass
- [x] 3.3 Write failing then passing tests that install, update, restore by operation identifier, and remove a keyed hook while unrelated named entries and other top-level settings stay semantically unchanged, including removal of the last entry leaving `{}`; verify interrupted-update recovery still reports a pending operation ID
- [x] 3.4 Add observation tests that an unowned entry is reported as an unauthoritative asset with locator `hooks/<name>`; verify via `list_assets`

## 4. Antigravity resolver

- [x] 4.1 Add `ANTIGRAVITY` to `Agent`, register `AntigravityResolver` in `specs/registry.py`, and append `"antigravity"` to `SUPPORTED_AGENTS`; verify `resolver_for("antigravity")` works and an unsupported name still raises
- [x] 4.2 Write failing tests for user skills at `<home>/.gemini/config/skills/<name>` and project skills at `<project>/.agents/skills/<name>`, including project isolation, no project root rejection, and a legacy-directory copy left untouched; implement the resolver paths and verify they pass
- [x] 4.3 Wire user (`~/.gemini/config/hooks.json`) and project (`.agents/hooks.json`) hook scopes to the keyed strategy; verify a Powerspec-shaped `powerspec.json` hook installs, reports current on reinspect, and is isolated per project
- [x] 4.4 Verify `ZuatRequest` default agents, CLI `--agent` choices, and the CLI help list now include `antigravity`, and that an explicit Codex-only request leaves Antigravity paths unmodified (isolation test)

## 5. Skill lookup

- [x] 5.1 Write failing `locate_skill` tests for located single copy, project-beats-user, copies in two user directories (unresolved), copies at two project levels (unresolved), symlink (unsupported), malformed candidate (invalid), and caller-selected evidence; implement `skill_search` for Antigravity and verify they pass
- [x] 5.2 Write failing tests for `skills.json` declared directories (workspace and global, `inherits` chain, cycle, malformed file, repo-root-relative and `~/` paths) producing unresolved with the named location; implement the conservative declared-directory tiers and verify they pass

## 6. Plugin discovery

- [x] 6.1 Write failing tests using fixtures modeled on the real layout (`config/plugins/<dir>/plugin.json`, `config.json` `plugins` map): enabled by default, manifest `disabled`, config override, missing version evidence, malformed `config.json` making discovery incomplete and suppressing plugin-owned skill ingestion; implement `AntigravityPluginAdapter` and verify they pass
- [x] 6.2 Add tests for contribution inventory (`skills/*/SKILL.md`, root `hooks.json` names), rejection of independent mutation of a contribution, and unsupported install/update/remove/preflight; verify each raises the unsupported-operation error and no files change
- [x] 6.3 Verify bundle build/bootstrap/doctor with Antigravity selected alone and with Claude: Antigravity is `unsupported`, no loose-skill fallback, and Claude's outcome is independent

## 7. Documentation and integration

- [x] 7.1 Update `README.md` (agent roster, lookup table row for Antigravity, plugin and bundle capability notes, default fan-out note) and verify every documented example still runs
- [x] 7.2 Add `examples/antigravity_lifecycle.py` using a temporary home and project to install, inspect, update, restore, and remove a skill and a keyed hook; verify it exits zero with `python examples/antigravity_lifecycle.py`
- [x] 7.3 Run the full pytest and qualifying Behave suites and `openspec validate add-antigravity-agent --strict`; verify both are green, then record the verified Zuat revision for the Powerspec pin

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Bump the Zuat pin in Powerspec (`support-antigravity-hooks`) to the archived revision.
