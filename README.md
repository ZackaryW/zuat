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

Native capabilities differ. Kimi currently supports discovery, not lifecycle
mutation. The inspected Claude and Codex managers do not support exact-version
restoration; Pi supports verified pinned npm versions. Missing identity/version
evidence remains unresolved, and unavailable revisions never fall back to latest.
Failed provider discovery is incomplete and does not ingest potentially
plugin-owned skill directories as global content. Uncertain mutations retain
pending evidence; `state.recover_plugins()` rediscovers state without replaying
the mutation, using the original project context where required.

Native-format fixtures, limitations, and verification evidence are recorded in
`openspec/changes/archive/2026-09-05-model-plugin-provider-revisions/`.
