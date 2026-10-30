# Design

## Context

The public Powerspec fixture installs a group, clears its native declarations, and installs again. Source-aware inspection reports absent, but `contains_fragment` filters missing mapping keys out of its `all` expression and the older lifecycle path reports current. Correcting that predicate exposes a second issue: the old receipt-only check treats verified absence as conflict.

## Goals / Non-Goals

Restore semantically absent owned hooks while retaining the new identity restrictions. Add an opt-in receipt-only guard to the public update API. No positional replacement, force expansion, or unrelated plugin changes.

## Decisions

### Existing portable containment helper

Extend `contains_fragment(document, fragment, *, key='hooks') -> bool` in `utils/documents.py`. It takes ordinary mapping/list values, performs no mutation, and requires each requested event to have a list containing every requested member. Missing keys and incompatible values return false. This also fits an external configuration reconciler checking declared event lists. Retain existing list and scalar equality semantics.

Reuse Python mapping lookup, `isinstance`, and `all`; no third-party parser or diff package is needed for this small predicate correction. Test with domain-neutral `events` mappings before integration. Exact uniqueness remains the responsibility of the existing group-selection helper, not this containment predicate.

### Semantic absence drives installation

Keep agent/provider validation in the resolver. Once `_preflight_hook_install` establishes semantic absence, do not let the older receipt containment check recategorize it. Route shared-hook installation through the already verified target replacement path, extending it to add a verified absent group without removing an array occupant. It re-inspects before publication and checks the resulting complete group. Existing update still rejects absence at its public boundary.

### Receipt-only authorization

The user approved `receipt_only=True` on both public forms of `update_asset`. Its default is false for compatibility. Inside the operation lock, before any mutation or no-op return, require a valid owned shared-hook group whose observed fingerprint equals the intended source. Existing force requirements still govern stale receipt repair; current owned groups remain no-ops. Unowned, missing, outdated, ambiguous, or non-shared-hook targets are rejected. Keep subsequent capture, pre-intent, replacement, and publication revalidation so later changes fail without overwriting concurrent edits. Powerspec passes both `force=True` and `receipt_only=True` for its narrowly authorized repair.

Verify successful receipt-only repair, repeat no-op, public wrapper forwarding, scope restrictions, and concurrent restoration of the old baseline before update, during capture, and just before replacement. The guard does not claim an operating-system lock against arbitrary external writers; the receipt-only path itself performs no native content replacement.

## Risks / Trade-offs

- Shared containment affects uninstall and verification too → run focused utility/lifecycle tests and the full suite.
- A source can change between preflight and mutation → preserve existing fresh inspection and fingerprint comparison.
- Empty or partial groups might be mistaken for absence → test missing whole groups separately from existing ambiguity rejections.

## Migration Plan

No receipt migration is needed. Existing owned-but-missing groups converge on the next explicit install. Powerspec will consume a verified revision containing this fix; no client-side private receipt workaround is introduced.
