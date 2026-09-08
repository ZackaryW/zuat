# Verification: establish-zuat-foundation

Reviewed 2026-09-08 against implementation commit `12aa595` and canonical-spec
commit `cd6cd87`. Documentation was subsequently aligned with accepted behavior
on 2026-09-08 following the user's approval to correct, sync, and archive.

## Summary

| Dimension | Result |
| --- | --- |
| Completeness | 49/49 tasks marked complete; implementation areas located for all 27 requirements |
| Correctness | 60 scenarios catalogued and mapped below; focused foundation tests pass |
| Coherence | Both documentation warnings resolved: public-operation scope and startup-recovery wording |

No critical implementation issue or failing runtime test was found in this
focused review. The initial review paused sync and archive because older wording
conflicted with subsequently accepted capabilities. The user approved the
documentation corrections described below; no runtime changes were required.

## Requirement and scenario mapping

Requirement names are grouped only to keep the report compact. Counts cover
every scenario in the three delta files; coverage references include current
regression tests, not proof of the historical red-first execution of every task.

| Capability / requirement group | Scenarios | Implementation and test evidence |
| --- | ---: | --- |
| Registry: Private registry isolation; Hidden Git implementation | 3 | `src/zuat/gitcore/repository.py:42`, public domain models; `tests/gitcore/test_journal.py`, `tests/pub/test_api.py`; source-provenance qualification resolved under W1 |
| Registry: Concrete human-browsable registry projection | 4 | Registry layout/catalog/profile sidecars; `tests/gitcore/test_projection.py` checks actual Claude payloads and reopen behavior |
| Registry: Append-only changed-observation journal | 3 | `repository.py:529`, public observations; `tests/gitcore/test_observation.py`, `test_projection.py` |
| Registry: Append-only lifecycle journal; Forced decisions are durable | 4 | `repository.py:260`, `:486`, public lifecycle; `tests/gitcore/test_history.py`, `tests/pub/test_profiles.py`, qualifying Behave workflows |
| Registry: Named desired-state profiles; Serialized profile transitions | 6 | `repository.py:208`, `src/zuat/pub/profile_operations.py`; `tests/gitcore/test_profiles.py`, `test_safety.py`, `tests/pub/test_profiles.py` |
| Registry: Forward-only revert | 3 | `repository.py:292`, public recovery/profile inverse operations; `tests/gitcore/test_revert.py`, `tests/pub/test_revert.py` |
| Registry: Domain history and internal recovery | 2 | `repository.py:663`, `:695`, public recovery; `tests/gitcore/test_recovery.py`, `test_history.py`; updated-operation exception demonstrated under W2 |
| Agent: Independent agent trees; Agent-owned native behavior | 4 | Separate resolver modules and registry dispatch; `tests/specs/test_resolvers.py` and Behave independent-agent workflow |
| Agent: Stable references for manageable assets | 3 | `repository.py:716`, contextual native locators and public observation; `tests/specs/test_observation.py`, `tests/pub/test_authority.py`, resolver tests |
| Agent: Complete bounded observation | 3 | Per-agent observation and `src/zuat/pub/observations.py`; `tests/specs/test_observation.py`, `tests/pub/test_authority.py` |
| Agent: Normalized manageable representation | 2 | Shared-hook fragment observation, plugin reference serialization; observation/resolver tests and canonical reference-only plugin tracking |
| Agent: Domain install and adoption | 2 | `src/zuat/pub/lifecycle.py:128`; `tests/pub/test_authority.py`, `test_revert.py`, concrete projection tests and Behave adoption workflow |
| Agent: Domain uninstall; Explicit forced reconciliation | 4 | Public selected-asset lifecycle and native preflight; `tests/pub/test_profiles.py`, `test_revert.py`, resolver conflict tests and Behave |
| Agent: Bounded and safe native access | 2 | Native bounded readers, shared-document helpers and resolver preflight; link rejection and unrelated-hook preservation tests |
| Agent: Per-agent verified outcomes | 2 | Public materialization result aggregation and profile transitions; resolver plugin-uncertainty tests and partial profile-switch tests |
| Public: Importable base package; Optional Click command | 3 | Lazy base shim and optional dependency extra; `tests/pub/test_imports.py`, `tests/cli/test_commands.py` |
| Public: Public orchestration boundary; Domain lifecycle operations | 4 | `zuat.pub` exports/service and thin CLI handlers; `tests/pub/test_api.py`, `test_imports.py`, CLI forwarding and removed-command tests |
| Public: Explicit mutation inputs | 2 | Public requests, lifecycle validation and Click required arguments; public API and incomplete CLI input tests |
| Public: Deterministic domain results; Deterministic CLI presentation | 4 | Public results and `src/zuat/cli/app.py:31`; API serialization and CLI JSON/stderr tests; scope qualification resolved under W1 |

## W1: Public-operation rules need explicit scope (resolved)

The original design says all public operations acquire the mutation lock,
observe, and journal (`design.md:93`). The result requirements also prohibit Git
hashes/refs without distinguishing the private journal from caller-selected
source repositories (`specs/git-profile-registry/spec.md:14` and
`specs/public-command-surface/spec.md:58`).

Those blanket statements do not describe the subsequently accepted API:

- `openspec/specs/managed-bundle-bootstrap/spec.md:142` expressly requires
  diagnostics not to run recovery, append events or repair state. The code in
  `src/zuat/pub/bundles/diagnostics.py:37` follows that rule.
- `src/zuat/pub/bundles/models.py:42` exposes the original source commit and
  requested source revision. These identify caller-selected source, not Zuat's
  private journal, and are the intentionally verified provenance correction.
- Bundle and extension queries have their own domain result contracts, rather
  than always returning a selected profile and asset-operation identifier.

Resolution: limited the observed-transaction description and common result shape
to applicable asset/profile lifecycle operations. The proposal, design, tasks,
and registry/public deltas now distinguish private journal Git controls from
source provenance and preserve the separate bundle/extension query contracts.
The same private-journal qualification was added to `openspec/config.yaml`.
No implemented fields were removed and no writes were added to diagnostics.

## W2: Startup recovery wording overpromises automatic work (resolved)

`design.md:106` and `specs/git-profile-registry/spec.md:122` describe fresh native
verification and a recorded recovery outcome at startup after an interrupted
mutation. The current implementation deliberately distinguishes operation kinds:

- `src/zuat/gitcore/repository.py:663` defers pending plugin-lifecycle and
  source-aware update markers to orchestration; other generic markers produce
  an indeterminate recovery event requiring fresh observation.
- `src/zuat/pub/assets.py:32` reports an interrupted update as partial with its
  pending operation ID and an explicit recovery requirement. Merely reopening
  does not restore native files or claim the update succeeded.
- `openspec/specs/source-aware-asset-lifecycle/spec.md:85` requires retained
  pending evidence. `tests/pub/assets/test_process_recovery.py` demonstrates
  process death, reopening, partial status, and a later explicit restoration.

Resolution: the design, registry delta, and task wording now describe safe
classification or preservation of interrupted state at reopen. Native verification
or restoration uses operation-specific orchestration and the original context,
with explicit restoration where required. The wording preserves pending evidence
and prohibits claiming interrupted mutations succeeded or automatically retrying
them at reopen. No automatic native restoration was introduced.

## Checks and limitations

- Foundation-focused pytest: **114 passed**, 26.81s. Covered Git core, public
  API/authority/profiles/revert/imports, resolver models/observation/contracts,
  and core CLI commands.
- Current provenance, read-only diagnostics and process-recovery pytest:
  **17 passed**, 15.60s.
- Behave: **1 feature, 4 scenarios, 23 steps passed**, 6.344s.
- `openspec validate establish-zuat-foundation --strict`: passed. Structural
  validation does not detect conflicts with later design decisions.
- The previous full run of unchanged runtime code was **423 passed, 2 skipped**;
  this review reran focused checks, not the entire suite or installed packaging.
- No live agent installation tests or real agent-home mutations were performed.
  This review does not establish all installed native-agent versions are compatible.
- Historical red-first execution is not independently established by completed
  checkboxes or today's green runs. No historical evidence was invented.

## Sync and archive status

The corrected deltas were synced into three new canonical capabilities:
`agent-asset-resolution`, `git-profile-registry`, and `public-command-surface`.
All 27 requirements and 60 scenarios were preserved. Exact normalized-content
comparison confirmed the sync, and SHA-256 checks confirmed the six existing
canonical specs were unchanged.

After correction, strict change validation passed and `openspec validate --specs`
reported **9 passed, 0 failed** (informational requirement-length notices only).
Runtime tests above were run during the initial review, not rerun for these
documentation-only corrections. The user's `.gitignore` was not edited, and no
commit was created as part of this finalization.

Archived at `openspec/changes/archive/2026-09-08-establish-zuat-foundation`.
The move preserved all eight files, including `.openspec.yaml`, verified by
SHA-256 comparison before this final report update. All 49 tasks are complete;
`openspec list --json` reports no remaining open changes.
