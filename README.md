# zuat
zack's useful agent tooling

Zuat observes and reconciles coding-agent assets through `zuat.pub`. Global
skills and hooks have recoverable content snapshots; plugins are tracked by
reference, never by copying their sources into the journal.

Install `zuat` for Python, or `zuat[cli]` for the optional Click interface.
Python 3.12+ and Git are required. There is no agent-router dependency.

```python
from zuat.pub import AssetSelector, PluginRef, Zuat

with Zuat(root="./agent-state") as state:
    inventory = state.discover_plugins("claude")
    bundled = state.list_assets(AssetSelector("claude", provider="plugin"))
    # Lifecycle helpers: install_plugin(ref), update_plugin(ref), remove_plugin(ref).
    ref = PluginRef("claude", "review@team")
```

```console
zuat plugin --agent claude discover --available --json
zuat list-assets --agent claude --kind skill --provider global
```

An exact plugin revision is `(agent_kind, plugin_id, version)`. Scope and opaque
project context remain separate. `home` selects the native user home;
`project_root` selects a project. Source `trust`, `trust_project`, and ownership
`force` are independent permissions, not substitutes for one another.

Python hosts can subclass `ZuatExtension`, call `register_extension(instance)`, and
call `artifact_status`, `resolve_artifacts`, `set_artifact_policy`, or
`clear_artifact_policy`. Locators receive immutable, transient installed context.
Returned paths must remain inside its verified root. Policy controls Zuat
resolution only; it cannot enable a natively disabled plugin.

Native plugin capabilities differ. Kimi currently supports discovery, not lifecycle
mutation. The inspected Claude and Codex managers do not support exact-version
restoration; Pi supports verified pinned npm versions. Missing identity/version
evidence remains unresolved, and unavailable revisions never fall back to latest.
Failed provider discovery is incomplete and does not ingest potentially
plugin-owned skill directories as global content. Uncertain mutations retain
pending evidence; `state.recover_plugins()` rediscovers state without replaying
the mutation, using the original project context where required.

Native-format fixtures, limitations, and verification evidence are recorded in
`openspec/changes/archive/2026-09-05-model-plugin-provider-revisions/`.

## Source-aware skills and hooks

The public Python additions are:

```python
Zuat.inspect_asset(asset: AssetInput) -> AssetInspection
Zuat.update_asset(asset: AssetInput, *, force: bool = False) -> OperationResult
```

`asset.source` is required. Its native identity must agree with any supplied
`name`, `locator`, and `asset_ref`. These operations address one independent
skill or one unambiguously owned hook source, not a bundled plugin contribution.
Compound hook sources retain their declared group and preserve unrelated hooks.
Each agent keeps its native formats and scope restrictions; Kimi project hooks
remain unsupported.

`AssetInspection` is frozen and reports `classification`, identity and optional
`asset_ref`, source/observed/baseline SHA-256 fingerprints, `owned`, immutable
`ownership_evidence`, `source_matches`, `completeness`, and `diagnostics`.
Missing evidence is `None`, not a fabricated fingerprint.

| Classification | Meaning |
| --- | --- |
| `absent` | Safely resolved target does not exist. |
| `current` | Valid ownership and installed content matches the source. |
| `outdated` | Installed content matches its owned baseline, but source differs. |
| `conflict` | Installed content differs from the owned baseline, even if it matches the new source. |
| `unowned` | Independent native content exists without ownership; matching bytes do not adopt it. |
| `unsupported` | Requested native scope/kind/provider is not supported. |
| `indeterminate` | Identity, source, receipt or provider evidence is insufficient or invalid. |

Inspection does not adopt, rewrite native files/profiles, or append lifecycle
history. An independently verified owned target remains inspectable if unrelated
plugin discovery fails; unknown-provider targets remain indeterminate.

Update accepts `outdated` by default. `conflict` and `unowned` require explicit
`force=True`; force does not bypass invalid receipts, ambiguous hooks, provider
boundaries or path validation. `current` returns `data["changed"] == False`
without a mutation event. Missing targets must be installed separately.

```python
from zuat.pub import AssetInput, AssetSelector, Zuat

asset = AssetInput("claude", "skill", scope="project", source="./package/reviewer")
with Zuat(root="./agent-state", home="./test-home", project_root="./project") as state:
    inspection = state.inspect_asset(asset)
    if inspection.classification == "outdated":
        updated = state.update_asset(asset)
        if updated.ok:
            restored = state.restore_all(
                updated.operation_id,
                AssetSelector("claude", kind="skill", scope="project"),
                force=True,
            )
```

Restoration appends a transition and recovers actual pre-update content and
ownership, including explicitly overwritten local/unowned content. It does not
reset Git history. Failed updates attempt verified compensation; uncertain
outcomes retain pending recovery intent. Restoring an interrupted update requires
the original project context and preserves evidence when that context is absent.
`status()` reports pending updates as partial, with the recovery operation ID in
`data["pending_operation_id"]`; pass that ID to `restore_all` after reopening.

Module-level `inspect_asset` and `update_asset` accept keyword-only `root`,
`home`, `project_root`, and `trust_project=False` (`update_asset` also accepts
`force=False`). Existing lifecycle, inventory and profile helpers forward the
same runtime context. Project assets require an explicit `project_root`; their
references, receipts and projections remain distinct across projects sharing a
registry. User assets remain shared. Applying a mixed-context profile retains
other projects and reports them in `data["coverage"]["excluded_asset_refs"]`.
Context-free earlier project state is rejected with fresh-registry guidance;
there is no automatic conversion or history rewrite.

Run `python examples/source_asset_lifecycle.py` for a complete, temporary-home
install/inspect/update/reopen/restore/remove demonstration using only `zuat.pub`.
It needs neither Click nor agent-router. Native plugin-manager availability is
still required where the selected agent's provider inspection depends on it.

This does not replace ZPP's dependency, translate its source objects, migrate
predecessor ownership, remove old hooks, or manage consumer `.gitignore` policy.

## Managed bundles and extensions

The base Python package provides these methods on `Zuat` and equivalent helpers
exported from `zuat.pub`:

```python
build_bundle(source, *, name=None, revision="HEAD") -> BundleBuild
get_bundle(bundle_id) -> BundleRecord
list_bundles() -> tuple[BundleRecord, ...]
resolve_bundle(bundle_id, *, build_revision=None, agent) -> Path
bootstrap_bundle(bundle_id, *, build_revision=None, agents=None,
                 trust=False, force=False) -> BundleOperationResult
add_bundle(source, *, name=None, revision="HEAD", agents=None,
           trust=False, force=False) -> BundleOperationResult
doctor_bundle(bundle_id, *, agents=None) -> BundleDiagnostics
remove_bundle(bundle_id, *, agents=None, purge=False) -> BundleOperationResult
```

`Zuat(..., bundle_root=None)` selects an independent compiler store, defaulting
to `<home>/.zuat` (the current user's home when omitted). Module-level helpers
accept `root`, `home`, `bundle_root`, `project_root`, and `trust_project` context.
`root`/`ZUAT_HOME` still select the existing Git registry; neither store may
contain the other. Callers use public handles, not the private index layout.

Sources are working-tree directories or explicit HTTPS Git URLs; `git+file://`
URLs select local Git repositories, including their requested commit/ref. Git
fetches have a bounded timeout, no interactive credentials, checkout filters,
hooks, submodules, or source build scripts. Credential-bearing URLs are rejected.
Skill frontmatter requires a name and description. Normalized names must be
unique; nested skill payloads, links, reparse points and special files are rejected.
Git inputs with case-colliding paths or reserved Windows names are rejected rather
than silently dropping support files during portable materialization.
Input capture is bounded to 10,000 files / 100 MiB and checks concurrent changes.

Builds retain validated skill/support bytes and agent-specific manifests. Content
and renderer inputs determine an immutable build revision. Repeated equivalent
builds reuse it, preserving the original build's provenance. For Git inputs,
`BundleBuild.source_revision` retains the requested branch, tag, `HEAD`, or commit
selector alongside the resolved `source_commit`; both are `None` for local inputs.
This metadata survives reopening the compiler store and is not added to tracking
history. Missing/modified output raises `BundleOutputError`, never a silent
rebuild. `BundleBuildError`, `BundleStoreError`, and `BundleNotFoundError` are other
typed `BundleError` failures. Generated bodies and local source bindings live
only in the compiler store, not Git history, profiles, or recovery records.

Bootstrap is user-scope only. Codex and Claude use automatically registered local
catalogs; Pi uses a registered local package route. Pi's generated-directory path
is transient routing, not its durable plugin ID, and arbitrary third-party local
packages do not acquire a bundle identity from their manifest name alone. Kimi
bootstrap is unsupported: there is no loose-skill fallback. Durable Pi bundle IDs
are not native install paths; use `bootstrap_bundle` to install a selected build.
Omitted agent selection
uses supported available managers; no available manager is a non-success result.
Native availability, format/version support and discovery failures remain explicit.

`trust=True` is required for generated local-source bootstrap. `force=True` does
not grant trust or adopt foreign installations. For an existing managed target,
Zuat attempts an update; only explicit force permits bounded removal followed by
one install attempt. Failure after deletion can leave the target absent. There is
no automatic retry, reconciliation daemon, cross-agent transaction, compensating
rollback, or guaranteed restoration from retained bundle builds. Removal retains
the registration while any owned target is unresolved, and unregisters after
verified absence. Default removal retains generated files.

`add_bundle` is the short path: build once, then bootstrap that exact revision.
It returns the ordinary bootstrap result, including its bundle ID and independent
target outcomes. A failed bootstrap leaves the successful build registered.

`doctor_bundle` checks retained output integrity and native manager availability
for selected agents (default: all supported build agents). Its typed `checks`
report `kind`, `agent`, `status`, optional build revision, and safe reason codes;
`ok` is false if any check is unhealthy. It neither repairs output nor changes
native configuration, recorded attempts, or journal history. It does not certify
that the bundle is installed/current; `status` remains historical.

Use `remove_bundle(id, purge=True)` to remove all registered targets and then
delete that bundle's generated build/catalog trees. Purge rejects agent filters,
links and reparse points; failed native removal preserves outputs. Filesystem
cleanup failure raises `BundleCleanupError`, retaining the registration and
absent-target evidence so the same explicit call can be retried. Successful
cleanup reports `outputs_removed=True`. This deletes generated files, not source
trees, other bundles, native caches or history; rebuilding requires the source.
Native marketplace registrations remain and their compiler paths can be recreated
by a later build/bootstrap. There is no orphan-output sweep or generation GC;
choose purge before unregistering if you want generated files removed.

Results report each target independently (`success`, `current`, `unsupported`,
`unavailable`, `failed`, `indeterminate`, or verified `absent` on removal).
`installed_version` and `activation` describe native observations separately
from the requested build. `get_bundle`/`list_bundles` show **historical** attempts,
not live status; interrupted attempts remain indeterminate on reopen without
replaying native commands. `result.ok` means all selected targets succeeded or
are current/verified absent; it is not an atomic all-agent guarantee.

An extension is ordinary explicitly supplied Python, not an automatic loader:

```python
from pathlib import Path
from zuat.pub import PluginArtifactContext, Zuat, ZuatExtension

class ReviewTools(ZuatExtension):
    identifier = "review-tools"
    version = "1"  # Extension contract, not a native plugin version.

    def locate_artifacts(self, context: PluginArtifactContext) -> tuple[Path, ...]:
        return (context.runtime_root / "skills/reviewer/SKILL.md",)

    def bootstrap(self, state: Zuat, source: Path):
        return state.add_bundle(source, name="review-tools", agents=("claude",), trust=True)

# Registration itself does not build, install, invoke locators or persist code.
with Zuat() as state:
    extension = ReviewTools()
    state.register_extension(extension)
    # Explicit invocation, when wanted:
    # result = extension.bootstrap(state, Path("./my-skills"))
```

`locate_artifacts` is optional and defaults to `()`. Registration validates bounded
`identifier`/`version` metadata and captures the bound locator. Re-registering the
same unchanged instance is idempotent; conflicting instances or changed metadata
are rejected. Module-level `register_extension` supplies defaults for future
services only. Service registrations stay local and must be supplied again after
restart. Artifact eligibility still requires current native evidence, version,
activation, host policy and containment. No extension code is loaded from `.zuat`.

```console
zuat bundle build ./my-skills --name review-tools --json
zuat bundle add ./my-skills --name review-tools --agent claude --trust --json
zuat bundle list --json
zuat bundle status <bundle-id> --json
zuat bundle doctor <bundle-id> --agent claude --json
zuat bundle bootstrap <bundle-id> --agent claude --trust --force --json
zuat bundle remove <bundle-id> --agent claude --json
zuat bundle remove <bundle-id> --purge --json
zuat --root ./tracking bundle --home ./test-home --bundle-root ./compiler list
```

Use `build --revision` for a Git ref and `bootstrap --build-revision` for a retained
compiled revision. `add --revision` builds and bootstraps a Git ref in one call.
Doctor and operation failures return nonzero exits in human and JSON formats.
Run `python examples/managed_bundle.py --agent claude` for a
complete public-API build/reopen/bootstrap/artifact/remove example. It uses only
temporary native homes and requires the selected native executable, not Click or
predecessor packages. Compiler attribution is included in the packaged
`zuat/utils/bundles/NOTICE`.
