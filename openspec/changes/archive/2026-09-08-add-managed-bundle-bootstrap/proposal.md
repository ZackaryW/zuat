## Why

Zuat can manage installed agent assets but cannot yet form a plugin from a skill repository and bootstrap it through a small public API. Migrating agent-bundler's useful compiler behavior lets applications and future extensions delegate this work without depending on agent-router or manipulating private storage.

## What Changes

- Add local/Git skill-source compilation into registered, immutable, agent-compatible bundle builds.
- Add build, get/list, bootstrap and remove operations under `zuat.pub`, with optional Click commands using those same APIs.
- Add one-call build/bootstrap, read-only build/manager diagnostics, and opt-in generated-output cleanup after complete removal, without reconciliation or automatic garbage collection.
- **BREAKING** Replace the artifact-only `ArtifactExtension` class and `register_artifact` entry points with a subclassable public `ZuatExtension` contract and `register_extension` entry points, without legacy aliases. Artifact location becomes an optional capability while existing artifact resolution, containment, eligibility and policy behavior are preserved.
- Keep extension identifier and contract version separate from native plugin identity and version. Extensions compose public bundle and lifecycle APIs rather than edit `.zuat`; registration alone does not install plugins, execute lifecycle callbacks, grant trust or persist extension code. No automatic extension loader or reconciliation callbacks are introduced.
- Keep a private bundle registry and generated outputs in `.zuat`; expose typed handles and runtime resolution rather than a public filesystem schema. Do not relocate the existing Git registry.
- Bootstrap selected agents through their native adapters, with explicit source trust and per-agent results. On an explicit forced replacement, allow bounded removal followed by installation; report failure without automatic convergence or compensating rollback.
- Separate stable bundle identity and build revision from native `(agent_kind, plugin_id, version)` evidence. Generated build outputs are not installed-state evidence.
- Narrow the durable-plugin-content restriction to permit Zuat's compiler output store, while retaining reference-only observation, profile, journal and recovery records.
- Migrate capabilities, not dependency or compatibility layers. Exclude grouped-skill fallback, automatic retry, desired-state reconciliation, guaranteed bundle rollback, hooks, overlays and public publishing.

## Capabilities

### New Capabilities

- `managed-bundle-bootstrap`: Public plugin building, private bundle registration, agent bootstrap and explicit bounded replacement/removal.

### Modified Capabilities

- `plugin-revision-tracking`: Permit isolated compiler outputs without admitting plugin bodies or runtime paths into lifecycle tracking state.
- `plugin-contribution-resolution`: Generalize explicit runtime extension registration to `ZuatExtension` with optional artifact location, retaining existing provider-aware artifact resolution and policy guarantees.
- `plugin-command-surface`: Replace artifact-only registration with general public extension registration while preserving explicit lifecycle operations and the optional CLI boundary.

## Impact

- Focused `pub/bundles/` operations and public models; neutral source/discovery/storage helpers in `utils`; separate native rendering and bootstrap behavior in agent-specific `specs` modules.
- Public extension types, registration and artifact dispatch; existing Python consumers, examples and tests move directly to `ZuatExtension` without an `ArtifactExtension` compatibility shim.
- Optional Click bundle commands; base Python operation remains CLI-independent. No agent-bundler, agent-router or Typer dependency.
- Nested pytest coverage and an isolated public consumer workflow; existing plugin, asset and journal guarantees remain regression requirements.
- No changes to agent-bundler, ZPP, real agent homes, or existing registry layouts during implementation tests.
