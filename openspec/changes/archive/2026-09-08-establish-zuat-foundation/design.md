## Context

See `proposal.md` for motivation and the three delta specifications for observable behavior. The current foundation implementation already establishes the package boundaries and agent-specific resolver modules, but its registry and public surface model Git's working tree, staging area, commits, and branches directly. That implementation must be corrected in place; this is a fresh library, so no compatibility layer or legacy command aliases are required.

Zuat manages native state that may have been created by Zuat, by an agent, or by a user. Shared hook documents make file-level ownership insufficient because several independently manageable fragments can coexist with unrelated settings. External plugin managers also prevent Zuat from promising atomic rollback in every case.

## Goals / Non-Goals

**Goals:**

- Keep Git as a private persistence mechanism for a linear, append-only domain journal.
- Give every manageable native asset a durable Zuat identity independent of its current content fingerprint.
- Make observation automatic and complete within each resolver's bounded native surface.
- Express all supported mutations as install, uninstall, profile switch, force, and forward-only revert operations.
- Keep agent-specific decisions in separate resolver implementations while sharing only agent-neutral mechanics.
- Make public Python and CLI contracts entirely domain-oriented.

**Non-Goals:**

- Public Git porcelain, Git-compatible status, staging, committing, branch management, or snapshot recovery.
- Backward compatibility with the discarded public API or command vocabulary.
- A shared cross-agent asset identity or automatic cross-agent synchronization.
- Mirroring complete native agent homes, credentials, sessions, caches, or plugin runtime directories.
- Remote Git synchronization or any use of `git push --force`; Zuat's `force` is a scoped lifecycle conflict decision.
- A background filesystem daemon in the first implementation; observation runs at public operation boundaries.

## Decisions

### Persist one linear private journal

`zuat.gitcore` will own one Git repository beneath the selected application-data root. A single internal journal line advances for every recorded event. Zuat may use private refs, indexes, trees, and commits to implement it, but these values never enter public requests or results.

Each journal commit stores an immutable operation document and the resulting concrete repository projection. The checked-out tree is deliberately human-browsable and has this stable shape:

```text
<registry-root>/
  claude/<scope>/<kind>/...
  codex/<scope>/<kind>/...
  kimi/<scope>/<kind>/...
  pi/<scope>/<kind>/...
  profiles/<profile>/<agent>/<scope>/<kind>/...
  operations/<sequence>-<operation-id>.json
  catalog.json
  selected-profile
```

The four top-level agent trees contain the latest complete bounded observation, including manageable content that Zuat did not install. Profile trees contain concrete desired assets only. `catalog.json` maps stable Zuat asset IDs to their agent-native identity and concrete repository locations, while `selected-profile` is a plain-text profile name. Operation documents record intent, outcome, force, diagnostics, and before-and-after asset references without becoming a second serialized copy of asset payloads. Sequence-prefixed operation filenames make journal order apparent without exposing Git commits.

There is no `observations/` wrapper, monolithic `state.json`, or `events/` database-shaped directory. Asset payloads are normalized as ordinary files or declarations in agent and profile trees so a Git diff identifies the actual changed asset and Git deduplicates repeated profile or observation content. Observation operations update the top-level agent tree and catalog but do not add unauthoritative content to a profile. Successful lifecycle operations update profile trees only where their domain intent requires it.

This linear event stream is chosen over branch-per-profile as the primary model because creation, switching, rejected operations, forced decisions, and reverts then have one total order. Named profiles remain projections inside journal state. An internal ref may point at the journal head, but a profile is never exposed as a Git branch.

Alternative: retain the existing working-tree/index/branch mapping and hide only the CLI commands. Rejected because internal status categories would continue to shape orchestration, conflict behavior, and result models around a user workflow that no longer exists.

Alternative: replace Git with a custom database and blob store. Rejected for this foundation because Git already supplies durable content-addressed objects, atomic ref advancement, history traversal, and deduplication behind a narrow adapter.

Alternative: store observations, profiles, and current state primarily in large JSON documents. Rejected because it makes a repository browser and ordinary Git diff show storage machinery instead of the skill, hook, extension, or plugin declaration that changed.

### Separate journal events from projected state

The journal model has two related forms:

- An immutable event records a stable operation ID, sequence, timestamp, kind, requested intent, target profile, asset references, before-and-after evidence, force decision, completeness, verification outcome, and diagnostics.
- A concrete projection records the current selected profile as plain text, every named profile's desired assets as ordinary files, the latest observed agent trees, and a compact stable-identity catalog.

Private journal commit identity is deliberately absent from the domain model. Public history and revert use Zuat operation IDs. Caller-selected source revisions and resolved source commits are provenance, not journal identifiers, and may appear in the source-aware bundle contract. The concrete projection can be rebuilt by replaying operation records and is committed with each operation to make startup reads and integrity checks bounded. Profile membership is represented by concrete profile assets and their small sidecar identity metadata rather than a duplicate membership table in a monolithic state document. Latest observation evidence can be recovered from the ordered operation stream and the top-level agent trees.

Changed observations receive observation events; identical complete observations are deduplicated against the last observation identity. Partial or indeterminate observations are never interpreted as authoritative deletion. Rejected mutations also receive events so user intent and the reason for refusal remain auditable.

Alternative: store only current profile trees and infer operations from Git diffs. Rejected because force decisions, rejected attempts, partial plugin outcomes, and inverse-operation provenance cannot be reconstructed reliably from tree differences.

Alternative: keep a complete serialized projected-state document alongside the concrete files. Rejected because it creates two competing representations and makes repository review noisy. Compact catalog and per-asset sidecar metadata are indexes over concrete assets, not an alternate payload store.

### Use durable asset identity plus observation evidence

An internal `AssetRef` catalog assigns an opaque stable Zuat ID to the tuple of agent, asset kind, scope, and agent-native locator. The locator is relative to a validated native root or is a resolver-defined semantic location inside a shared document. Content fingerprints, authority, desired payload identity, and verification timestamps are observation evidence, not identity.

The catalog also records the normalized concrete path used in the private repository. Each concrete profile asset carries enough adjacent metadata to recover its stable asset reference without consulting a duplicated profile-membership table. Shared-document fragments are materialized independently beneath the relevant hook tree even though the resolver later reconciles them into one native settings document.

For ordinary files and directories, the native locator is a canonical scope-relative path. For shared documents, the agent resolver enumerates independently manageable hook fragments and produces a deterministic semantic locator within the supported hook structure. If a native move changes the locator, Zuat observes a removal and an addition rather than guessing identity across locations.

Authority is derived on each observation:

- `authoritative`: the selected profile contains the asset reference and observed content matches desired evidence;
- `unauthoritative`: manageable content exists but is not selected-profile intent;
- `conflicting`: native content occupies a desired locator with incompatible evidence, or the planned operation would displace incompatible unauthoritative content;
- `partial` or `indeterminate`: observation or verification cannot establish a complete answer.

Ownership records remain useful provenance and rollback evidence, but they are not a permanent permission gate. Equivalent existing content can be adopted by install. Conflicting unauthoritative content can be changed only by an explicit force on the specific operation and references.

Alternative: identify assets by fingerprint. Rejected because any content edit would create a new identity and make ownership, history, and revert difficult to follow.

### Orchestrate applicable lifecycle mutations as observed transactions

Asset and profile lifecycle mutations use the following orchestration pattern, applying only the stages required by the operation. Profile creation does not mutate native state, and explicit observation can journal changed evidence without applying assets. Read-only queries, bundle diagnostics, compilation, and extension registration follow their own capability contracts; they do not acquire mutation semantics merely because they are public APIs.

1. Acquire the application-root mutation lock.
2. Ask the selected agent resolver or resolvers for a complete bounded observation.
3. Update stable asset identities and append an observation event only when normalized evidence changed.
4. Validate the requested domain operation and calculate an agent-specific plan against profile and observed evidence.
5. Reject and journal a blocking conflict unless the caller explicitly supplied force for that operation.
6. Before native mutation, write an internal recovery marker containing the operation ID, plan, and before evidence.
7. Apply any planned native filesystem, shared-document, or plugin actions and verify their postconditions.
8. Update the profile projection only for verified changes, append the operation outcome, atomically advance the journal head, and clear a recovery marker only when its operation is resolved.

If the process stops after native mutation but before journal advancement, reopening safely classifies interrupted state or preserves pending evidence for operation-specific orchestration. Generic markers produce an indeterminate recovery event requiring fresh observation; plugin-lifecycle and source-aware asset-update markers remain pending for their orchestrator and original context. Reopening alone does not automatically retry, replay, or restore native changes. Applicable public recovery operations perform native verification or explicit restoration and record their outcomes without losing before evidence or reporting a partially accepted profile update as successful. Users refer to domain operation IDs, never manipulate Git, and never select hidden snapshots.

Install adds or adopts verified desired content into the selected profile. Uninstall removes selected desired content when present and removes the referenced native asset. Removing or overwriting conflicting unauthoritative content requires force. Profile switch preflights the target against current observations and selects the target only after all required outcomes meet the operation's success policy.

Alternative: update the profile before native mutation and repair it later. Rejected because a crash or indeterminate plugin result could expose unverified intent as successfully materialized state.

### Implement revert as a new inverse transaction

Revert resolves a prior Zuat operation ID, derives its inverse from recorded before-and-after evidence, and sends that inverse through the same observation, conflict, force, apply, verify, and journal pipeline. It never resets a ref, checks out an old commit, amends an event, or deletes history. A revert event references the original operation and is itself revertible.

Intervening drift is evaluated like any other conflict. The caller must explicitly force a revert that would overwrite or remove conflicting unauthoritative state. This preserves the append-only audit trail and prevents historical intent from silently taking precedence over current native content.

Alternative: reset the profile or journal head to an earlier commit. Rejected because it rewrites the visible operation story and cannot safely account for native changes that occurred afterward.

### Keep product layers acyclic

The package dependency direction is:

```text
zuat.cli --> zuat.pub --> zuat.gitcore
                     --> zuat.specs --> zuat.utils

zuat.gitcore --> GitPython
```

`zuat.pub` owns supported request and result types plus orchestration. Click handlers import only `zuat.pub`. `zuat.specs/interface.py` defines the resolver protocol and normalized domain types. `codex.py`, `claude.py`, `kimi.py`, and `pi.py` explicitly own their native formats, locations, supported scopes, observation, planning, mutation, and verification. `registry.py` performs resolver lookup without moving agent behavior into a shared mode switch.

`zuat.utils` contains focused agent-neutral mechanics such as bounded file collection, fingerprints, atomic replacement, shared-document write primitives, process execution, locks, and result assembly. Utilities receive already selected locations and agent-native callbacks; they do not decide behavior by inspecting agent identity.

`zuat.gitcore` owns event serialization, projected-state persistence, operation-ID lookup, integrity checks, locking, recovery markers, and the GitPython adapter. GitPython types stop at this boundary.

Alternative: centralize native behavior in one configurable base resolver. Rejected because constructor-only agent classes conceal meaningful differences among Codex, Claude, Kimi, and Pi.

### Keep Click optional with a base-package shim

GitPython and PyYAML remain base dependencies because journal persistence and semantic skill validation are core Python capabilities. Click remains only in `[project.optional-dependencies].cli`. The console entry point uses a small base-package shim that imports the Click application lazily and converts a missing optional dependency into guidance to install `zuat[cli]`.

Alternative: point the console entry directly at the Click module. Rejected because a missing optional dependency would raise before Zuat could present installation guidance.

### Verify agent-native outcomes at their real boundary

Skills and Pi extensions use bounded canonical roots, regular-file collection, symlink rejection, sibling temporary materialization, replacement, rollback evidence, and post-write fingerprint verification. Shared hook documents are parsed completely, changed at fragment granularity, written atomically, reparsed, and checked to ensure unrelated content survived. Every supported hook fragment is enumerated whether or not an ownership record exists.

Plugins remain declarative in profiles. Per-agent adapters execute noninteractive native plugin operations through an injectable argument-vector runner and verify by rediscovery. When external behavior cannot prove convergence, the event outcome is partial or indeterminate and profile transition success is withheld according to the operation plan.

Alternative: treat a successful plugin process exit as convergence. Rejected because process success does not prove final native state and cannot support trustworthy revert.

## Risks / Trade-offs

- [The private journal projection and native surfaces can diverge across a crash] -> Preserve recovery evidence, classify or retain pending state at reopen, and use operation-specific observation and explicit restoration where required before reporting recovery success.
- [Stable identity inside array-shaped hook documents is limited by native formats without IDs] -> Use resolver-defined semantic locators and treat a true locator move as remove-plus-add rather than guessing.
- [Forced mutation can destroy user-created content] -> Scope force to explicit asset references, preserve before evidence, verify unrelated shared content, and journal the decision.
- [Observation events can grow indefinitely] -> Deduplicate unchanged observations and rely on Git object reuse; define retention or compaction only in a later capability that preserves domain history.
- [Concrete observation and profile trees repeat paths and content] -> Let Git object storage deduplicate identical blobs and prefer repository clarity over a bespoke packed representation.
- [Catalog or sidecar metadata can disagree with concrete files after external edits to the private root] -> Treat the root as Zuat-controlled, validate the projection on startup, and append a diagnostic or recovery outcome instead of silently accepting inconsistent membership.
- [GitPython depends on the Git executable] -> Keep it behind `gitcore`, test the exact adapter operations, and surface a deterministic prerequisite error.
- [Native behavior can regress across agent versions] -> Maintain agent-specific fixtures and drive implementation in red-green-refactor slices.
- [An external plugin operation may be non-atomic] -> Record partial or indeterminate outcomes and never report unverified convergence.
- [Multiple processes could interleave native and journal mutations] -> Hold one application-root lock across observation, plan, native action, verification, and journal advancement.

## Migration Plan

1. Replace existing tests for stage, commit, Git status, branch checkout, and snapshot recovery with failing tests for automatic observation journaling, domain history, and forward-only revert.
2. Introduce the journal event, projected state, stable asset reference, authority, and public result models without compatibility aliases.
3. Replace working-tree and branch orchestration in `gitcore` with the linear journal adapter, recovery marker, profile projection, and domain operation lookup.
4. Expand each concrete resolver to enumerate all manageable assets, including previously unknown shared hook fragments, and to support adopt, install, uninstall, force, and verification.
5. Replace public Python and Click commands with status, install, uninstall, profile, history, and revert operations; remove discarded Git-shaped commands outright.
6. Run focused pytest tests red then green for each behavior, followed by the full pytest suite and only genuinely cross-component Behave workflows.
7. Replace the database-shaped `observations/`, `events/`, and `state.json` projection with top-level agent trees, concrete profile trees, ordered `operations/`, `catalog.json`, and `selected-profile`; this fresh library provides no reader or migration compatibility for the discarded private layout.

Development rollback uses source control to revert the implementation patch and removes only explicitly selected temporary registry roots. The persistent manual Claude simulation remains untouched until the user separately authorizes cleanup.
