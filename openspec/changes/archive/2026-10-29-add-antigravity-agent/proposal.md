# Proposal

## Why

Our team is adopting Google Antigravity (IDE and `agy` CLI), but Zuat can only manage Codex, Claude, Kimi, and Pi. Internal tooling built on Zuat, notably Powerspec, rejects `--agent antigravity` at the `SUPPORTED_AGENTS` check, so neither Powerspec nor OpenSpec skills can be deployed to it. Antigravity 1.4.x documents stable, file-based skill, hook, and plugin surfaces, so it can be modeled as a first-class Zuat agent now.

## What Changes

- Add an independent `antigravity` agent tree with its own resolver, selectable through every existing agent-parameterized public and CLI surface.
- Manage Antigravity skills at user scope (`~/.gemini/config/skills`) and project scope (`<project>/.agents/skills`), with the same ownership, inspection, update, restoration, and removal behavior other agents have.
- Manage Antigravity hooks in its `hooks.json` documents (`~/.gemini/config/hooks.json` for user scope, `<project>/.agents/hooks.json` for project scope). Unlike the other agents' array-in-shared-document hooks, Antigravity keys each hook by name, so the hook's name is its ownership identity. This needs a resolver-supplied keyed hook-document strategy beside the existing fragment strategy; Codex, Claude, and Kimi behavior is unchanged.
- Add Antigravity skill lookup (`locate_skill`) following its documented priority: project copies beat user copies; several copies in one scope, the legacy and CLI-specific user directories, and built-in or declared skills are never silently chosen.
- Add read-only Antigravity plugin discovery from `~/.gemini/config/plugins` and `config.json`. Install, update, remove, and bundle bootstrap are reported unsupported, as for Kimi.
- Add `antigravity` to `SUPPORTED_AGENTS`. Because omitted agent selections default to every supported agent, default-fan-out calls (for example `ZuatRequest` without `agents`, CLI commands without `--agent`) now also include Antigravity.

## Capabilities

### New Capabilities
- `antigravity-native-assets`: Antigravity's native skill and hook locations, keyed hook-document semantics, user/project scopes, read-only plugin discovery, and explicit unsupported plugin lifecycle and bundle bootstrap.

### Modified Capabilities
- `agent-asset-resolution`: the supported-agent roster and independent agent trees include Antigravity.
- `installed-skill-lookup`: adds Antigravity's native same-name selection rule and its unresolved cases.

## Impact

- New `src/zuat/specs/antigravity.py` and `antigravity_plugins.py`; registration in `specs/registry.py`; `Agent` enum in `specs/native.py`; `SUPPORTED_AGENTS` in `pub/models.py`.
- A keyed hook-document strategy threaded through `specs/base.py` (`ResolverSupport`), `utils/inspection.py`, and `utils/lifecycle.py`, selected by the resolver and never by agent identity, with a JSON hook loader in `utils/assets.py`.
- README and CLI help roster updates; new pytest coverage using temporary homes, plus a documented spike verifying the unverified native behaviors recorded in `design.md`.
- Downstream: Powerspec must pin a Zuat revision that includes this change before `pspec init --agent antigravity` can work (separate Powerspec change `support-antigravity-hooks`).
- Evidence caveat: native behavior is taken from Antigravity's own documentation and the agy 1.4.10 bundled customization guide, not yet from a verified run.
