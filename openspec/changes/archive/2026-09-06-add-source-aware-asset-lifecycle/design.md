## Context

See proposal.md for motivation. `pub/service.py` already coordinates generic installation and restoration, but its observation status is not a comparison against a caller's packaged source. `utils/lifecycle.py` contains useful native inspection primitives that are not public contracts. Ordinary observation paths and ownership keys include agent/scope/name but not project context; plugin records already use `utils/contexts.py` and context-scoped stores.

ZPP's inspected consumer boundary needs content-versus-baseline inspection and selected-asset updates, not an agent-router-shaped facade. Its ownership-safe predecessor migration and project `.gitignore` behavior are consumer policies and are not moved here. The active foundation change and archived plugin change remain intact.

## Goals / Non-Goals

**Goals:** Keep the public addition small, share one native inspection truth between inspection and mutation, and extend the existing project-context mechanism through every ordinary-asset persistence boundary. Reuse journal operations and existing restoration to make new updates recoverable.

**Non-Goals:** Modify ZPP, import old ownership receipts, recreate agent-router classes or command names, implement native plugin capabilities, add a second rollback engine, manage consumer `.gitignore`, or expand the CLI. This change alone does not certify the ZPP dependency cutover.

## Decisions

### 1. Add two source-aware Python operations

Expose `Zuat.inspect_asset(asset: AssetInput) -> AssetInspection` and `Zuat.update_asset(asset: AssetInput, *, force=False) -> OperationResult`, with module-level wrappers under `zuat.pub`. Limit them to independently managed `skill` and `hook` kinds. Require a valid source; resolve the target from agent-native source identity, scope and selected project, or validate an explicit asset reference against all those inputs. Conflicting source/name/reference combinations fail rather than select a different target.

`AssetInspection` is a frozen public result containing classification, agent/kind/name/scope, optional established asset reference, source/observed/baseline fingerprints, ownership evidence, source-match status, completeness and diagnostics. Classifications are `absent`, `current`, `outdated`, `conflict`, `unowned`, `unsupported`, and `indeterminate`. Missing evidence is represented explicitly, not through invented fingerprints or an absent classification. This is a Zuat result, not an alias for internal/native or agent-router types.

Keep existing `install`, `uninstall`, `restore_all` and selectors as the rest of the consumer API. Relevant module-level lifecycle helpers accept and forward `home`, `project_root` and `trust_project` consistently with the stateful service; omitted context keeps existing defaults. Demonstrate the full workflow without importing `zuat.specs` or constructing internal plans. Existing CLI handlers still call only public APIs; no new commands are necessary for this Python-consumer change.

Alternative rejected: eight agent-router-compatible skill/hook methods or teaching ZPP to read Zuat's private stores. A kind-bearing input covers both asset families while preserving the chosen public boundary.

### 2. Native inspection is targeted and non-authorizing

Add a bounded inspection contract to the resolver interface, implemented by each concrete agent using neutral source/baseline comparison mechanics. Compare observed content to the last established owned baseline first, then to the supplied source. A modified owned target remains `conflict` even if its bytes match a new package. A byte-identical foreign target remains `unowned`, with `source_matches=True`; adoption remains a separate operation.

Shared hooks must resolve declaration identity from a valid receipt and native fragment semantics, not merely array position, synthesized observation filename, or display name. Ambiguous matches and malformed receipts produce non-authorizing results. Preserve unsupported scopes, including agent-specific project-hook restrictions.

Do not implement inspection by unconditional whole-agent observation. A verified owned independent target can be inspected without a working plugin manager. Resolve provider eligibility before fingerprinting or archiving unknown candidates: unavailable plugin inventory must not turn possible plugin trees into global content. Where independence cannot be established, return indeterminate. Inspection itself does not adopt, rewrite a profile, or append a lifecycle mutation; unrelated broad observation retains conservative failure handling.

Alternative rejected: map general `status()` authority flags directly to source-relative states. It cannot distinguish an owned old package from an external edit reliably.

### 3. Explicit update reuses one operation coordinator

Use a focused public asset-operation module, with `Zuat` delegating to it, to avoid growing the facade further. Under the existing registry lock, resolve and inspect the current target, validate provider/scope/path/source and force policy, capture the actual before state, record safe recovery intent, perform native replacement, verify, publish the new profile/ownership state, and append the update result. Extract only the reusable coordination needed from current installation rather than wrap a public operation inside another locked public operation.

Update requires an existing target. `current` produces a no-change result (`data.changed=False`) without native replacement or a synthetic mutation; `outdated` is eligible by default; `conflict` and `unowned` require force. Unknown identity/provider or invalid ownership cannot be made safe by force. Reinspect within the operation and retain postcondition verification; a registry lock is not a lock against external agent processes.

Capture actual pre-update content, not merely the selected profile's prior package version. A restored forced update returns the prior native content and prior authority, not silently owned packaged content. Whole skills use the existing safe directory replacement; shared hooks use fragment-level replacement and verification preserving neighboring values. Revert/restore append new domain transitions through existing APIs. Failed verification does not publish a successful target profile; failed compensation or interruption retains recovery intent with context and observed outcomes. The explicit new update uses `OperationKind.UPDATE`; adapt inverse/recovery dispatch so it does not assume every UPDATE is a plugin.

Alternative rejected: uninstall then install as two independent convenience calls. That creates an avoidable missing-target window and splits the consumer's single update/rollback point.

### 4. Extend the existing context key to ordinary assets end to end

Reuse normalized, opaque project context keys from `utils/contexts.py`; do not invent branch/profile identity as project identity. Thread the key into ordinary project asset locators, observations, ownership namespaces, profile paths/sidecars, catalog entries, event evidence and pending operations. Centralize path/key mechanics so read and write paths agree. Use short storage components where needed for Windows path lengths while retaining the full context in domain metadata.

Continue one registry with the existing four agent roots. Add project-context partitions within the affected scope's ordinary asset storage. User scope is not partitioned by selected project. Existing plugin pointer layout and serialization remain unchanged.

All callers of ownership and desired-asset enumeration must select the applicable context, including remove and profile reconciliation, not only new inspection/update. An observation of B preserves A's last observation; missing A in B is not an absence event. Profile application filters unrelated project entries, retains them in storage, and reports selected-context coverage rather than implying global convergence. Explicit asset references or restoration operations targeting another context fail before mutation. Recovery validates the original context before native observation or compensation.

Alternative rejected: a new registry for every command or every project. It avoids some collisions but fragments shared user state and does not meet the selected shared-registry model.

### 5. Keep consumer policy and installation handover outside the library

Zuat continues to support explicit forced replacement of unauthoritative content when safe and native-supported. ZPP can reject that operation under its own policy using the new inspection evidence. This change does not auto-read agent-router receipts, auto-adopt packaged names, remove predecessor hooks, or transfer existing installations. Ambiguous old Zuat ordinary-project records receive fresh-registry guidance before mutation; do not silently rewrite history. Preserve valid user-only and already-contextual plugin behavior.

The later ZPP change owns source-object translation, lifecycle classification mapping, trait extension registration, installation handover, and `.gitignore` decisions. Its acceptance suite must run against Zuat before dependency replacement. No claim of all-agent or all-agent-router parity follows from these two public operations.

## Risks / Trade-offs

- Context threading spans old entry points -> test two projects and shared user assets through install/list/adopt/update/remove/profile/revert/restart, not only the new methods.
- Shared hooks have unstable array positions -> verify receipt-to-fragment identity, reject ambiguity and test neighboring insertions and edits.
- Provider discovery may be incomplete -> targeted owned inspection can succeed, but unknown candidates stay unresolved rather than weakening pointer-only guarantees.
- External edits can race inspection -> reinspect at update and verify after replacement; retain honest recovery evidence where convergence cannot be established.
- Public result growth can expose internals -> keep fingerprints and operation IDs as domain evidence, without Git hashes or internal plans.

## Migration Plan

1. Implement against fresh temporary agent homes and registries using failing-first pytest evidence. Existing green regression tests do not count as red evidence.
2. Validate base-only packaging and a public consumer workflow: install A, inspect against B, update B, reopen, restore A, remove; repeat with two projects and shared-hook neighbors. Preserve plugin reference-only tests.
3. Report incompatible context-free project state without conversion or deletion. Do not touch real agent installations during apply.
4. Hand off the documented Python contract to the subsequent ZPP integration change. Package rollback is not a native-state rollback; native restoration remains an explicit forward-appended operation.
