# Native capability evidence

Inspected on 2026-09-04. This is implementation evidence, not a claim that all adapters are complete.

| Agent | Evidence | Discovery | Mutation restrictions |
| --- | --- | --- | --- |
| Claude | Installed CLI 2.1.233: plugin, list, install, uninstall, update help | `plugin list --json`; `--available` explicitly includes catalog entries | Install/remove: user, project, local. Update additionally permits managed. No exact-version option in the inspected help. |
| Codex | Installed CLI 0.149.1: plugin, add, list help | `plugin list --json`; `--available` explicitly includes uninstalled entries | Add accepts a configured marketplace selector, not arbitrary direct sources. No exact-version option in the inspected help. Current Zuat adapter is user-scoped. |
| Pi | Installed `@earendil-works/pi-coding-agent` 0.82.1 package and `dist/package-manager-cli.js`; official [package documentation](https://pi.dev/docs/latest/packages) | `list` reads configured packages; project visibility depends on project trust | Install/remove use `--local` for project scope but reject untrusted projects. Update has no scope flag. Project trust requires a separate public-contract decision below. |
| Kimi | Existing Zuat fixture contract in `tests/test_plugins.py` and file adapter | Version-1 installed inventory fixture; no local Kimi executable available | Discovery-only remains the conservative implementation boundary; no external native lifecycle support is claimed. |

The Pi executable fails at startup under this machine's Node 20.19.0 (`undici` reports `markAsUncloneable` unavailable). Its package declares Node >=22.19.0. No Node/package installation or upgrade was performed. Its installed source was inspected read-only instead.

## Resolved clarification: project trust is distinct from source trust

Pi 0.82.1 `dist/package-manager-cli.js` provides direct evidence:

- `createCommandSettingsManager`, lines 478-515: an explicit false project-trust override sets project trust false, even where saved trust exists. Omitting an override can load project trust extensions on non-update commands.
- `handlePackageCommand`, lines 635-650: project install/remove require a trusted project; `--no-approve` therefore prevents them.
- Its option parser, lines 180-190: a local-scope flag is accepted only for install/remove, not update.
- `handlePackageCommand`, update branch: a targeted source is passed to the package manager without a scope selector. Isolation needs separate verification before advertising project-scoped update.

The current design models plugin-source `trust` and authority `force`, but not project-configuration trust. Automatically adding `--approve` would expand trust to project configuration. Keeping `--no-approve` and claiming complete project discovery/lifecycle would be false. Removing the flag can introduce prompts or project extension loading. None is an acceptable silent implementation choice.

Proposed decision for the user: introduce an independent explicit `trust_project` input, default false; keep plugin-source trust and force independent. Define how incomplete project discovery is reported when project trust is absent, and reject any update whose native command cannot isolate the requested installation. Update the artifacts before continuing the affected implementation.

Approved by the user on 2026-09-05: add independent default-false `trust_project` and proceed automatically. The design and command/revision specs now encode it. Adapter tests verify explicit native trust flags, rejection before project mutation without trust, incomplete untrusted discovery, selected working directory, private agent home, and rejection of source-targeted Pi updates that span scopes.

Fixtures: `tests/test_plugins.py` retains the original native inventory shapes; `tests/test_plugin_adapters.py` adds configured-catalog and project-trust cases based on the help/source above. Stateful workflow fixtures in `tests/test_plugin_workflows.py` model supported native state transitions; they do not claim unsupported production Claude exact-version acquisition.

## Additional verified formats (2026-09-05)

- Codex's official `codex-rs/cli/src/plugin_cmd.rs` distinguishes installed and available rows. Its reported version can fall back to catalog metadata. Zuat therefore resolves runtime revisions against the installed cache, not a catalog source directory. The official [`core-plugins/src/store.rs`](https://github.com/openai/codex/blob/main/codex-rs/core-plugins/src/store.rs) defines that cache. Missing runtime evidence remains unresolved. [`loader.rs`](https://github.com/openai/codex/blob/main/codex-rs/core-plugins/src/loader.rs) establishes manifest hook declarations and the default `hooks/hooks.json`.
- Claude's [plugin reference](https://code.claude.com/docs/en/plugins-reference) establishes additive skill directories and custom hook declarations. Fixtures cover both default and declared resources without persisting bodies.
- Kimi's official [`plugin/store.ts`](https://github.com/MoonshotAI/kimi-code/blob/main/packages/agent-core/src/plugin/store.ts) confirms version-1 `installed.json` records and transient `root`. Its [plugin reference](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins.html) establishes manifest precedence, version metadata, skill paths, and hook arrays. These are now covered by native-format discovery fixtures; the earlier fixture-only evidence is superseded. Lifecycle remains unsupported because the documented interface is interactive slash commands rather than a verified noninteractive manager.
- Pi's documented pinned npm installation is implemented for exact npm versions, with rediscovery and no fallback. Other exact source/version acquisitions remain unsupported. Trusted direct sources that cannot supply safe canonical identity produce indeterminate outcomes, not fabricated revisions.

Project installations carry an opaque context key independently of revision identity. Native commands use selected runtime roots; those paths and prior trust grants do not enter pointers. Cross-project and cross-scope tests cover independent ownership and profile removal.
