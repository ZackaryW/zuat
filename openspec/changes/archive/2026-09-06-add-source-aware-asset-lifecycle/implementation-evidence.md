# Implementation evidence

Native-state fixtures use temporary homes/project roots. No real agent setup or ZPP source is in scope.

## Baseline

- `uv run --extra cli pytest -q --tb=short`: 263 passed (86.52s).
- `uv run --extra cli behave --format progress`: 4 scenarios, 23 steps passed.

## Scenario coverage plan

Use pytest for the additional workflows: each can assert its complete behavior in one test. No new Behave scenario is justified.

| Capability scenarios | Behavioral coverage |
| --- | --- |
| Equal assets in two projects; equivalent paths/shared users | `tests/pub/assets/test_context.py`: references, payloads and receipts (2.1–2.2) |
| Empty second project; foreign reference/missing context | selected observation, incomplete inventory and pre-mutation guards (2.3) |
| Mixed-context profile | catalog retention, sidecars and excluded-context coverage (2.4) |
| Earlier context-free record | fresh-registry rejection without rewriting native/history state (2.5) |
| New packaged revision; local modification; matching unowned content; absence/unsupported | `tests/pub/assets/test_inspection.py`: immutable public evidence and native scope matrix (3.1–3.2) |
| Offline owned target; ambiguous provider | targeted inspection without broad observation (3.3) |
| Ordinary update; changed since inspection; ambiguous hook; no-op/missing | `tests/pub/assets/test_update.py`: force, revalidation, no-change and identity checks (4.1–4.2) |
| Shared neighbors; removed source file | precise native replacement and restoration (4.2) |
| Update/restore; forced local repair | actual-before payload and receipt/authority restoration (4.3) |
| Interrupted update; wrong-project recovery | mutation/verification/compensation injection and restart checks (4.4, 5.1) |
| Update A and restore after restart | public install–inspect–update–reopen–restore–remove workflow with two projects (5.3) |
| Python-only consumer | `tests/pub/assets/test_helpers.py` and isolated base-only wheel workflow (5.2, 6.1) |

The acceptance workflow was selected before implementation: install source A, inspect source B, update B, close/reopen, restore A and remove; skills and shared hooks in two projects, preserving neighboring/user/plugin state. This is not an actual ZPP dependency cutover.

## Red/green observations

- Project identity tests initially failed: equal projects shared references and B's hook receipt conflicted with A. Context partitions and scoped ownership made the first three tests green.
- Wrong-context revert incorrectly succeeded; mixed-profile coverage was missing; context-free catalog state was accepted. Four failing tests became green after context guards/reporting.
- Four initial inspection tests failed because the public operation was absent, then passed after implementation.
- Four initial update workflows failed because update was absent, then exposed the journal rejecting ordinary UPDATE. All passed after lifecycle integration.
- Failure/restart tests exposed missing compensation and pending intent being erased on reopen. All eight update tests then passed, including wrong-context rejection and explicit restoration.
- Forced unowned hook restoration exposed name-based observation verification; targeted verification fixed it without adopting prior content.
- Native matrix exposed Pi project-extension filename handling and install/inspect reference disagreement. Tests cover both user and project scopes.
- Existing resolver fixtures used the intentionally incompatible context-free project layout; those fixtures now use project partitions while continuing to test native destinations and unsupported Kimi project hooks.

- An actual child-process `os._exit` initially left an unrecoverable sentinel lock. Process-lifetime OS locking now releases exclusion on process death; concurrent-writer rejection and existing helper locking tests remain green.
- Pending updates are reported through public status without falsely claiming convergence. Recovery checks actual receipts as well as content/profile state, clears verified no-op pending recovery, and retains the correct baseline when restoring a restoration.
- An explicit locator initially could override a different reference; it now fails closed. Malformed native Kimi hook entries and malformed receipt fields return indeterminate rather than leaking parser exceptions or authorizing force.
- Forced creation of a managed reference without earlier broad observation initially caused a false absence in another project. Context filtering now uses reference identity independently of prior observations.
- Valid single-document skill input and compound owned hook sources were exercised red-to-green. Compound groups preserve ownership across observation, update, restore and removal while retaining neighboring hooks.
- Coexisting user skills/settings remain unchanged during project operations. A plugin-body sentinel was checked against every committed Git blob after update/restoration/removal; no plugin body entered history.

## Packaging and verification

- `uv build`: wheel and source distribution built successfully.
- Reinstalled the wheel into a fresh base-only virtual environment, using `python -I`: `zuat.pub` imports with neither `click` nor `agent_router` available.
- Executed `examples/source_asset_lifecycle.py` with that installed interpreter: install, inspection, update, restart, restoration, removal and two-project isolation passed.
- `uv run --extra cli behave --format progress`: existing 4 scenarios / 23 steps passed; no redundant Behave scenarios added.
- `openspec validate add-source-aware-asset-lifecycle --strict`: passed.
- Ruff checks passed for the new implementation modules, demonstration and new tests; `git diff --check` passed.
- Intermediate full regression runs passed at 313, 319, 324 and 325 tests.
- Final `uv run --extra cli pytest -q --tb=short`: **327 passed in 148.17s**. This includes the final compound-hook and single-document skill lifecycle changes.
- After the final implementation edits, rebuilt/reinstalled the wheel and reran the isolated public example successfully; reran Behave (4 scenarios / 23 steps) and strict OpenSpec validation successfully.

## Maintainability follow-up

The requested behavior-preserving refactor keeps the existing public API and
capability requirements. No new feature/change or compatibility layer was added.

- `pub/service.py` now owns only facade dispatch, resource lifetime, and shared
  resolver context (237 lines, previously 1,688).
- `pub/observations.py` owns observation and project-reference validation;
  `pub/lifecycle.py` owns install/adopt/remove; `pub/profile_operations.py` owns
  profile transitions; `pub/recovery.py` owns revert/restore; `pub/projections.py`
  owns shared archived/inverse projection mechanics. No public module exceeds
  625 lines. The module name `profile_operations` intentionally avoids replacing
  the existing `zuat.pub.profiles()` package function when imported.
- Pure evidence/payload mechanics moved to `utils/evidence.py` and
  `utils/payloads.py`. Public selection and result translation remain in `pub`.
- Added rationale docstrings to facade/helpers, models, plugin/artifact/source
  operations, and extracted orchestration. They explain context checks before
  native I/O, lock scope, preflight/intent/verification ordering, actual content
  versus owned baselines, pointer-only plugin persistence, and recovery handoff.
- Pre-refactor full pytest baseline: 327 passed in 151.05s. Existing behavior
  tests are regression evidence, not newly claimed red evidence for a feature.
- Focused lifecycle/update/plugin/artifact/recovery checks: 52 passed. Extraction
  regressions (helper name shadowing and a package function/submodule collision)
  were caught by existing tests and corrected without weakening their assertions.
- Public API/import checks after the module rename: 17 passed.
- Final full regression run: `uv run --extra cli pytest -q --tb=short`:
  **327 passed in 150.47s**. Existing capability tasks remain 18/18 complete.
- Final-layout Behave: 4 scenarios / 23 steps passed. Wheel/sdist build and the
  reinstalled base-only public workflow passed. Ruff `F,I` checks and formatting
  checks passed for `pub` and the extracted utility modules.
- Strict OpenSpec validation and `git diff --check` passed. No commit or archive
  was created as part of this documentation/refactoring request.

## Nested test layout follow-up

- Moved the 43 flat pytest modules into package-aligned `tests/cli`, `gitcore`,
  `pub`, `specs`, and `utils` groups, with nested asset/plugin areas. Filenames
  now omit context already supplied by their directories.
- Added package markers so repeated short filenames have distinct import names;
  updated shared-helper imports and the resolver test's repository-relative
  lookup. Test bodies/assertions are otherwise unchanged. Layout conventions and
  focused commands are documented in `tests/README.md`.
- Compared collection before/after using the exact path mapping: the same 327
  parametrized cases are discovered. Full execution, not collection counts, is
  the behavior-preservation evidence.
- `uv run --extra cli pytest -q --tb=short`: **327 passed in 149.01s**.
- Direct-file execution of native plugin adapters, public asset helpers, and
  public plugin recovery: **35 passed in 18.24s**.
- `uv run --extra cli behave --format progress`: **4 scenarios / 23 steps passed**.
- Updated current coverage references; archived verification records retain
  their historical paths. Product code and capability requirements are unchanged;
  the existing change remains 18/18 complete and unarchived.

## Finalization

- Runtime, public-module refactoring and nested test layout were committed in
  `2a382e20c254a114bc4641571912fdf944b07e1b`.
- On 2026-09-06, both capability deltas were promoted to canonical specs with
  their purposes, requirements and scenarios preserved. Strict canonical
  validation passed for all five specs; strict validation of this change passed.
- Finalization archives this completed change without promoting the older
  foundation change or claiming a ZPP dependency cutover. The runtime commit
  already records the durable decisions and verified lock-recovery lesson.

## Scope and remaining external validation

Verification ran on Windows with temporary native homes and project roots. Claude/Codex/Pi native boundaries use injected inventories/native fixtures; these tests are not certification against every currently installed external agent release. The POSIX advisory-lock branch was not executed on this Windows host. Kimi's local provider inventory was used in the installed-package demonstration.

Unsupported native scopes remain unsupported, and ambiguous provider/declaration/receipt evidence remains non-authorizing. No new native plugin capability, old ownership reader, agent-router dependency/alias, ZPP integration, dependency cutover or consumer `.gitignore` policy was added. No real agent home or ZPP source was modified. The pre-existing `.gitignore` edits and active foundation change were left untouched.
