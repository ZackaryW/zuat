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

Python hosts can register `ArtifactExtension(identifier, version, locate)` and
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
