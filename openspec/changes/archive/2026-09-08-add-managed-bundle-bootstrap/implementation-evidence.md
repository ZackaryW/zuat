# Implementation evidence

## Baseline (before implementation)

- `uv run --extra cli pytest -q --tb=short`: 327 passed, 161.58s.
- `uv run --extra cli behave --format progress`: 1 feature, 4 scenarios, 23 steps passed, 6.860s.
- Baselines are regression evidence, not red evidence.

## Scenario-to-test map

Scenario coverage is grouped below; observed execution evidence follows.

| Delta | Scenarios | Nested test location |
| --- | --- | --- |
| managed-bundle-bootstrap | Build without installation; Invalid or colliding source; Repeated equivalent build | `tests/pub/bundles/test_build.py` |
| managed-bundle-bootstrap | Extension uses an alternate store; Build is not installed evidence; Missing build output | `tests/pub/bundles/test_store.py`, `test_build.py` |
| managed-bundle-bootstrap | Bootstrap supported targets; Unsupported target and successful neighbor; Force without source trust; Agent still uses an earlier build | `tests/pub/bundles/test_bootstrap.py`, `tests/specs/bundles/` |
| managed-bundle-bootstrap | Update failure without force; Forced replacement succeeds; Replacement installation fails; Ambiguous or foreign target | `tests/pub/bundles/test_replacement.py` |
| managed-bundle-bootstrap | Partial removal; Restart after interruption | `tests/pub/bundles/test_removal.py`, `test_store.py` |
| managed-bundle-bootstrap | Base-only consumer; Equivalent CLI operation; Extension composes bundle operations explicitly | `tests/pub/bundles/test_consumer.py`, `tests/cli/bundles/` and installed-wheel evidence |
| plugin-command-surface | Plugin lifecycle through the public interface; CLI and Python parity | existing `tests/pub/plugins/`, `tests/cli/`; bundle additions above |
| plugin-command-surface | General extension through the base Python package | `tests/pub/extensions/test_registration.py`; base-wheel verification |
| plugin-contribution-resolution | Registered extension resolves an artifact; Unknown extension; Extension without artifact location; Explicit registration is inert; Conflicting registration preserves the original; Registration scopes remain independent | `tests/pub/extensions/test_registration.py`, migrated `tests/pub/plugins/test_artifacts.py`, `test_end_to_end.py` |
| plugin-revision-tracking | Snapshot mixed providers; Native output contains sensitive payloads | existing plugin reference-isolation tests; `tests/pub/bundles/test_isolation.py` |
| plugin-revision-tracking | Build outputs remain outside tracking history; Compiler exception does not authorize plugin capture | `tests/pub/bundles/test_isolation.py` |

## Native contracts inspected without mutation

- Codex help exposes plugin add/remove/list and marketplace add/list/upgrade. Local catalog directory registration is supported; upgrade help describes refreshing Git snapshots, not replacing a local bundle. Marketplace inventory JSON is an object with a `marketplaces` list and `name`/`root` fields; optional `marketplaceSource` describes Git sources.
- Claude help exposes plugin install/update/uninstall, user scope, and marketplace add/list with local paths and JSON list output. Existing inventory includes `name`, `source`, and `installLocation`. A local catalog must be validated in an isolated fixture before claiming native support; a raw plugin-directory install is not the catalog route.
- Installed Pi package `@earendil-works/pi-coding-agent` is 0.82.1. Its installed `dist/package-manager-cli.js` documents `--approve`/`--no-approve` and targeted `update --extension`. `dist/core/package-manager.js` registers local source paths and reports those paths through package inventory; native manifest/identity separation still needs verification.
- Live `pi --help` fails before command parsing in undici (`markAsUncloneable`, Node 20.19.0). No native runtime repair attempted. This limits live smoke evidence, not permission to invent private native config edits.
- Real home inventories were read only. No real agent installation/configuration mutation.

## Red/green increments

- Extension registration: 5 new tests failed on missing new API / presence of old API before changes.
- Artifact contract migration: migrated focused tests produced 5 failures, 7 passes before implementation. After replacing the contract, extension/artifact/end-to-end subset: **19 passed**, 12.27s.
- Compiler store: 10 new tests failed before implementation; after root isolation, typed errors, atomic index/lock and historical attempt queries: **10 passed**, 3.75s.
- Bundle compiler: 15 new tests failed before implementation; after captured input compilation, independent agent renderers and verified resolution, bundle subset: **25 passed**, 10.39s.

## Native and integration verification

- Bootstrap/replacement subset started with **9 failures** (missing native bundle APIs). Implemented catalog setup, per-agent orchestration, bounded force fallback, and existing observation-only recovery.
- Catalog/native adapter subset: **40 passed**, 17.55s. This includes preserving unrelated catalog registrations and retaining the existing unresolved treatment of arbitrary Pi local packages.
- Opt-in installed native probe (`ZUAT_TEST_NATIVE_CATALOGS=1`): **2 passed**, 13.54s, covering Codex and Claude local catalog setup, actual install, fresh current check, and remove in temporary homes. Codex initially rejected root-level `marketplace.json`; corrected its agent-owned layout to `.agents/plugins/marketplace.json`, then reran green. Claude's local `installLocation` source evidence was verified against the installed CLI.
- Pi's local route is bound only from selected compiler registrations; native package names alone do not authorize a stable bundle identity. Installed-version evidence comes from rediscovered native package manifests. Pi live execution remains limited by the installed Node/undici startup failure noted above; stateful native-boundary fixtures cover its local install, replacement, removal, and pointer isolation.
- Removal/extension-consumer/history-isolation subset started **5 failed, 1 passed**; after implementing verified-absent results and allowlisted bundle metadata: **6 passed**, 16.18s. The consumer explicitly calls an extension method, retains public handles across reopen, replaces independently, injects a post-delete install failure, retries explicitly, resolves artifacts, and removes.
- Omitted-agent selection and CLI parity started **3 failed**, then **3 passed**, 2.85s after availability selection and thin public-only Click handlers.
- Additional red/green checks addressed rejecting overlap *before* Git initialization (**4 failures** including missing captured source mappings), validating malformed build digests, exposing observed version/activation (**4 failures -> 4 passed**, 4.96s), distinct catalog identities for differently named bundles from one source, and refusing success after lower-level neighbor verification fails (**2 failures -> replacement subset 6 passed**, 13.62s).
- Missing selected output was initially incorrectly labeled generic indeterminate; a failing public bootstrap test now verifies **unavailable/build-output-unavailable** with no native calls (**1 passed**, 0.82s after correction).
- Final containment review reproduced a catalog manifest-parent redirect with a failing test. Compiler/catalog/source writes now share ancestor checks for links and Windows reparse points before directory creation or replacement; the unrelated external catalog remains intact.
- Local Git fixtures with case-colliding support paths and reserved `NUL` entries previously compiled while silently dropping files on Windows. A test-local Git setting permits constructing these otherwise valid cross-platform Git trees; after observing the intended failures, compilation now rejects them before materialization. Index writes also enforce the same 8 MiB bound as reads, preserving the previous index on overflow. The focused containment/portable-path/index subset passed **4 tests**, 2.96s.
- A further failing public test established that Pi's durable `local/<name>` ID must never be sent as an untrusted relative install path. Native validation now rejects that form before any command; bundle preparation supplies only an explicitly trusted runtime route. Pi/bundle/native adapter subset: **41 passed**, 10.42s.
- Source-to-generated mappings remain in compiler registration metadata. Build bodies, raw stderr, credentials, local source/output routes, and extension code are excluded from Git/profile/recovery state. The isolation test examines reachable historical Git blobs as well as control files after successful bootstrap and failed forced replacement.

## Packaging and documentation verification

- `uv build`: source distribution and wheel built successfully.
- Fresh base-only wheel environment contained only Zuat, GitPython/gitdb/smmap, and PyYAML. Isolated interpreter inspection confirmed no Click, Typer, agent-router, or skill2plugin import and verified the packaged MIT NOTICE. Import path was installed `site-packages`, not the repository source tree.
- Repeated the final wheel's base-only public example with `uv run --no-project --isolated --with ./dist/zuat-0.1.0-py3-none-any.whl python -I examples/managed_bundle.py --agent claude`: build, reopen, actual temporary-home native bootstrap, artifact resolution, and removal verified.
- Invoking the base-only console entry point gives the existing concise `zuat[cli]` installation guidance without a traceback.
- Installed `./dist/zuat-0.1.0-py3-none-any.whl[cli]` and pytest in a separate test environment; installed-package CLI parity plus extension consumer: **3 passed**, 8.17s.
- Reinstalled the latest built wheel and repeated installed CLI/public-consumer checks: **3 passed**, 20.71s. The latest fresh base-only wheel also passed the native Claude public example with Click/Typer/predecessor imports absent.
- README documents exact signatures, optional locator/inert registration, context/store selection, trust versus force, unsupported Kimi, native limitations, historical queries, retained builds, and no implicit loading/retry/reconciliation/rollback. `openspec/config.yaml` gained only the stable private compiler-store/public extension boundaries.

## Regression and final checks

- First full implementation run: **382 passed, 2 skipped**, 214.12s. The skips are opt-in native probes executed separately above.
- Subsequent complete regression runs: **385 passed, 2 skipped**, 223.58s; then **389 passed, 2 skipped**, 220.35s.
- Existing Behave suite: **1 feature, 4 scenarios, 23 steps passed**, 6.729s. No duplicate presentation-only Behave scenarios were added.
- Refreshed Behave run after hardening: **1 feature, 4 scenarios, 23 steps passed**, 6.688s.
- Focused new implementation Ruff checks pass. `openspec validate add-managed-bundle-bootstrap --strict` and `git diff --check` pass.
- Final combined pytest run, including the Pi install-route regression and all containment/portable-path/index checks: **390 passed, 2 skipped**, 235.39s. The two opt-in native probes passed separately. Strict change validation and diff checks passed again after this run. All 19 implementation tasks are complete.
- No real agent home was selected for mutation. Native integration writes were confined to temporary homes/stores. No agent-bundler/ZPP source, old foundation artifacts, or unrelated `.gitignore` edits were changed. No commit or archive was created.

## Minimal integration follow-up

The original implementation was checkpointed in `af2af02`. The approved follow-up
adds small convenience surfaces, not the predecessor's reconciliation engine.

- One-call add: **4 failing tests** on the absent API, then **4 passed**, 4.19s. The workflow pins its own build despite an intervening publication, preserves partial success, rejects untrusted bootstrap without native writes, and never bootstraps invalid source.
- Read-only diagnostics: **4 failing tests**, then **4 passed**, 2.76s. Checks cover manager availability, unsupported Kimi, output integrity, safe failures, invalid registration, and preserving pending attempts/native files/journal history. Added missing-file coverage alongside modified-file coverage.
- Explicit purge: **6 failing tests** on the absent option/result, then **6 passed**, 13.07s. Complete removal deletes only selected compiler build/catalog trees, preserves neighbors and source files, rejects partial filters and links, and retains registration on cleanup I/O failure. Additional coverage verifies that a manually restored native installation prevents a later purge retry.
- CLI convenience: **6 failing tests** on absent commands, then all bundle CLI tests **8 passed**, 2.61s. Public forwarding preserves source/revision/agent/trust/force/root choices, typed JSON results and unhealthy exit codes in both output formats.
- Initial focused bundle/CLI/utility regression: **73 passed**, 76.13s. Latest cleanup/diagnostics subset: **12 passed**, 19.90s, including the restored-native retry guard and missing-file check.
- Wheel and source distribution built successfully. A fresh installed base-only wheel passed public add/get/resolve/doctor/purge with explicit temporary stores and unsupported Kimi; Click, Typer, agent-router and skill2plugin imports were absent. This is packaging/unsupported-boundary evidence, not a new live native-agent probe.
- Installed CLI wheel: **6 passed**, 2.16s, executing the new CLI consumer workflow and result presentation/exit tests from isolated Python.
- Qualifying Behave regression: **4 scenarios / 23 steps passed**, 7.509s. No duplicate Behave scenarios were added.
- Scoped Ruff and strict OpenSpec validation passed. README documents purge's retained native marketplace registrations and no orphan sweep. Existing `config.yaml` boundaries need no product-detail additions.
- Full final pytest regression: **412 passed, 2 skipped**, 261.18s. The skips are the existing opt-in native probes; this follow-up used isolated native-boundary fixtures rather than repeating live native tests. All **24 tasks** are complete.
- No real agent home, predecessor repository, older foundation artifact, or user `.gitignore` edit was changed. Purge tests deleted only their own temporary generated outputs. This follow-up remains uncommitted and the change remains unarchived; checkpoint `af2af02` is unchanged.

## Verification correction: requested Git revision (2026-09-08)

- Review found the design promised retention of the requested Git ref, but only
  the resolved commit was retained. Reopened task 2.1 in this same change.
- Added `tests/pub/bundles/test_provenance.py` before implementation: **11 failed**,
  24.88s, on missing `source_revision` and accepted invalid persisted selectors.
- Added read-only `BundleBuild.source_revision`, private compiler persistence and
  shared acquisition/index validation. Local builds report `None`; equivalent
  builds preserve the original ref/commit rather than replace provenance or
  change content-addressed identity. No journal metadata allowance was added.
- Focused tests then passed: **11 passed**, 12.57s. Extended the journal allowlist
  regression to reject source-revision metadata. README, design, task 2.1 and the
  verification report document the correction; the stable config is unchanged.
- Fresh installed base-only wheel ran the same **11 tests successfully**, 12.40s,
  after confirming imports came from `site-packages` and Click was absent.
- Full regression: **423 passed, 2 skipped**, 277.73s. The skips remain the opt-in
  native probes; no live agent installation test was run for this correction.
- Behave: **1 feature, 4 scenarios, 23 steps passed**, 7.769s. Package build,
  strict change validation, scoped Ruff checks and diff checks passed.
- All **24 tasks** are complete again. No existing missing Git ref was inferred
  or backfilled, no real agent home was mutated, and unrelated work was preserved.
  This correction does not itself archive the change or create a commit.

## Finalization (2026-09-08)

- Committed the convenience APIs, source-ref correction, tests and README in
  `12aa595` with two validated zmem decisions covering retry-safe cleanup and
  immutable build provenance.
- Synced all four delta capabilities into canonical specs, preserving unrelated
  requirements and existing purposes. All **six canonical specs** validate.
- Archived this change as `2026-09-08-add-managed-bundle-bootstrap` after verifying
  every delta was applied. All ten files, including hidden change metadata, were
  preserved during the move. The earlier verification warning is resolved.
- The user `.gitignore` edits and old foundation artifacts remain outside the
  finalized work. No runtime implementation changed during archival.
