# Tasks

## 1. Containment contract

- [x] 1.1 Correct mapping containment; observe failing then passing domain-neutral tests for missing keys, malformed values, partial mappings, and complete matches.

## 2. Native installation

- [x] 2.1 Reconcile verified absent owned hooks through semantic target checks; verify public install/inspect/repeat behavior for Codex, Claude, and Kimi with unrelated settings and declarations preserved.
- [x] 2.2 Document reinstall behavior and identity limits; verify example and existing rejection/recovery tests.

## 3. Integration

- [x] 3.1 Run full ZuAT tests with CLI extra, strict OpenSpec validation, and Powerspec hook integration against the corrected package; record evidence and dependency publication status.

## 4. Guarded receipt repair

- [x] 4.1 Add default-false receipt_only to public update APIs and enforce valid owned shared-hook source equality inside the update operation; verify success, repeat no-op, rejection, and concurrent edit preservation with red/green public API tests.
- [x] 4.2 Document the guard and update the public example; verify the example and Powerspec's guarded repair integration.

## Evidence

- Final guarded implementation: `uv run --extra cli pytest -q --tb=short --basetemp C:/Users/ZackaryW/.tmp/zuat-guard-1022-final` passed 623 tests, with 18 skipped. Behave passed 4 scenarios / 24 steps, and the updated public example passed. Strict change validation and diff whitespace checks passed. These checks ran before source publication; Git publication is separate from a tagged package release.

- Guard implementation: after API forwarding was added, 3 behavioral tests reproduced unauthorized content replacement/adoption; all 11 initial guard cases passed after enforcement. The broader hook suites passed 73 tests and the updated public example passed. Powerspec hook/CLI tests passed 35 cases against an explicit fresh wheel whose 75 Python files match current source.

- Containment regression: 7 failing tests before the correction, then 7 passing.
- Missing-owned-hook regression: 9 failing cases before integration, then passing for Codex, Claude, and Kimi across missing files, empty groups, and unrelated events.
- Focused helper/ownership/lifecycle tests: 82 passed.
- Full suite with CLI extra and short Windows temp root: 611 passed, 18 skipped.
- Behave: 4 scenarios and 24 steps passed. Shared-hook public example passed.
- Strict OpenSpec validation passed.
- Powerspec's 82 focused hook/upgrade tests passed using `uv run --with ../zuat` against a built local package. At this earlier checkpoint, Powerspec pinned published 0.1.2 commit 170f18b8 pending publication of the correction.
