# Tasks

Each implementation task is red-green: add the focused failing test, confirm it fails for the intended reason, then implement until it passes.

## 1. Public boundary and no-side-effect harness

- [x] 1.1 Add a `tests/pub/lookup/` package with a fixture that builds a disposable home and project and a helper that snapshots every file and directory entry, including absent registry and control paths; verify the helper detects a deliberately created file in a self-test
- [x] 1.2 Add the frozen `SkillLocation` result and a `locate_skill(agent, name, *, cwd, home=None, selected=None)` export in `zuat.pub` that returns `unsupported` for unknown agents and plugin-qualified names without scanning; verify with tests that importing and calling it does not import `zuat.pub.service` or `zuat.gitcore` and leaves the snapshot unchanged

## 2. Agent-neutral skill identity and matching

- [x] 2.1 Add a frontmatter-only skill identity reader in `utils/` that reads only `SKILL.md` and reuses the existing frontmatter parser; verify with tests that it returns the declared name, never opens other skill files, and reports missing, unreadable, non-UTF-8, and malformed metadata distinctly
- [x] 2.2 Add the agent-neutral upward walk from an invocation directory to the repository root (`.git` file or directory, else the invocation directory alone); verify with tests for a subdirectory, a worktree-style `.git` file, and no repository
- [x] 2.3 Add candidate matching across ordered tiers: match by declared name, treat a folder-name match with unverifiable metadata as invalid, ignore unrelated broken entries, and follow symlinks only for tiers that allow them; verify with tests for renamed folders, unrelated broken skills, and symlinked candidates in allowed and disallowed tiers
- [x] 2.4 Add agent-neutral outcome classification for `prefer-tier`, `ambiguous`, caller evidence, and unmodeled-location shadowing, returning provenance and the candidate list; verify with table-driven tests covering each outcome and provenance value

## 3. Agent lookup policies

- [x] 3.1 Add a lookup method to the shared resolver contract and implement Claude tiers (user, project levels from cwd to repository root, symlinks followed), user-over-project preference, ambiguous same-level project copies, and an injectable managed-settings location reported as unmodeled; verify with resolver tests using disposable homes
- [x] 3.2 Implement Codex tiers (`.agents/skills` from cwd to repository root, `~/.codex/skills`, `~/.agents/skills`, symlinks followed), the ambiguous policy, read-only `[[skills.config]]` disable evidence from `config.toml`, and an injectable admin location reported as unmodeled; verify with tests for no-evidence ambiguity, one disabled copy, and malformed config yielding unresolved
- [x] 3.3 Implement Kimi tiers (project root as nearest `.git` ancestor: `.kimi-code/skills`, `.agents/skills`; user: `~/.kimi-code/skills`, `~/.agents/skills`), project-over-user preference, ambiguous same-scope copies, and `extra_skill_dirs` from config reported as unmodeled; verify with resolver tests
- [x] 3.4 Implement Pi tiers (`~/.pi/agent/skills`, `~/.agents/skills`, `.pi/skills`, `.agents/skills` from cwd to repository root) with the ambiguous policy; verify with resolver tests that same-named copies are unresolved and symlinked candidates are unsupported
- [x] 3.5 Verify lookup methods never construct ownership stores, plugin adapters, or subprocesses by running every agent's lookup with a process runner and store factory that fail on use

## 4. Public behavior and documentation

- [x] 4.1 Add public API tests in `tests/pub/lookup/` for each spec scenario: no registry, repeated lookup, missing, unsupported agent, declared-name mismatch, subdirectory invocation, two projects sharing a user skill, Claude and Kimi native rules, Codex ambiguity and native disable, profile scope not deciding, accepted and rejected caller evidence, malformed and unrelated broken skills, Claude symlink provenance, plugin-qualified name, and Codex admin shadowing; verify each passes and the snapshot is unchanged after every lookup
- [x] 4.2 Document `locate_skill` in README with supported agents, verified sources and date, selection rules, how to supply `selected`, outcome meanings, limitations (plugins, Claude nested and session-time skills, unmodeled locations, Pi order), and a runnable disposable-home example; verify by running the example as written

## 5. Integration

- [x] 5.1 Run `uv run --extra cli pytest -q` and `uv run --extra cli behave --format progress` and verify existing lifecycle, observation, and plugin tests pass unchanged
- [x] 5.2 Run `openspec validate add-installed-skill-lookup --strict` and record the final public import, signature, result contract, and pinned commit for the Powerspec handoff
