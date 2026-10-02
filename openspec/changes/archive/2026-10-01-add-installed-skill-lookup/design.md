# Design

## Context

See proposal.md - Why. Relevant current state:

- `zuat.pub` entrypoints all open `Zuat`, which constructs `GitRegistry` (initializes Git, layout, and an `zuat:initialize` commit). `ResolverSupport.observe` creates the agent registry tree, and `observe_skills` mirrors every skill into it and prunes absent ones.
- Agent resolvers are cheap to construct: `ResolverSupport.__init__` only resolves paths, and plugin adapters and ownership stores are created lazily. A resolver can therefore be built with only `home` and used for lookup without binding a registry, as long as lookup never calls `bind`, `plugins`, or `observe`.
- `load_skill` rejects symbolic links, collects every file, and fingerprints the skill. `_frontmatter` already parses and validates `SKILL.md` YAML frontmatter.
- Each resolver models one user skill root and one project skill root at a fixed `project_root`, which is not how hosts search.

Native behavior verified against host documentation on 2026-10-01:

| Agent | Searched skill roots (from invocation directory) | Same name across roots | Symlinked skill folders |
|---|---|---|---|
| Claude Code ([skills](https://code.claude.com/docs/en/skills)) | managed `.claude/skills`; `~/.claude/skills`; `.claude/skills` in cwd and each parent up to the repository (worktree) root | enterprise > personal > project; plugin skills are namespaced; nested subdirectory skills load later in a session | supported |
| Codex ([skills](https://learn.chatgpt.com/docs/build-skills)) | `.agents/skills` in cwd, parents, repository root; `~/.codex/skills` and `~/.agents/skills`; `/etc/codex/skills`; bundled | not merged, both appear in selectors; `[[skills.config]] path=... enabled=false` in `config.toml` disables a copy | supported |
| Kimi Code ([skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)) | project root = nearest `.git` upward from cwd: `.kimi-code/skills`, `.agents/skills`; `$KIMI_CODE_HOME/skills` (`~/.kimi-code/skills`), `~/.agents/skills`; `extra_skill_dirs`; built-in | project > user > extra > built-in | not documented |
| Pi ([skills](https://hochej.github.io/pi-mono/coding-agent/skills/)) | `~/.pi/agent/skills`, `~/.agents/skills`, `.pi/skills`, `.agents/skills` in cwd and ancestors to git root; packages; settings; `--skill` | first found wins with a warning; traversal order not verified against source | not documented |

## Goals / Non-Goals

**Goals:**
- One pure lookup path from public API to filesystem reads, with no registry, store, or subprocess on it.
- Agent-specific roots and selection policy stay in the agent resolvers; matching and outcome classification stay agent-neutral.
- Every outcome is a returned value with actionable diagnostics, so Powerspec never needs to catch internal exception types.

**Non-Goals:**
- Plugin-provided skill lookup or plugin-qualified names.
- Claude nested subdirectory skills, `--add-dir`, `/cd`, and other session-time discovery.
- Modeling managed or admin locations, Kimi `extra_skill_dirs`, Pi packages or settings, or bundled built-in skills as candidates.
- Changing lifecycle observation paths, the symbolic-link exclusion for observation and mutation, or adding a CLI command.

## Decisions

### Separate read path, not a read-only mode of observation

Lookup gets its own function in `zuat.pub` that builds a resolver with `resolver_for(agent, home=...)` and calls only new lookup methods. It does not import `zuat.pub.service` or `zuat.gitcore`.

Alternative: a `dry_run` flag on `observe`. Rejected because observation is entangled with mirroring, pruning, plugin discovery subprocesses, and ownership stores; a flag would make the no-write guarantee depend on every branch honoring it.

### Resolver exposes search tiers and a selection policy

Each resolver adds a lookup method returning, for an invocation directory and home:

- ordered tiers, each with scope (`user` or `project`), root paths, whether symlinked skill folders are followed, and a stable tier label;
- the agent's policy for same-named matches in different tiers: `prefer-tier` (an ordered tier preference), `first-found`, or `ambiguous`;
- known unmodeled locations that might hold a same-named skill (for example Claude managed settings, Codex `/etc/codex/skills`, Kimi `extra_skill_dirs` from `config.toml`).

The upward walk from cwd to the repository root is an agent-neutral helper parameterized by the root marker (`.git` file or directory). The tier list and policy are the agent's.

Policies in this change:

- Claude: `prefer-tier` user over project; project tiers are cwd and each parent to the repository root. Same name in two project levels is `ambiguous`, since the documentation only defines nested-name namespacing for subdirectory skills.
- Kimi: `prefer-tier` project over user. Within one scope, `.kimi-code/skills` and `.agents/skills` collisions are `ambiguous` (not documented).
- Codex: `ambiguous`, with native disable evidence (below).
- Pi: `ambiguous` in this change. The documented rule is first-found, but its order is unverified; promoting Pi to `first-found` requires a source-verified order and is a follow-up.

Alternative: a universal precedence in shared code. Rejected; the hosts disagree (Claude user-first, Kimi project-first, Codex none).

### Codex native disable evidence

The Codex resolver reads `[[skills.config]]` entries from `~/.codex/config.toml` (read-only, with the existing TOML reader) and drops candidates whose `SKILL.md` path is disabled. If exactly one candidate remains, it is located with `native-config` provenance. An unreadable or malformed config yields `unresolved` when it could change the answer, never a guess.

### Caller selection evidence is a path

`selected` is an installed skill directory or `SKILL.md` path. Lookup resolves it, requires it to be one of the agent's candidates for that invocation directory with a matching declared name, and returns it with `caller-evidence` provenance. A path that is not a candidate, or whose declared name differs, is `invalid`; lookup never substitutes another copy.

Alternative: a scope enum. Rejected because install scope does not determine host selection and cannot distinguish two project levels or two user roots.

### Frontmatter-only identity and targeted scanning

An agent-neutral reader opens only `<candidate>/SKILL.md`, parses frontmatter with the existing parser, and returns the declared name and `compatible_agents`. Because the declared name may differ from the folder name, each tier root is scanned one level deep, but a candidate's errors only matter when it could be the requested skill: its folder name equals the requested name, or its frontmatter parses with that name. Other broken entries are ignored silently.

A candidate that matches by folder name but has missing, unreadable, or malformed `SKILL.md` makes the result `invalid` with that path, because the host may select it and Zuat cannot confirm identity.

### Symbolic links follow the agent's documented support

Tiers marked as following symlinks (Claude, Codex) resolve symlinked skill folders and report the canonical target as the root, keeping the native locator as provenance. Other agents treat symlinked candidates as `unsupported` with a diagnostic rather than silently skipping a copy the host might load. This is lookup-only; observation keeps its exclusion.

### Result value

A frozen `SkillLocation` exported from `zuat.pub` with: `outcome` (`located`, `missing`, `unresolved`, `unsupported`, `invalid`), `agent`, `name`, `root`, `entrypoint`, `scope`, `provider` (`global` for independent skills, matching existing provider vocabulary), `provenance` (`single-candidate`, `native-rule`, `native-config`, `caller-evidence`), `candidates` (tier label and path for each match), and `diagnostics`. Location fields are `None` unless located. An unknown agent returns `unsupported` without scanning any agent.

## Risks / Trade-offs

- [Host documentation drifts from host behavior] → Record verified sources and date in the spec and README; each policy is a small per-agent table that is easy to revise.
- [An unmodeled location shadows the returned copy] → Probe known unmodeled locations and return `unresolved` when one exists and could hold the name; document the remaining unknowns (bundled skills, plugin roots).
- [Scanning a large skills root for a renamed skill is slow] → Frontmatter-only reads; folder-name match first; no resource collection.
- [Pi and ambiguous cases return `unresolved` more often than users expect] → Diagnostic lists every candidate path so the caller can pass one as `selected`.
- [Lookup accidentally constructs a registry or store] → Tests snapshot all paths, including absent registry and control paths, before and after lookup, and run with no registry present.

## Migration Plan

Additive public API; no stored state or existing behavior changes. Rollback is removing the export.
