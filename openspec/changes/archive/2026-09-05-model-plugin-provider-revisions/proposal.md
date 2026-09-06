## Why

Zuat currently treats installed plugins as generic declarations, leaving plugin-specific public operations incomplete and failing to distinguish plugin-provided skills and hooks from global declarations. Plugins need explicit revision identity and reference-only persistence so Zuat can track their lifecycle and contributions without ingesting their source content.

## What Changes

- **BREAKING** Identify an exact plugin revision by `(agent_kind, plugin_id, version)`. Preserve the canonical agent-native plugin ID, including its namespace where applicable, and treat versions as opaque values. Installation scope and profile selection are separate from revision identity; upgrades record a transition between revisions of the same agent/plugin pair.
- **BREAKING** Persist plugin references and narrowly defined state metadata in observations, profiles, journal events, and recovery records. Exclude plugin source trees, bundled skill/hook bodies, runtime payloads, raw native-manager output, runtime paths, and credentials from durable plugin records and payload archives.
- Model both global declarations and installed plugins as providers of skills and hooks. Retain provider identity when names overlap; plugin contributions reference their exact plugin revision and contribution identifier. Discovering a contribution does not turn it into a copied global asset or imply that it can be independently mutated.
- Add provider-aware listing and selection to the public helper operations. Preserve each agent's native activation, scope, namespace, and collision semantics; report unsupported contribution operations explicitly instead of editing plugin-managed contents.
- Complete the supported plugin Python and CLI surfaces: installed discovery, explicit available-catalog discovery, installation by native reference with explicit trust for direct sources, update, and removal. Keep native lifecycle support agent-specific and verify outcomes through rediscovery.
- Restore generic artifact extension registration, contribution resolution, status, and `inherit`/`enabled`/`disabled` policy operations. Policy cannot override native disablement, and resolving artifact paths does not persist or copy their contents.
- Make profile reconciliation and restoration resolve recorded plugin revision pointers through supported native managers. Missing version evidence or an unavailable exact revision must be reported explicitly; Zuat must not silently substitute the latest version or claim an exact restore it cannot verify.
- Preserve forward-appended domain history and the separation between source trust and forced reconciliation. Global skill/hook content continues to use the existing content snapshot model; plugin-owned content follows the reference-only rule.
- Require independent, explicit project-configuration trust (`trust_project=False` by default) where native plugin operations read or modify trusted project state. Incomplete untrusted project discovery is reported rather than interpreted as absence; source trust and force never imply project trust.

## Capabilities

### New Capabilities

- `plugin-revision-tracking`: Plugin revision identity, scope-specific installation state, reference-only persistence, and verifiable profile/recovery transitions.
- `plugin-contribution-resolution`: Global and plugin provider provenance, revision-bound skill/hook and generic artifact references, provider-aware selection, and effective contribution policy.
- `plugin-command-surface`: Public Python and optional CLI discovery, trusted installation, update, removal, and artifact operations backed by agent-specific lifecycle capabilities.

### Modified Capabilities

None in the canonical catalog, which is currently empty. These capabilities refine the plugin portions of the active `establish-zuat-foundation` artifacts and the archived `add-convenience-asset-helpers` artifacts. Those earlier artifacts remain historical context; this separate change records the replacement plugin behavior without promoting their superseded requirements into canonical specs.

## Impact

- `src/zuat/pub/`: plugin request/result contracts, lifecycle orchestration, provider-aware helpers, and artifact policy APIs.
- `src/zuat/specs/`: per-agent plugin discovery and lifecycle support, revision evidence, contribution discovery, and native capability reporting.
- `src/zuat/gitcore/`: reference-only plugin projections and journal/recovery serialization, integrated with existing profiles and append-only operations.
- `src/zuat/utils/`: reusable reference validation, safe artifact resolution, and serialization mechanics.
- `src/zuat/cli/`: thin Click adapters calling only `zuat.pub`; Click remains optional.
- Tests: red-first behavioral coverage for provider isolation, public plugin workflows, persistence exclusions, native restrictions, and recovery outcomes. End-to-end checks use isolated agent state.
- Zuat remains self-contained. Agent-router is a migration reference only; this change adds no dependency on it, legacy state readers, or backward-compatibility layer.
