## Context

See proposal.md for motivation. Agent-bundler's `skill2plugin` separates source discovery/compiler code from an Agent Router lifecycle port, but couples orchestration to its own JSON state and uses generated directory paths as Claude/Pi references. Zuat already has public lifecycle APIs, separate native adapters, source trust checks and reference-only plugin history. Its artifact extension contract locates installed artifacts; it is not a bundle compiler or a reason to introduce a new plugin-loading framework.

Design is required because the change crosses public extension APIs, filesystem storage, native agent adapters and the plugin persistence boundary. The four capability deltas define observable behavior; this document chooses a small implementation rather than a desired-state engine.

## Goals / Non-Goals

**Goals:** Make building and bootstrapping callable independently; keep bundle identity stable across builds; isolate generated content from tracking history; reuse native operations and their verification; let applications use public handles instead of `.zuat` paths.

**Non-Goals:** A sync daemon, reconciliation plans, per-agent desired-state profiles, automatic retries, cross-agent transactions, guaranteed bundle restoration, old `s2p` commands/state readers, grouped loose skills, automatic extension loading or lifecycle callback execution, hook bundling, overlays, publishing or generation garbage collection. Existing asset/profile/recovery behavior is not removed or weakened.

## Decisions

### 1. Small public operations with one explicit build selection

Add focused modules under `pub/bundles/` for models, building, registry queries and bootstrap/removal. Keep `Zuat` a thin facade and expose equivalent module-level helpers through `zuat.pub`. Proposed signatures:

```python
build_bundle(source, *, name=None, revision="HEAD") -> BundleBuild
get_bundle(bundle_id) -> BundleRecord
list_bundles() -> tuple[BundleRecord, ...]
resolve_bundle(bundle_id, *, build_revision=None, agent) -> Path
bootstrap_bundle(bundle_id, *, build_revision=None, agents=None,
                 trust=False, force=False) -> BundleOperationResult
remove_bundle(bundle_id, *, agents=None) -> BundleOperationResult
```

The service accepts a separate `bundle_root`; helpers forward it along with existing `root` and `home` context. An omitted build revision resolves the latest successfully registered build once at the start of a call, not separately during each agent attempt. Runtime path resolution validates containment and build integrity. No public mutable registry handle is returned. A build provides its bundle ID and build revision; per-target results distinguish success, current, unsupported, unavailable, failed and indeterminate with safe diagnostics. Last-attempt metadata is labeled historical, never fresh native status. Bundle errors use typed public failures/exceptions consistently with existing conventions.

Alternative rejected: preserve `Skill2PluginService`, add legacy aliases or expose the JSON schema. Future extensions need reusable operations, not another application embedded in Zuat. The generalized extension class below replaces the artifact-only class; it does not add a dynamic extension loader.

### 1a. One subclassable public extension contract

Introduce `ZuatExtension` in a focused `pub/extensions.py`, exported from `zuat.pub`. Its initial contract is deliberately small:

```python
class ZuatExtension:
    identifier: str
    version: str

    def locate_artifacts(
        self, context: PluginArtifactContext
    ) -> tuple[Path, ...]:
        return ()
```

Hosts provide identity/version on their subclass or instance; registration validates them using the existing bounded metadata rules. The optional locator defaults to no artifacts. Keep `PluginArtifactContext` and `ArtifactStatus`, plus `artifact_status`, `resolve_artifacts` and policy APIs: they already model installed-provider evidence, and generalizing the extension does not change that domain.

Replace module-level and service-level `register_artifact` with `register_extension`. Remove the old `ArtifactExtension` export/type and registration entry points rather than retain aliases. Registration captures the extension's identifier, contract version and bound locator as runtime values. Re-registering the same instance with unchanged identity/version/locator is idempotent; another instance claiming its ID, or changed registration metadata, is a conflict. Do not infer code equality from class names or version strings. A service uses its own registration mapping, initially copied from process defaults; later process registrations do not retroactively change existing services.

Registration validates/stores the supplied runtime object only: no locator call, startup callback, automatic bundle build, native command or persistent extension serialization. Instantiation/import of host-supplied Python remains the host's responsibility; this interface is not a sandbox. Nothing in `.zuat` or the journal loads extension code on restart. Missing registrations remain unknown; a registered default locator returns no eligible artifacts and artifact-unavailable status. Locator failures produce safe unresolved results rather than persisting exception payloads or altering policy/native state.

Artifact dispatch invokes the captured `locate_artifacts` only after the existing native eligibility checks, then applies existing root containment checks. Preserve revision binding, disabled-plugin behavior, policy scope and policy history keyed by extension identifier; the extension's contract version is not a native plugin version. Tests must retain these behaviors when callers move to the new class.

Extensions can expose their own ordinary methods accepting a `Zuat` service and explicitly call `build_bundle`, `bootstrap_bundle` or queries. Zuat does not discover or invoke those methods. They receive no private-store handle and require the same trust/force inputs as any host call. No base-class build/install/remove hooks, automatic extension-owned storage namespace or new capability dispatcher are needed for this scope.

Alternative rejected: keep both extension classes or give the base class a full lifecycle framework. Optional artifact location plus explicit public API composition provides the requested extensibility without reinstating reconciliation machinery.

### 2. `.zuat` is a compiler store, not a replacement Git registry

Resolve the default compiler root to the selected home directory's `.zuat` (`Path.home()` when home is omitted); `bundle_root` explicitly overrides it. Do not infer it from the working directory or auto-read project configuration. Initial installations remain user-scope. This keeps existing registry `root`/`ZUAT_HOME` semantics intact and permits future project consumers to select a store through the API without migrating current users.

Keep a compact registration index, immutable build directories and staging beneath this root. A record contains bundle ID, source binding, successful build revisions, and each target's canonical installed reference plus last attempt. Use atomic index replacement and one bounded store lock to prevent concurrent build/bootstrap/remove calls corrupting registrations. Maintain at most one current attempt marker per selected target; reopening reports unfinished attempts, never executes them. Do not add a second replay engine or event-sourced state store.

Generated files and private local source bindings belong only here. Build directories must be disjoint from the Git tracking root, including resolved ancestor/descendant overlap and linked paths; reject unsafe overlap. Journal only allowlisted bundle IDs, build revisions and verified plugin references through existing operation facilities. No raw native output, build files, source credentials or local runtime paths enter history. Temporary Git checkouts are removed after compilation; persistent output is the build, not a cloned source repository.

The modified plugin requirement is necessary because its current wording forbids even compiler outputs in auxiliary storage. The exception is for explicitly built inputs/outputs, not for harvesting installed plugins. Alternative rejected: commit generated plugin trees to the journal or make `.zuat` itself another Git repository.

### 3. Migrate compiler mechanics, not predecessor lifecycle state

Port bounded skill discovery, collision checks, frontmatter validation, source-to-generated mappings and deterministic fingerprints. Preserve support files. Build from a validated isolated file set so hashing and copying describe the same content; do not validate one walk and then use an unrestricted copy of a changing tree. Reject links/reparse points, special files, ambiguous nesting that duplicates skill payloads, escapes and excessive trees. Render into staging and publish only complete validated output. Include renderer-contract version and build options in build identity so a renderer change cannot incorrectly reuse old output.

Keep source selection explicit: local sources bind to their resolved roots; Git sources retain a sanitized locator, requested revision and resolved commit. Reject credential-bearing source references for persistent bindings rather than saving secrets. Fetch into a temporary checkout without source hook execution or recursive submodules. No source-provided build scripts execute.

Use existing GitPython, YAML and neutral filesystem/process helpers where suitable. No runtime dependency on agent-bundler, agent-router, Typer or platformdirs is required. Preserve applicable attribution when porting source. Alternative rejected: importing the predecessor compiler and thereby retaining its state/dependency surface.

### 4. Native formation and bootstrap belong to each agent

Extend the shared resolver contract with a focused bundle capability exposing rendering and bootstrap preparation, implemented separately for Codex, Claude and Pi. Codex's existing local marketplace behavior is migration input, not authority to bypass native validation. Provide managed catalog setup for catalog-based agents through the native runner and preserve unrelated catalog entries. For Claude, prepare a supported local catalog/plugin reference rather than assuming its current adapter accepts raw directory installation. For Pi, separate transient local package routing from the stable manifest/native identity used in registry records; do not persist a generation-directory path as the plugin ID.

Keep source locators separate from IDs and from proposed/native versions. Build versions are publisher declarations; only native rediscovery establishes an installed exact revision. Validate these integrations against native fixtures and read-only installed CLI contracts during implementation; if a native manager cannot establish a safe supported route, return unsupported rather than emulate its private configuration. Kimi explicitly reports unsupported plugin bootstrap; do not manufacture a native plugin or install a loose-skill group. Omitted agents selects supported available targets; no available target returns an explicit unavailable result rather than successful installation.

Alternative rejected: central agent switches in utilities or silently converting plugin bundles into ordinary assets. Those reproduce the earlier modeling problem and expand ownership behavior.

### 5. One attempt, optional bounded destructive fallback

Read and validate the selected build, trust, target identity and supported route before any destructive action. For each selected agent, inspect current state: absent means install, an established current build means no change, and an established earlier managed build means attempt supported update. Compare native version evidence rather than the global content hash or a cached success flag.

Without force, no failed/unsupported update triggers removal. With force, re-establish that the exact registered target remains identifiable; remove through the supported native operation, verify absence, then attempt installation once. Do not delete plugin-cache parent directories or remove another installation merely because its display name matches. An unresolved existing native-operation marker must be resolved observationally through existing facilities or reported as blocking; do not bypass it to force another write. Force is neither source trust nor adoption of a foreign installation.

Record each target's observed outcome and complete the call. If replacement installation fails after deletion, leave the bundle registered and report absence/uncertainty. Preserve successful other-agent work. An update or removal can have side effects even when its command fails: retain truthful outcome evidence rather than promise original content survived. No automatic rollback, retry queue, profile publication or bundle-level inverse plan is added. Existing lower-level history remains forward-appended and reference-only.

Remove selected registered targets similarly. Keep registration while any target is installed or unresolved; unregister after all are verified absent. Uninstalled build-only bundles can be unregistered without native calls. Retained immutable output need not be garbage-collected in this change and is not advertised as a restore guarantee.

Alternative rejected: port predecessor reconciliation/state wholesale or add transaction compensation. The requested operation is explicit bootstrap/replace, not convergence.

### 6. Thin CLI and behavioral evidence

Add `zuat bundle build`, `list`, `status`, `bootstrap` and `remove`; `status` reports stored registration/last-attempt evidence and does not mutate. Expose revision selection, root selection, agent filters, trust and force where relevant. Human and JSON output use the same public results. Keep Click optional and do not add old executable aliases.

Use nested tests in `tests/pub/bundles`, `tests/pub/extensions`, `tests/specs/bundles`, `tests/utils/bundles` and the existing CLI grouping. Write failing behavior tests before each implementation increment; verify extension registration/isolation, actual generated files, native fixtures, independent target outcomes and journal contents. Use pytest for the complete consumer workflow because one focused test can establish it; retain existing qualifying Behave regressions without duplicating them for presentation.

## Risks / Trade-offs

- Native local-plugin routes vary -> agent-owned capability checks, explicit unsupported outcomes and native-boundary fixtures; no blanket all-agent support claim.
- Force can leave an installation absent -> preflight first, explicit trust/force, verify removal and report the final observed state; this is accepted, not compensated.
- Local files can change during build -> materialize a validated bounded input snapshot and publish immutable output only after validation.
- Two stores can disagree after interruption -> label last attempts unverified and re-observe on the next explicit bootstrap; no automatic resume or distributed transaction.
- Generated content can leak into Git through root overlap -> reject overlap and test every newly created Git blob for known bundle-content sentinels on success and failure.

## Migration Plan

Add bundle operations and directly replace the artifact-only extension API in this fresh library; update current repository callers/tests/examples without aliases, legacy receipt readers, state conversion, or edits to agent-bundler/ZPP. Existing artifact policy records retain their identifiers and behavior; host extensions are explicitly registered again at runtime, not loaded from history. Keep `config.yaml` concise: during apply, record only the stable compiler-store/public-extension boundary, with behavioral details staying in capability specs. Prove the workflow in temporary homes/stores and a base-only installed package before any separately authorized live bootstrap. Removing the new package feature does not undo native installations; explicit removal is the supported exit, and no guaranteed bundle downgrade/rollback is introduced.
