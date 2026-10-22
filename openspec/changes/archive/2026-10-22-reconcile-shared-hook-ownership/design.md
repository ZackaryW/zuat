# Design

## Context

See `proposal.md` for motivation and the two delta specifications for behavior. Inspection currently uses `selected_fragment` in `utils/inspection.py`: it tries exact baseline declarations, falls back to the sole declaration of an event, and otherwise raises an identity error. For groups it reconstructs results in native order. `AssetOperations.inspect` catches resolution errors by returning an indeterminate result with no receipt or source evidence. Source-driven install follows a separate planning path and can append the desired group even when targeted inspection cannot identify it.

The 2026-10-22 Powerspec investigation reproduced six cases using isolated homes/registries: exact unowned hooks rejected by the caller, reordered owned hooks classified as conflict, unrelated insertion correctly reused, legacy unowned hooks duplicated by install fallback, genuinely edited hooks rejected, and correct current hooks with a valid stale receipt rejected. Read-only inspection of the live Codex configuration found the last case: desired hooks matched exactly while the receipt recorded earlier handler fields and matcher. These observations establish failure examples, not tests of the proposed implementation or evidence about who caused the live drift.

Existing ZuAT machinery already supplies the main contract: `inspect_asset(AssetInput)`, `update_asset(AssetInput, force=False)`, `install(ZuatRequest)`, operation identifiers, and `restore_all`. Update freezes source bytes, captures actual native content and prior ownership separately, begins recoverable intent, rechecks state, verifies replacement, and publishes profile/history. Recovery uses inverse profiles and restores receipts independently. This design extends that path rather than introducing another lifecycle coordinator.

## Goals / Non-Goals

**Goals:** Resolve uniquely identifiable shared-hook groups; preserve baseline/source/ownership distinctions; make receipt-only forced updates recoverable; prevent inspection/install disagreement from producing duplicate callbacks; retain existing context and provider boundaries.

**Non-Goals:** Automatic adoption during inspection; private receipt editing by callers; heuristic recognition of Powerspec command names or aliases; repair of malformed receipts; choosing between duplicate groups; blanket order-insensitive fingerprints; live-machine cleanup; new CLI commands; a new persistent identity format; changes to Powerspec or dependency publication in this change.

## Decisions

### 1. Reuse explicit forced update for ownership repair

Keep public signatures and existing classification names. A valid receipt is evidence of a recorded baseline, not proof that current native content still equals it. Once a unique complete group is identified, return its actual fingerprint and source equality independently of the valid receipt fingerprint. A source-matching stale baseline is `conflict`, with `owned=True` and `source_matches=True`; invalid receipt contents remain indeterminate and cannot authorize repair. When selection remains unresolved, preserve independently validated receipt/source fields where available, leave the observed fingerprint/source match unknown, and explain the identity failure. Consumers must use classification and completeness rather than the ownership flag alone.

`update_asset(asset, force=True)` is the explicit authority-reconciliation request. Without force, the same conflict remains rejected. Receipt-only repair returns an ordinary successful update operation with `data["changed"]=True`, plus additive `native_changed=False` and `ownership_changed=True`. `changed` refers to managed-state change, not necessarily a native rewrite. A current no-op retains `changed=False`, does not create a mutation event, and reports both additive flags false. Ordinary successful content replacement reports its actual native/control effects. Document these semantics without requiring consumers to inspect private Git or receipt files.

A separate repair API was considered but would duplicate selection, locking, capture, and recovery. Automatically calling a stale receipt current was rejected because it would contradict the existing conflict contract and erase the distinction between matching bytes and authority.

### 2. Resolve groups using complete evidence, never incidental position

Validate source, receipt schema/fingerprint/destination, scope, provider eligibility, and supplied reference/locator before selection. For valid receipt-backed groups:

1. Prefer a unique complete exact baseline match. Preserve actual relative order when reconstructing the selected group. If baseline and desired groups coexist as distinct complete groups, report competing candidates rather than overwrite one or leave duplicates behind.
2. If exact baseline selection is incomplete, accept a unique complete exact desired-source group only when every surviving exact baseline member lies within that group and no member is claimed by another receipt/provider. This identifies the current content for explicit reconciliation; it does not bless the receipt or authorize an unforced update.
3. Preserve the existing single-declaration fallback only where an event has one unambiguous candidate, no competing claims, and the complete group remains one-to-one. Do not extend this into fuzzy command/matcher similarity. Otherwise return indeterminate rather than partial success or absence.

For unowned source-only groups, complete exact matches identify adoption candidates. Verified absence requires all requested events to have no candidate declarations, unless the resolver has other supported explicit evidence proving a distinct target. Same-event differing declarations are not evidence of absence. Partial matches, duplicates, overlap, and multiple possible mappings remain unresolved; callers can select existing supported references where they genuinely identify a target, but a positional hint cannot override ambiguity.

Receipt, reference, and candidate evidence must agree. Selecting an exact desired group cannot steal another asset's declaration. Reordering retains the recorded identity but remains a fingerprint difference: no generic matcher-overlap analysis or sorting is introduced. Existing adapters have no established order-equivalence rule, so this change treats reordered groups as conflicts and leaves explicit forced update as the reconciliation path.

### 3. Small shared selection mechanics; application policy stays outside

Use the existing `fragment_parts`, `combine_fragments`, and `fragment_fingerprint` operations, standard-library collections, JSON, and SHA-256. Add or factor an internal exact-group selection operation alongside `selected_fragment`; do not expose a new public utility package. No third-party matcher is needed: the missing behavior is bounded exact structural comparison, not schema inference or a matching framework.

Portable internal contract: given a native document and a desired fragment of the supported mapping/list shapes, return the complete selected fragment plus its concrete member positions, or an explicit absent/partial/ambiguous outcome. Positions are transient evidence within that document, never durable identity. Preserve native ordering, enforce one-to-one membership, distinguish zero matches from partial matches, and reject malformed shapes and duplicate matches. The operation is pure, does not mutate inputs or access filesystem/registry state, and yields equivalent evidence on repeat calls. Another tool managing a group of declarations in a shared configuration document can reuse these mechanics without agent or registry types. Domain-neutral fixtures cover mapping/list groups, neighbors, duplicates, omissions, and order changes.

Resolvers supply native shape, provider eligibility, scope, receipt validation, and conflicting-owner checks. `pub/` supplies authorization, operation intent, and publication. Extend existing helpers rather than creating speculative abstractions; helper names can follow local conventions without changing this contract. Verify the pure slice before wiring it into inspection and installation.

### 4. Source-driven install uses the same identity gate

Apply target-aware preflight under the registry lock before native mutation, including rechecks after any observation step. Share the evidence/selection mechanics with targeted inspection; do not route this through a whole-agent public status call as proof of target ownership. A fully matching unowned independent group can use the existing adoption path. A current owned group can be reused. Existing supported owned-update cases keep their locked reconciliation checks.

If shared-hook identity or provider status is indeterminate, fail before mutation rather than rely on `apply_shared_hook`'s append fallback. Force does not turn unknown into absent. Preserve legitimate insertion into absent events and unrelated settings. Reject another receipt's overlapping claim rather than changing ownership by matching identical bytes. Existing observation/rejected-operation history may still be recorded; no selected-profile success or authoritative target evidence is published for a rejected install.

This tightens source-only installation: configurations that previously accepted a new same-event group despite unresolved differing entries will now fail with an identity diagnostic. It is intentional protection against the reproduced duplicate case. Callers need a verified target or explicit supported selection; this change does not guess which legacy commands should be removed.

The user confirmed during implementation that the previous forced positional overwrite contract is retired too: array locators may address an asset, but cannot authorize overwriting its current occupant. Reordered independently owned declarations retain their verified identities and duplicates remain non-authorizing even with an explicit locator. Update the prior positional-restoration regression accordingly.

### 5. Receipt-only repair uses the existing recoverable transaction

After normal target resolution and force checks, distinguish source-equal content with stale authority from content replacement. Freeze source and capture actual selected content, prior ownership, prior profile baseline, and selected membership/order before beginning intent. Recheck those facts under the existing lock. In the receipt-only branch, skip native serialization and replacement entirely, preserve bytes and modification time, and save only the verified new ownership record. Verify native evidence again before profile/event publication. Record the existing update operation kind, stable reference, recovery identifier, and receipt-only effect metadata; do not introduce another journal or rewrite existing events.

Reuse the existing compensation and `restore_all` path, extending it to verify native content and old receipt separately. Restore the original stale receipt and original profile evidence, not a receipt synthesized from the current source. For a receipt-only restore where native content is still unchanged, avoid rewriting it. A concurrent edit or new competing declaration must prevent stale authority publication; compensate control state only when safe, preserve unrelated edits, and retain partial/pending recovery evidence when convergence cannot be established.

Failure injection must cover before receipt save, after receipt save, before/after profile publication, and before completion is recorded. A process restart must expose an unresolved operation rather than treating matching hooks as proof of completion. Use the existing process-recovery tests and explicit context checks; do not claim filesystem-plus-journal atomicity.

### 6. Verification and consumer handoff

Use pytest through `uv run pytest`, with red/green evidence for each changed behavior. Test public inspection/install/update/restore and persistent file/control outcomes, not only helper return values. Cover Codex and Claude multi-handler JSON groups and Kimi's supported user TOML groups; retain unsupported Kimi-project and Pi dedicated-extension behavior. Reuse existing provider, malformed receipt, symlink, cross-project, offline-owned inspection, and base-without-Click coverage. Use only temporary homes and explicit registry/bundle/project roots; subprocess fixtures must isolate relevant home/app-data variables so tests cannot repair live state.

Update README and `examples/source_asset_lifecycle.py` or a focused companion example with a consumer decision table: current -> reuse; outdated -> unforced update; exact unowned -> explicit non-forced install/adopt; absent -> install; source-matching owned conflict -> explicitly authorized forced update; indeterminate/unsupported -> stop with diagnostics. Document that ownership repair is a state change despite unchanged native content and that callers must reopen/reinspect after completion.

The Powerspec follow-up must adopt exact unowned matches, remove its indeterminate-install fallback, expose an explicitly authorized hook-repair path rather than broadening its skill-only force silently, pin a verified ZuAT revision, and exercise the stale-receipt and no-duplicate cases. Capture this handoff in ZuAT docs; do not edit Powerspec or automatically repair the user's machine in this change.

## Risks / Trade-offs

- Exact desired content could be mistaken for the old installation -> Require valid receipt context, unique complete selection, no competing baseline remnants/owners, and explicit force; reject unresolved identity.
- Existing consumers may rely on permissive append behavior -> Document the tightened preflight and test legitimate absence/adoption alongside rejection cases.
- Reordering may affect execution -> Preserve native order and report conflict; do not change fingerprint meaning or receipt schema globally.
- Receipt publication can fail independently of native content -> Capture control and content before-state separately, verify after reopen, and retain recovery intent on uncertainty.
- General observation may assign different fragment identities when a receipt is stale -> Test status/reopen/targeted inspection together and retain the established semantic reference; do not infer group authority from individual observed entries.

## Migration Plan

No eager receipt migration, registry replacement, or new dependency is required. Existing receipts remain readable; a corrected implementation provides better evidence and explicit repair through existing APIs. Deploy only after focused and full tests pass. Existing application adoption requires its own dependency update. Rollback reverts the code while retaining forward journal history; receipt-only operations must remain restorable through captured existing-format evidence. Validate restored legacy receipt behavior and ordinary lifecycle operations before declaring compatibility.
