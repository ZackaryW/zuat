## 1. Establish the behavioral baseline

- [x] 1.1 Run the current pytest and qualifying Behave suites, record their commands/results, and map every scenario in both capability specs to planned behavioral coverage. Use temporary homes, two project roots, shared user state and injected plugin managers; select the public install-inspect-update-restart-restore-remove acceptance workflow before implementation. Existing green tests are regression evidence, not red evidence; use pytest unless an additional Behave workflow establishes genuinely different cross-component evidence.

## 2. Isolate ordinary project asset state

- [x] 2.1 Add and run failing tests for equal named/content skills and hooks in two projects and equivalent normalized paths; implement context-aware ordinary asset identities and observation paths using existing context primitives, then verify distinct project references and stable user-scoped identity.
- [x] 2.2 Add failing ownership tests for installing/adopting/updating/removing equal-named assets in separate projects; thread context through ordinary ownership stores and resolver calls, then verify native and receipt state in the other project is unchanged.
- [x] 2.3 Add failing observation/listing tests for an empty second project, incomplete discovery and foreign asset references; implement selected-context filtering and retention, then verify no false absence or cross-context selection and no mutation without required project context.
- [x] 2.4 Add failing profile/catalog tests for profiles holding both projects plus user assets; implement context-bound paths, sidecars, desired enumeration and reporting, then verify applying A preserves B's entries and state and does not claim B was applied.
- [x] 2.5 Add failing tests for earlier context-free project records; reject ambiguous state before native mutation with fresh-registry guidance, then verify original history/files are preserved and valid user-only and plugin-context regressions remain green.

## 3. Expose source-aware inspection

- [x] 3.1 Add failing public tests for all inspection classifications, source/name/reference mismatch, immutable result values and separate source-match/ownership evidence; introduce the public inspection contract and focused facade delegation, then verify matching foreign content remains unowned and local modifications remain conflicting even when matching the supplied source.
- [x] 3.2 Add failing native-boundary tests across supported agent skill/hook scopes, malformed sources/receipts and ambiguous shared-hook fragments; implement per-agent target resolution and neutral comparison primitives, then verify accurate absent/current/outdated/conflict/unsupported/indeterminate results without native writes or adoption.
- [x] 3.3 Add failing tests for unavailable plugin discovery with independently verified owned targets and unknown-provider candidates; implement targeted inspection without mandatory whole-agent observation, then verify usable owned inspection, conservative indeterminate outcomes and no plugin bodies entering durable global state.

## 4. Implement one recoverable targeted update

- [x] 4.1 Add failing public update tests for outdated, current, absent, unowned, conflicting and changed-since-inspection targets; implement update preflight and reuse the existing operation coordinator without nested operations, then verify explicit force boundaries, truthful no-change results and rejection before unsafe writes.
- [x] 4.2 Add failing native replacement tests for removed skill files, shared-hook neighboring insertions/settings and bundled-provider rejection; implement precise targeted replacement and verification, then verify complete selected projections and unchanged neighboring assets, configuration and plugins.
- [x] 4.3 Add failing update/restore and update/revert tests including forced replacement of locally modified and unowned content; capture actual pre-update payload and authority, append ordinary UPDATE history and adapt inverse dispatch, then verify restoration recovers the true prior content/authority without erasing the update.
- [x] 4.4 Add failing tests for mutation failure, failed postcondition verification and failed compensation; preserve safe before/after evidence and honest results, then verify unverified target profiles are not published and pending recovery remains actionable where needed.

## 5. Verify restart and consumer-facing context

- [x] 5.1 Add failing interruption/restart tests for ordinary project updates and recovery under the wrong project; implement context-aware pending intent and recovery/restore/revert checks, then verify A can be restored after restart, B stays untouched, and wrong-context recovery preserves pending evidence without native mutation.
- [x] 5.2 Add failing module-level public tests forwarding root/home/project_root/trust_project through inspection, update and relevant existing lifecycle helpers; implement consistent context propagation, then verify parity with a stateful Zuat consumer without importing internal modules.
- [x] 5.3 Author and run the selected public consumer workflow red before filling any remaining integration gaps: install A, inspect B, update, reopen, restore A and remove, with two project scopes and shared-hook neighbors. Rerun to green and verify native content, ownership, domain history and preserved user/plugin state; do not treat simulated ZPP-shaped coverage as an actual ZPP dependency cutover.

## 6. Package, document and hand off

- [x] 6.1 Document the exact public signatures, result classifications, force/adoption boundaries, context requirements, rollback example and explicit exclusions; execute the documented public workflow in an isolated base-only installed package without Click or agent-router. If packaging behavior needs changing, record a failing check first and rerun it to green.
- [x] 6.2 Run all affected tests, full pytest, existing qualifying Behave tests and any justified additions, package build, and `openspec validate add-source-aware-asset-lifecycle --strict`; record observed results and uncovered/unsupported cases. Confirm tests touched no real agent home and no ZPP dependency or source files were changed before marking implementation complete.
