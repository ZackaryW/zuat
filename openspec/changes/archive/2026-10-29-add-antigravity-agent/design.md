# Design

## Context

Zuat models each agent as a resolver in `specs/` over shared mechanics in `ResolverSupport` (`specs/base.py`). Skills are "dedicated" assets (a directory under a skills root). Hooks are "shared": ownership is a receipt plus a *fragment* matched inside a document the user also edits. That machinery assumes a `{"hooks": {Event: [entry, ...]}}` shape (or a list for Kimi) and hard-codes the `"hooks"` key in `utils/inspection.py` (`exact_group`, `selected_fragment`, `resolve_hook_group`), `utils/lifecycle.py`, and `load_json_hook` in `utils/assets.py`.

Antigravity's `hooks.json` has no wrapper: its top-level keys are hook names, each mapping events to handlers. See `proposal.md` for motivation. Native facts below come from the agy 1.4.10 bundled `agy-customizations` guide (`~/.gemini/antigravity/builtin/skills/agy-customizations/docs/`) and antigravity.google/docs; none has been run-verified yet.

| Surface | User scope | Project scope |
| --- | --- | --- |
| Skills | `~/.gemini/config/skills` (CLI: `~/.gemini/antigravity-cli/skills`, legacy: `~/.gemini/antigravity/skills`) | `.agents/skills` (also `.agent`, `_agents`, `_agent`), searched from cwd up to the repo root |
| Hooks | `~/.gemini/config/hooks.json` | `.agents/hooks.json` |
| Plugins | `~/.gemini/config/plugins/<dir>/plugin.json`, enablement in `~/.gemini/config/config.json` | `.agents/plugins` (not modeled) |

Documented priority: workspace project > declared (`skills.json`/`plugins.json`) > global > built-in. Symlink behavior and same-name behavior inside one tier are undocumented.

**Spike results (agy 1.4.10 CLI, 2026-10-29):** project-scope `.agents/hooks.json` loads and a named entry fires `SessionStart`, with the hook's working directory set to the `.agents` folder (confirms D8). A flat handler list is required; the grouped `matcher` form under `SessionStart` never runs, silently. Project skills load from all four spellings (`.agents`, `.agent`, `_agents`, `_agent` under `skills/`), including when launched from a subdirectory. A command quoted with backslashes never ran; relevant to hook content but not to Zuat's document handling. The global `~/.gemini/config/hooks.json` also loads and fires in the CLI, with its working directory set to `~/.gemini/config`. User skills: with temporary probe skills (since removed), the CLI listed skills from `~/.gemini/config/skills` and `~/.gemini/antigravity-cli/skills` but not from the legacy `~/.gemini/antigravity/skills`, which confirms D4's install target; lookup still searches the legacy directory because the IDE documents it. Plugins: `agy plugin list --json` reports user plugins only, with `name`, `enabled`, `version`, `source`, `path`, and `skills`; a workspace plugin whose manifest says `"disabled": true` exposed no skills, and an enabled plugin's skill appeared without a namespace prefix. Not tested: the IDE surface, and the `config.json` enablement override (it would mean editing the user's real settings).

## Goals / Non-Goals

**Goals:**
- Skills and hooks for Antigravity reach the same ownership, inspection, update, restoration, and removal guarantees as Claude and Codex, at user and project scope.
- Existing Codex, Claude, and Kimi hook behavior is byte-for-byte unchanged.
- Lookup never reports a confident wrong answer where Antigravity's own rules are undocumented.

**Non-Goals:**
- Antigravity plugin install/update/remove/bundle bootstrap (`agy plugin` exists, but this change is discovery only).
- Per-surface (IDE versus CLI) install targets; built-in skills; project-scope plugins.
- Anything Powerspec-specific such as hook content, response serialization, or workspace discovery (change `support-antigravity-hooks` in Powerspec).

## Decisions

### D1. Resolver-supplied hook-document strategy, not an agent switch
Extract the document-shape knowledge now spread across `inspection.py`, `lifecycle.py`, and the loaders behind a small strategy that the resolver passes to `ResolverSupport`: locate a hook's group in a document, test containment, put, delete, and enumerate observed hooks. Two implementations: *fragment* (the existing code moved behind the interface, behavior unchanged) and *keyed* (new). Shared code calls the strategy and never branches on agent identity, per project context.

Alternatives rejected: a lossy normalizing `read_document`/`write_document` view that flattens named hooks into `{"hooks": {Event: [...]}}` (it would drop names, the only real identity, and cannot split back safely); treating `hooks.json` as a dedicated whole file (would clobber hooks the user or other tools registered); packaging the hook as a plugin (needs the plugin lifecycle this change defers).

### D2. Keyed ownership is the hook name
Identity, locator (`hooks/<name>`), and receipt key are the name; there is no index. Classification (absent/current/outdated/conflict/unowned/indeterminate) reuses the existing vocabulary and receipt/baseline fingerprinting over the canonical JSON of the entry value. Positional locators cannot exist, which removes the duplicate/partial-group states the fragment strategy has to arbitrate. A duplicate key (detected with an `object_pairs_hook` parse, since stock `json` keeps the last silently) or a non-object entry is indeterminate and not force-overridable.

### D3. Hook source format
A source is `<name>.json` whose only top-level key equals its stem, so the file is exactly what lands in `hooks.json` and the existing name regex and identity checks apply. A `{"hooks": {...}}` wrapper was rejected: it would force Zuat to translate and hide the true identity.

### D4. Write to the unified `~/.gemini/config` root only
The customization guide calls `~/.gemini/config/` the global configuration applying to all projects; this machine's install keeps `config.json`, plugins, and MCP config there. The CLI-specific `antigravity-cli/skills` and legacy `antigravity/skills` are *searched* by lookup but never written. If the spike (task 1.1) shows the CLI does not read `config/skills`, a follow-up adds an explicit second target without touching ownership design, since paths are confined to the resolver.

### D5. Lookup search model
User tiers: `config/skills`, `antigravity-cli/skills`, `antigravity/skills`. Project tiers: each of `.agents`, `.agent`, `_agents`, `_agent` plus `/skills` at every level from the invocation directory to the repository root. `prefer=("project", "user")`; any other same-name collision is unresolved (Claude's two-project-level precedent). Symlinks are unsupported. Declared directories from `skills.json` (workspace `.agents*/skills.json` at each level and `~/.gemini/config/skills.json`) are *unmodeled* tiers: `entries` and `inherits` are expanded with a depth cap and cycle guard, `include_only`/`exclude` are ignored conservatively (a possible shadow counts), and unreadable or malformed files are blocking diagnostics. Built-in skills rank below global discovery and cannot shadow a user copy, so they are left unmodeled.

### D6. Plugin adapter reads files, never runs `agy`
Discovery scans `config/plugins/*/plugin.json` and the `plugins` map of `config.json`, so it works offline and without the CLI, as Kimi's does. Plugin identity is the directory name (the key `config.json` uses); `installedFrom` becomes source evidence. Enablement: `config.json` entry wins, else the manifest's `disabled`, else enabled. Contributions are `skills/*/SKILL.md` and hook names in the plugin-root `hooks.json`. All lifecycle methods raise the existing unsupported-operation error; `bundle_adapter()` returns `None`.

### D7. Roster and ordering
Add `ANTIGRAVITY` to `Agent` and the registry, and append `"antigravity"` to the end of `SUPPORTED_AGENTS` so existing default ordering is stable. Click choices, validation, and default fan-out read that tuple, so no per-command edits are needed.

### D8. Project hooks are enabled
Unlike Kimi, the guide documents `.agents/hooks.json`, so `project_hooks` is set. If the spike finds otherwise, set it to `None` as Kimi does; the requirement is one scenario.

## Risks / Trade-offs

- **Native behavior is documented, not observed** → Spike tasks 1.1-1.3 run before implementation; results are written back here and any divergence updates the specs before code.
- **Refactoring shared-hook code can regress Claude/Codex/Kimi** → Extract the fragment strategy first with the full existing suite green and no behavior change, then add keyed.
- **Default fan-out now touches Antigravity** (omitted `agents` installs into `~/.gemini/config` for users who never run it) → README and release note; callers wanting the old scope pass `agents` explicitly. Same exposure exists for Kimi today.
- **Rewriting `hooks.json` normalizes formatting** (`write_json` sorts keys) → semantic preservation is the contract, as for Claude settings; documented in the spec scenario.
- **The IDE or CLI may rewrite `hooks.json`/`config.json` concurrently** → existing publication-time recheck and pending-operation recovery apply unchanged.
- **Same-name behavior inside one tier is undocumented** → reported unresolved, never guessed.

## Migration Plan

Additive. First observation creates an `antigravity/` tree in the Git registry; nothing is written to Antigravity homes until an install is requested. Rollback is reverting the change; existing receipts for other agents are untouched. Powerspec bumps its Zuat pin only after this lands.

## Open Questions

- Should a later change add a CLI-specific skills target, depending on spike 1.1?
- Should project-scope plugin discovery (`.agents/plugins`) be added once a consumer needs it?
