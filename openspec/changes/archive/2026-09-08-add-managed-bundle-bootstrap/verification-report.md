# Verification: add-managed-bundle-bootstrap

Review date: 2026-09-08. Scope: current working tree, including the uncommitted
add/doctor/purge follow-up to checkpoint `af2af02`.

## Summary

| Dimension | Result |
| --- | --- |
| Completeness | 24/24 tasks marked complete; implementations located for all 12 delta requirements |
| Correctness | All 38 delta scenarios mapped to implementation and automated coverage; no missing requirement found |
| Coherence | Requested Git revision warning corrected with red/green regression coverage |

No critical issues or outstanding review warnings remain. The sole warning was
corrected at the user's request and the post-fix checks passed. Canonical specs
were synced and verified, then the change was archived on 2026-09-08.

## Requirement and scenario coverage

Paths below are repository-relative. Scenario counts include all scenarios in
each delta requirement, not counts of test functions.

| Requirement | Scenarios | Implementation | Coverage |
| --- | ---: | --- | --- |
| Build registered plugins from skill sources | 3 | `src/zuat/pub/bundles/building.py:22`, `src/zuat/utils/bundles/source.py:18`, capture utilities and agent renderers | `tests/pub/bundles/test_build.py`: build/reopen, invalid/colliding input, equivalent builds |
| Private registry with public handles | 3 | `src/zuat/pub/bundles/store.py:126`, `src/zuat/pub/bundles/building.py:131` | `tests/pub/bundles/test_store.py`, `test_build.py`: alternate roots, registered versus installed evidence, missing/tampered output |
| Explicit agent bootstrap | 4 | `src/zuat/pub/bundles/operations.py:47`, `src/zuat/pub/bundles/targets.py:36`, agent bundle adapters | `tests/pub/bundles/test_bootstrap.py`, `tests/specs/bundles/`: native evidence, independent targets, unsupported selection, trust, older builds |
| Bounded forced replacement without reconciliation | 4 | `src/zuat/pub/bundles/targets.py:36` | `tests/pub/bundles/test_replacement.py`: bounded update/delete/install, failed reinstall, foreign targets and neighbor integrity |
| Explicit removal and truthful stored outcomes | 2 | `src/zuat/pub/bundles/operations.py:91`, `src/zuat/pub/bundles/targets.py:28` | `tests/pub/bundles/test_removal.py`, `test_store.py`: partial removal and interrupted historical attempts without automatic retry |
| Self-contained extension-facing operations | 3 | Public service/module exports, `src/zuat/pub/extensions.py:15`, thin bundle CLI | `tests/pub/bundles/test_consumer.py`, `tests/cli/bundles/`; previously recorded installed base-only wheel checks |
| Small bundle convenience operations | 2 | Public `add_bundle` delegates build then exact-revision bootstrap | `tests/pub/bundles/test_add.py`: intervening build cannot alter selection; partial results retained |
| Read-only bundle diagnostics | 2 | `src/zuat/pub/bundles/diagnostics.py:37` | `tests/pub/bundles/test_diagnostics.py`: missing/modified output, unavailable/unsupported manager, no state repair or journal writes |
| Explicit bounded compiler cleanup | 2 | `src/zuat/pub/bundles/cleanup.py:9`, `src/zuat/utils/bundles/removal.py` | `tests/pub/bundles/test_cleanup.py`: scoped deletion, native failure, link rejection, retry safety and preserved neighbors |
| Public plugin operations | 3 | Public service, module exports, generalized extension type and CLI | `tests/pub/plugins/`, `tests/cli/`, `tests/pub/extensions/test_registration.py`; prior base-only packaging evidence |
| Generic artifact extension registration | 6 | `src/zuat/pub/extensions.py:15`, `src/zuat/pub/extensions.py:67`, service registration and artifact dispatch | `tests/pub/extensions/test_registration.py`, `tests/pub/plugins/test_artifacts.py`, `test_end_to_end.py`: locators, unknown/optional locators, inert registration, conflicts and independent scopes |
| Reference-only durable plugin records | 4 | Compiler store separation, bundle journal allowlist and existing plugin safety filtering | `tests/pub/bundles/test_isolation.py`, plugin persistence tests: mixed providers, sensitive output and reachable historical blobs remain reference-only |

## Resolved finding: requested Git revision provenance

The initial review found that the design promised the requested Git ref but the
compiler saved only the source locator and resolved commit. Exact-commit building
worked; provenance after reopening was incomplete.

The correction adds `BundleBuild.source_revision` and persists it with each new
Git build in `src/zuat/pub/bundles/building.py`. Store reads and acquisition share
the existing bounded selector validation from `src/zuat/utils/bundles/source.py`.
Local inputs report no Git revision. Equivalent builds retain their original ref
and commit, even when requested through another ref or an identical-content
commit; source selection does not change content-addressed build identity.

`tests/pub/bundles/test_provenance.py` established **11 expected failures** before
implementation (missing public provenance and accepted malformed metadata), then
**11 passes** after implementation. It covers branches, tags, HEAD, exact commit
selectors, public reopen/list/get, original-provenance reuse, local inputs and
fail-closed index validation. The journal allowlist regression also explicitly
rejects source-revision metadata. No journal schema or installation behavior was
changed, and no historical missing ref is inferred or backfilled.

## Initial review checks (before correction)

- `uv run pytest -q`: **412 passed, 2 skipped**, 227.11 seconds.
- `uv run behave`: **1 feature, 4 scenarios, 23 steps passed**, 6.279 seconds.
- `uv build`: wheel and source distribution built successfully.
- `openspec validate add-managed-bundle-bootstrap --strict`: passed.
- `git diff --check`: passed; Git emitted existing LF/CRLF conversion notices.

## Post-correction checks

- Focused regression: **11 passed**, 12.57 seconds, after **11 failed**, 24.88 seconds.
- Fresh installed base-only wheel: **11 passed**, 12.40 seconds; import location
  confirmed as installed `site-packages` and Click confirmed absent.
- Behave: **1 feature, 4 scenarios, 23 steps passed**, 7.769 seconds.
- Wheel/source build, strict change validation and scoped Ruff checks passed.
- Full post-correction pytest regression: **423 passed, 2 skipped**, 277.73 seconds.

## Limits and finalization state

- The two pytest skips are opt-in installed native probes. Live agent mutations
  were not run in this review. Existing implementation evidence records earlier
  successful temporary-home Codex/Claude probes and a Pi startup failure caused
  by the installed Node/undici combination; Pi live compatibility remains
  unverified here. Native-boundary fixture coverage is not a live-runtime claim.
- The installed base-only wheel reran the focused provenance tests after the fix.
  Broader installed CLI/native consumer checks were not repeated; their prior
  results remain in `implementation-evidence.md`.
- This is a focused implementation/spec review and regression run, not an
  exhaustive security audit or a claim of full predecessor feature parity.
- Initial verification and the correction did not commit or archive work.
  Subsequent authorized finalization synced all four delta capabilities and
  validated all six canonical specs before archiving this directory; all ten
  change files, including hidden metadata, were preserved during the move.
  The unrelated `.gitignore` edits and old
  `openspec/changes/establish-zuat-foundation/` artifacts were left untouched.
