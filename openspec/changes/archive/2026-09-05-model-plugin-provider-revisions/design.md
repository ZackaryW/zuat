## Context

See [proposal.md](proposal.md) for motivation and the three capability specs for behavioral contracts. This design is required because plugin identity crosses discovery, public helpers, journal serialization, profile reconciliation, and recovery.

The current implementation already has native adapters, but `specs/base.py` writes complete plugin records into normalized asset JSON. `specs/plugins.py` carries raw native evidence and saves it through ownership records. `pub/service.py` and `gitcore/repository.py` use generic payload archiving and inverse-profile paths for assets, including plugins. Adding plugin convenience calls alone would retain those persistence problems. The current public selector also cannot distinguish global from plugin providers.

## Goals / Non-Goals

**Goals:**

- Separate transient native evidence from safe durable domain state at the first observation boundary.
- Reuse the existing operation lock, domain history, and profile coordination while giving plugin pointers a distinct storage and reconciliation path.
- Keep public operations simple and each agent responsible for native semantics; avoid another large orchestration module.

**Non-Goals:**

- A plugin source cache, marketplace hosting service, universal native namespace, or plugin execution runtime.
- Making every agent support every operation or inventing exact-version installation where its native manager cannot provide it.
- Independent edits to bundled files, a CLI for loading arbitrary Python extensions, or a general plugin dependency solver.
- Agent-router dependencies, old-format readers, compatibility aliases, or rewriting existing history to claim it never contained source data.

## Decisions

### 1. Use a small explicit revision model, not a new identity framework

Introduce an immutable exact revision value with only `agent_kind`, canonical `plugin_id`, and opaque `version`. A separate installation value contains scope, project context when applicable, presence, activation, authority, and an optional resolved revision. Unresolved evidence is a status on that installation, not a revision with a fake version. Validate native types rather than coercing arbitrary objects into identity strings.

A plugin contribution reference adds `kind` and a provider-local contribution ID to the revision. Installation context remains alongside it. Global providers retain their existing native declaration identity. Artifact policies use the stable agent/plugin pair plus installation context and artifact ID so upgrades do not reset policy; contribution references still pin their actual revision.

Source input is not revision identity. If a direct local source has no safe canonical native ID or verifiable version, retain an unresolved observation and diagnostic rather than persist its filesystem path as an exact reference. Source-based reacquisition that needs a local path requires fresh caller input.

Alternative rejected: extending the existing hashed asset reference with a version string while continuing to treat its JSON file as content. That would conflate revision, installation, and payload and retain the generic archive problem.

### 2. Split durable plugin pointers from global content payloads

Represent persisted asset state as explicit variants: global declaration payload or plugin installation/contribution pointer. Plugin branches never call generic source-tree copying, content fingerprinting, or payload archive functions. Profile and observation projections keep the existing four agent directories; plugin entries are inspectable pointer records under the relevant installation context, not duplicated plugin directories.

Use an allowlisted serializer for plugin state at every write boundary: observation, catalog/provenance, profile, event before/after, event metadata, and recovery marker. Store canonical references, presence, activation, authority, contribution IDs, policies, domain outcomes, and safe source routing metadata only. Reject invalid durable records; do not serialize arbitrary `native_evidence`, request dictionaries, exception strings, or subprocess output. Allowlisted strings still need validation: credentials and local runtime paths cannot become safe merely by occupying an allowed field.

Transient discovery contexts carry verified runtime roots and native evidence only in memory. Native output is converted into structured diagnostic codes and safe summaries before any journal/recovery write. Artifact paths can be returned to a caller as transient resolution results but are never reused as durable plugin evidence. Unknown fields are not silently carried into ownership stores or caches.

Alternative rejected: redacting a few fields from today's `to_dict()` output. An allowlist and separate runtime type are easier to audit and do not leak newly added native fields by default.

### 3. Keep native lifecycle and contribution semantics with each agent

Define the shared plugin protocol and capability values alongside resolver contracts in `specs/interface.py`. Keep agent-specific implementations with their agent modules, extracting focused companion modules if needed rather than collecting all agents' policy in `specs/plugins.py`. Share subprocess execution, source validation primitives, containment checks, and serialization mechanics through domain-focused `utils` modules only.

Capabilities describe operation-by-scope support, installed and available discovery, accepted reference forms, activation evidence, and exact-version acquisition. They are not one broad scope set reused for all operations. Preserve the existing conservative boundaries: Codex user scope, Pi user/project scope, Kimi discovery-only, and Claude scope-specific restrictions including managed-scope install/remove rejection. Verify concrete command forms and any managed update support against native evidence during implementation; unsupported or unverified forms return explicit capability errors.

Adapters derive the actual native configuration root from the supplied user home and pass the chosen project root explicitly as subprocess working directory. They own namespace interpretation, installed-root validation, contribution manifests, and native precedence. Generic code does not decide that every same-named contribution is a collision.

Approved clarification (2026-09-05): expose independent `trust_project=False` on public service/context and plugin requests, with `--trust-project` on the CLI. It authorizes native project-configuration trust for the selected project only and is not persisted as a reusable permission. Source `trust` and reconciliation `force` remain separate. Pi passes an explicit trust override, never relies on prompting or incidental saved trust. Without project trust, project inventory is incomplete, not absent, and project mutations fail before execution. User-scoped Pi mutations ignore project configuration even in a trusted service. Project update is rejected when the native source-based command could also update another installation. Recovery and profile operations require fresh trust and must preserve unobserved state.

Installed, active, and exact-version-known are independent dimensions. For example, partial activation evidence does not by itself disprove installation. Verification evaluates the requested postcondition rather than requiring an `ACTIVE` flag for every operation.

Alternative rejected: a generic manager that branches on agent name and normalizes every native installation into a shared directory format. This loses native isolation and repeats the earlier rejected design.

### 4. Add focused public orchestration instead of growing the facade

Expose typed plugin requests/results and reference values from `zuat.pub`. Add focused public orchestration modules for plugin lifecycle and artifact operations; `Zuat` and module-level convenience functions delegate to them. Internal adapters never import the public facade. Use existing shared operation coordination rather than opening nested registry operations from convenience wrappers.

The public surface includes `discover_plugins(include_available=False)`, `install_plugin`, `update_plugin`, `remove_plugin`, artifact extension registration, `resolve_artifacts`, `artifact_status`, `set_artifact_policy`, and `clear_artifact_policy`. Installation accepts native input and a separate optional exact revision request; update/remove address an installation, with an optional expected revision to detect stale callers. Results separate native outcome, installation evidence, revision certainty, and safe diagnostics.

Extend asset selectors with explicit provider fields and route existing `list_assets`, `adopt_all`, `uninstall_all`, and `restore_all` through provider-aware dispatch. An all-provider listing does not imply every listed contribution is independently mutable. Preflight the complete selected mutation set before changing anything; unsupported bundled targets produce a diagnostic rather than implicit plugin removal. Adoption records pointers and provenance without importing bundled content.

Add a thin `plugin` CLI group for `discover --available`, `install`, `update`, `remove`, and artifact `status` and `set` operations; setting `inherit` clears an override. Handlers call only `zuat.pub`. Keep Click in the existing optional extra and preserve Python-only use.

Alternative rejected: telling callers to construct temporary profiles and generic asset plans for routine plugin operations. Those remain internal mechanisms, not the usability surface.

### 5. Reuse append-only coordination with pointer-specific reconciliation

The lifecycle sequence is: observe targeted native state; validate scope, authority/force, source trust, and requested revision; record safe recovery intent; invoke the supported manager; rediscover; publish only verified state; append the domain outcome. If mutation or verification fails, capture the actual known state and leave an honest recovery outcome. Do not treat a successful command exit as convergence.

For update, preserve before/after revision pointers on the same installation. Catalog refresh is allowed as part of a native targeted update, but do not intentionally bulk-update unrelated installations. Direct-source trust is an explicit independent input, including supported relative paths and Git SSH forms; force never supplies it.

Profile switch, revert, and bulk restore dispatch global assets to existing payload restoration and plugins to exact-reference resolution. Preflight all required exact acquisitions before mutation. No known exact acquisition path means explicit unsupported/unavailable, not an unpinned install. Where a native manager cannot preflight remote availability, surface that uncertainty and do not promise atomic restoration. A later partial failure must not mark the target profile fully applied.

An interrupted operation retains safe before and intended references. Recovery rediscoveries occur through the public orchestration/agent boundary, not inside a Git-only repository constructor. Reopening storage can identify pending work; native recovery establishes and appends its result without blindly replaying an install or erasing the earlier operation. Compensation itself is another verified forward transition and can fail if an old version is no longer obtainable.

Alternative rejected: recovering plugins from archived files or resetting private Git state. Neither establishes native-manager state and both contradict the pointer-only model.

### 6. Resolve artifacts transiently and report policy honestly

Use an in-process extension registry with an identifier, extension contract version, and locator callback accepting immutable installed-plugin context. Registration is trusted host Python code; containment validation constrains returned paths, not the callback's arbitrary execution. Do not auto-import extensions named in plugin manifests.

For each resolution, rediscover the installation, validate the requested revision if supplied, obtain its current verified root, compute native eligibility, apply the policy, then canonicalize and confine locator results to that root. Missing roots, traversals, symlink escapes, and stale revisions yield explicit diagnostics. Available catalog entries cannot provide runtime artifacts. Return paths without opening or storing artifact bodies.

Policy `disabled` suppresses Zuat resolution; `enabled` cannot override native disablement; `inherit` defers to adapter eligibility. Unknown activation can permit generic resolution only where the adapter has verified installed-root eligibility, without claiming native execution. Record policy changes as metadata-only domain events, independently for each installation context.

Alternative rejected: copying plugin contributions into global skill/hook folders or treating artifact policy as native enablement. That changes the agent's own behavior and breaks isolated plugin ownership.

## Risks / Trade-offs

- Native managers omit versions or exact acquisition features -> expose unresolved/unsupported results; never manufacture precision.
- Catalogs and source access can change after preflight -> verify after mutation and retain honest partial recovery evidence.
- Native output and errors can contain secrets or source bodies -> isolate transient types, validate durable fields, and test every persistence sink including failure paths and private Git history.
- Existing generic helpers assume every asset has a payload -> exercise mixed global/plugin operations before accepting the change, not only new convenience methods.
- Moving plugin roots or concurrent native changes can stale evidence -> re-resolve before use, reverify after mutation, and reject stale exact references.
- Per-agent behavior requires more adapter tests -> share mechanics only; this is preferable to a universal mode switch that silently changes semantics.

## Migration Plan

1. Implement and verify against fresh isolated registries and agent homes. Leave real user installations untouched unless separately requested.
2. Replace the current plugin representation and route all existing plugin entry points through pointer-only paths. No compatibility readers, duplicate APIs, or dependency on agent-router are added.
3. Do not silently open incompatible plugin records as valid pointers or rewrite old history. Report incompatible state with guidance to use a fresh registry; never delete an existing registry automatically. The new persistence guarantee applies to newly produced state, not retrospectively to earlier Git objects.
4. Keep this change's new plugin contracts separate from the earlier foundation artifacts. Do not sync superseded plugin requirements into canonical specs. Complete implementation and verification before any later archive/sync step.
5. Rollback of package code does not roll back native installations. Reconcile any native changes explicitly through supported public operations, preserving their append-only outcomes.
