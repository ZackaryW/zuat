# Proposal

## Why

Powerspec (`pspec skill <name> --agent <agent>`) must read the exact installed skill an agent invocation uses, but Zuat cannot answer "which installed copy does this agent select here?" without writing state. Every public inspection path opens or initializes the Git registry and mirrors observed skills into it, the inventory reports same-named user and project copies without saying which one the host selects, and project discovery checks one fixed folder rather than the locations hosts actually search from the invocation directory.

## What Changes

- Add a public, registry-independent `locate_skill` lookup in `zuat.pub` that takes an explicit agent, declared skill name, invocation directory, optional injectable native home, and optional caller-supplied selection evidence.
- Return one small frozen result distinguishing located, missing, unresolved selection, unsupported, and invalid outcomes, with the selected root, entrypoint, scope, provider, selection provenance, candidate paths, and diagnostics.
- Give each agent resolver an explicit, side-effect-free description of the skill roots it searches from an invocation directory, including documented shared `.agents/skills` locations, and of its native same-name selection policy.
- Apply only verified native selection policy: Claude prefers the user copy over the project copy, Kimi prefers the project copy over the user copy, Codex never chooses between same-named copies unless native configuration disables all but one, and Pi remains unresolved until its traversal order is verified.
- Accept a caller-supplied installed path as selection evidence, validated as a real candidate for the requested agent and context; an invalid path is reported, never replaced by another copy.
- Read only `SKILL.md` frontmatter to establish identity; do not collect or fingerprint skill resources.
- Report unresolved selection, rather than a located result, when a known native location Zuat does not model could hold a same-named copy.
- Lookup never initializes or updates a registry, records observations or receipts, runs native agent commands, or modifies native or consumer state.
- No change to existing lifecycle, observation, or plugin behavior; no CLI command in this change.

## Capabilities

### New Capabilities
- `installed-skill-lookup`: Read-only, registry-independent location of the installed skill an explicit agent selects for an invocation context, including native selection policy, caller evidence, outcome classification, and no-side-effect guarantees.

### Modified Capabilities
<!-- None. Existing observation and mutation requirements, including their symbolic-link exclusion, continue to govern asset observations and mutations; lookup is a separate read-only query under its own capability contract, as public-command-surface already permits for read-only queries. -->

## Impact

- `src/zuat/pub/`: new public function and result type, exported from `zuat.pub` without importing the service facade or Git registry.
- `src/zuat/specs/`: Claude, Codex, Kimi, and Pi resolvers gain skill search roots and selection policy; resolver construction for lookup must not require a registry or ownership store.
- `src/zuat/utils/`: agent-neutral frontmatter-only skill identity reading and candidate matching, reusing existing frontmatter parsing.
- Tests: new focused pytest coverage with disposable homes and projects, including before/after filesystem snapshots proving no lookup-created state.
- Downstream: Powerspec (`implement-skill-content-resolution`) consumes the result; Zuat takes no dependency on Powerspec or OpenSpec configuration.
- Documented limitations: plugin-provided skills, Claude nested subdirectory skills that load during a session, and unmodeled locations (Claude managed settings, Codex admin, Kimi extra directories, Pi package and settings skills) yield explicit diagnostics.
