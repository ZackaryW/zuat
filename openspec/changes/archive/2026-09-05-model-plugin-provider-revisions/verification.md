# Implementation evidence

## Baseline

- `uv run --extra cli pytest -q`: 146 passed (54.11s).
- `uv run --extra cli behave`: 4 scenarios / 23 steps passed.
- Existing repository changes predate this apply run; they are preserved.

## Coverage map

| Capability | Behavioral test boundary | Isolation and evidence |
| --- | --- | --- |
| Revision tracking | Native values, mixed observation, profile persistence, public update/restore/restart | Temporary registry and user homes; inspect decoded pointer records and all durable sinks, including Git objects and private archives |
| Contribution resolution | Per-agent discovery, public provider selectors, artifact extension/status/policy | Temporary installed plugin trees with colliding global names, moved roots and escaping symlinks; assert native state and resolution outcomes |
| Command surface | Public Python orchestration, injected native process runner, Click runner, installed package | Stateful native fixtures, two project roots and separate agent roots; verify requested transitions, untouched neighbors, and base-only installation |

Persistence sinks to cover: normalized observations, catalog, native provenance stores, profile entries/sidecars, journal before/after and metadata, recovery markers, private payload archive, and committed Git objects. Native stdout/stderr and runtime contexts remain transient.

The cross-boundary acceptance workflow is install/discover -> update A to B -> restart -> restore A with global content unchanged -> artifact policy resolution. It will use pytest with a stateful native-manager fixture and reopened registry; adding Behave would duplicate the same evidence. Existing genuine Behave workflows remain regression coverage. New behavioral tests must be run red before their implementation; no baseline green result is counted as red evidence.

## Red/green log

- Task 1.2: `uv run --extra cli pytest tests/test_plugin_revisions.py -q` initially failed all 8 cases: missing revision/contribution behavior and invalid version values accepted.
- Task 1.2 green: revision tests plus existing native models, 11 passed.
- Task 1.3 red: `tests/test_plugin_state.py`, 9 failed / 1 existing safe-source case passed; failures demonstrated raw-evidence leakage, unsafe fields, and credential/path routing persistence. Green with revision/native/plugin regressions: 29 passed.
- Task 2.1 partial red: `tests/test_plugin_capabilities.py`, 4 failed / 2 regression cases passed. Claude managed install/removal reached execution incorrectly, and explicit capability reporting was absent. Green after operation-specific capabilities and per-agent adapter extraction: 17 passed including existing plugin/native tests. The task is not complete; see `native-capabilities.md` for the project-trust blocker.

## Apply pause verification

This section records the prior pause, before the approved continuation below.

- `uv run --extra cli pytest -q`: 170 passed (50.81s).
- `uv run --extra cli behave`: 4 scenarios / 23 steps passed.
- `openspec validate model-plugin-provider-revisions --strict`: valid.
- Apply progress: 3/26 tasks complete; task 2.1 remains partial. Full plugin lifecycle, pointer persistence across all sinks, and public surfaces are not yet implemented.
- No live plugin install, update, removal, restore, or registry reset was performed. Native executable checks were help/version only. Test mutations used temporary state.

## Approved continuation (2026-09-05)

- `tests/test_plugin_adapters.py`: initial red 18 failed / 4 existing cases passed. After implementation and correcting two obsolete regression expectations (native config root; missing Pi runtime root), adapter/capability/plugin tests: 36 passed.
- `tests/test_plugin_workflows.py`: initial red 6 failed. Pointer adoption/removal, incompatible-record rejection, untrusted observation preservation, and public lifecycle then passed all 6.
- `tests/test_plugin_artifacts.py`: initial red 4 failed; registration, provider provenance, scoped policy and transient resolution then passed.
- `tests/test_plugin_cli.py`: initial red 2 failed; explicit trust-control routing and public exports then passed both cases.
- `tests/test_plugin_persistence.py`: initial red 2 failed, demonstrating global-folder source ingestion and unfiltered recovery metadata. After fixes, persistence/workflow/artifact tests: 12 passed.
- `tests/test_plugin_recovery.py`: exact restore was added as an already-green regression (not red evidence); new update-revert and restart-recovery cases failed before implementation. All 3 cases then passed.
- Last broad checkpoint: pytest results recorded separately below after completion. Tasks remain unchecked until their full verification scope is covered; focused passing tests alone do not complete the entire change.

## Completed continuation evidence

Additional failing-first cases demonstrated and corrected:

- Deleted prior pointers and accidental plugin-as-global ingestion after failed discovery; raw evidence fields accepted by journal serialization; incompatible historical records accepted by the reader.
- Cross-project installation collisions and failure to remove project-owned plugins during profile reconciliation.
- Pi version pins being treated as separate identities, unsupported exact npm restoration, adopting the wrong pinned version, replacing external revisions without force, and missing intended-revision recovery evidence.
- Unverified updates clearing pending recovery, unnoticed changes to neighboring plugins, and recovery accepting the wrong project context.
- Missing Codex runtime roots, treating catalog versions as installed revisions, conflicting/ambiguous marketplaces, and incomplete Claude/Kimi contribution decoding.
- Standalone provider filters and CLI dispatch/filter gaps; artifact policy being rebound to another project.
- Trusted direct-source installation rejected by pointer serialization, and simple discovery omitting external ownership observations.

The isolated cross-boundary pytest workflow now exercises public discovery/lifecycle, update, restart, profile restoration, policy persistence, and mixed global/plugin deletion and bulk restoration. It verifies global content, native revisions, unpublished failed target profiles, private control files, and actual private Git blob objects. Successful existing behavior added as regression coverage (including several artifact cases and mixed restoration) is not retroactively claimed as red evidence.

Coverage anchors:

| Tasks | Executed tests |
| --- | --- |
| 2.2–2.4 | `test_plugin_adapters.py`, `test_plugin_capabilities.py`, `test_plugin_project_context.py`, `test_plugin_contributions_native.py` |
| 3.1–3.4 | `test_plugin_state.py`, `test_plugin_persistence.py`, `test_plugin_workflows.py`, `test_plugin_end_to_end.py` |
| 4.1–4.3 | `test_plugin_workflows.py`, `test_pi_exact_plugins.py`, `test_plugin_project_context.py` |
| 5.1–5.5 | `test_plugin_artifacts.py`, `test_plugin_contributions_native.py`, `test_plugin_cli.py` |
| 6.1–6.3 | `test_plugin_recovery.py`, `test_pi_exact_plugins.py`, `test_plugin_end_to_end.py`, `test_plugin_project_context.py` |
| 7.1–7.3 | `test_plugin_cli.py`, `test_cli.py`, `test_plugin_end_to_end.py`, isolated installed-package commands |

Packaging checks built a wheel and sdist and installed separate base-only and CLI-extra environments. Base-only discovery ran without Click or agent-router. Its console command exited 1 with concise `zuat[cli]` guidance; the CLI-extra environment exposed plugin commands successfully. Final rebuild/check results follow below.

No live plugin installation, update, removal, restoration, or registry reset was performed. Stateful tests use temporary native homes and registries. The CLI routing suite explicitly prohibits invoking real native managers. Native unsupported capabilities remain explicit rather than being replaced with source copying or compatibility readers.

## Final verification (2026-09-05)

- Final failing-first recovery case: a native command failure after recording an operation incorrectly returned complete coverage without an operation reference. The test failed on that outcome; the implementation now returns partial/indeterminate with the pending operation ID. All 6 recovery tests passed after the fix.
- `uv run --extra cli pytest -q --tb=short`: **263 passed in 82.59s**, no failures or skips.
- `uv run --extra cli behave --format progress`: **1 feature, 4 scenarios, 23 steps passed**, no failures or skips (6.323s). Existing public profile workflows remain the qualifying Behave coverage; the plugin acceptance workflow is covered by the stateful pytest tests above.
- `uvx ruff check --select F821 src/zuat tests`: passed (undefined-name check, not a claim of full lint coverage).
- `uv build`: built `dist/zuat-0.1.0.tar.gz` and `dist/zuat-0.1.0-py3-none-any.whl` successfully.
- Installed-wheel base-only environment: importing `zuat.pub` and calling `discover_plugins("kimi", root=<temporary registry>, home=<temporary home>)` succeeded with an empty complete inventory; Click and `z_agent_router` were absent.
- Installed-wheel base-only `zuat --help`: expected exit 1 with concise optional-extra installation guidance and no traceback.
- Installed CLI-extra `zuat --root <temporary registry> plugin --agent kimi --home <temporary home> discover --json`: exit 0, successful complete empty inventory.
- `openspec validate model-plugin-provider-revisions --strict`: valid.
- `git diff --check`: passed; Git reported only the existing README line-ending normalization warning.

All implementation tasks are complete. Native limitations remain explicit: Claude/Codex exact-version acquisition and Kimi lifecycle mutation are unsupported; Pi exact acquisition is restricted to supported pinned npm revisions. Pi validation used inspected native source and isolated stateful fixtures because its installed executable cannot start with this machine's Node version. These checks did not mutate real agent configuration or installed plugins.
