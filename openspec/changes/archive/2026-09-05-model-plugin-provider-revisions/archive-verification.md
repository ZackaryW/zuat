# Verification Report: model-plugin-provider-revisions

Reviewed on 2026-09-05 using the OpenSpec verification and archive workflows.

## Summary

| Dimension | Assessment |
| --- | --- |
| Completeness | 26/26 tasks complete; all four planning artifacts done; implementation evidence for all 19 requirements |
| Correctness | 44 scenarios reviewed against native adapters, orchestration, persistence and behavioral tests; native limitations remain explicit |
| Coherence | Package boundaries and six architectural decisions substantially followed; one public-signature design discrepancy noted below |

## Requirement-to-evidence map

Paths below are relative to the repository root. Test references supplement the executed coverage recorded in `verification.md`; a keyword match alone is not treated as behavioral proof.

| Requirement | Implementation | Behavioral evidence |
| --- | --- | --- |
| Public plugin operations | `src/zuat/pub/plugins.py:18`, `src/zuat/cli/plugins.py:10` | `tests/test_plugin_workflows.py:77`, `tests/test_plugin_cli.py:17` |
| Installed and available discovery are distinct | `src/zuat/pub/plugins.py:22`, per-agent discovery adapters | `tests/test_plugin_adapters.py:36`, `tests/test_plugin_workflows.py:195` |
| Explicit trust for direct installation sources | `src/zuat/utils/plugin_lifecycle.py:139`, native source policy | `tests/test_plugin_adapters.py:122`, `tests/test_plugin_workflows.py:206` |
| Independent project configuration trust | `src/zuat/specs/pi_plugins.py:192`, project context binding | `tests/test_plugin_adapters.py:76`, `tests/test_plugin_adapters.py:92` |
| Agent-specific operation capabilities | `src/zuat/specs/interface.py`, four agent-owned plugin adapters | `tests/test_plugin_capabilities.py:22`, `tests/test_plugin_project_context.py:11` |
| Verified targeted lifecycle operations | `src/zuat/pub/plugins.py:73`, `src/zuat/utils/plugin_lifecycle.py:156` | `tests/test_plugin_workflows.py:158`, `tests/test_plugin_project_context.py:11` |
| Optional CLI and self-contained runtime | `src/zuat/pub/__init__.py`, `src/zuat/cli/__init__.py`, `pyproject.toml` | Installed base-only/CLI-extra checks in `verification.md`; import-boundary regression suite |
| Global and plugin provider provenance | `src/zuat/specs/base.py:165`, `src/zuat/specs/native.py:162` | `tests/test_plugin_artifacts.py:11`, `tests/test_plugin_revisions.py:43`, native contribution fixtures |
| Provider-aware selection and native behavior | `src/zuat/pub/models.py:24`, `src/zuat/specs/base.py:213` | `tests/test_plugin_artifacts.py:74`, `tests/test_plugin_artifacts.py:95` |
| Generic artifact extension registration | `src/zuat/pub/artifacts.py:31`, `src/zuat/pub/artifact_models.py` | `tests/test_plugin_artifacts.py:50`, `tests/test_plugin_artifacts.py:65` |
| Safe runtime artifact resolution | `src/zuat/pub/artifacts.py:72`, `src/zuat/utils/runtime_paths.py` | `tests/test_plugin_artifacts.py:50`, `tests/test_plugin_artifacts.py:104`, `tests/test_plugin_artifacts.py:133` |
| Artifact policy and effective status | `src/zuat/pub/artifacts.py:44`, `src/zuat/pub/artifacts.py:132` | `tests/test_plugin_artifacts.py:27`, `tests/test_plugin_end_to_end.py:12` |
| Resolution policy is not native mutation | `src/zuat/pub/artifacts.py:132`, metadata-only history | `tests/test_plugin_artifacts.py:27`, `tests/test_plugin_end_to_end.py:12` |
| Exact plugin revision identity | `src/zuat/specs/native.py:142` | `tests/test_plugin_revisions.py:16`, `tests/test_plugin_project_context.py:11` |
| Reference-only durable plugin records | `src/zuat/utils/plugin_pointers.py`, `src/zuat/gitcore/plugin_safety.py`, `src/zuat/gitcore/repository.py:787` | `tests/test_plugin_persistence.py`, `tests/test_plugin_state.py`, Git-object assertions in `tests/test_plugin_end_to_end.py:12` |
| Ownership remains separate from observation | `src/zuat/pub/plugins.py:22`, `src/zuat/pub/service.py:1314` | `tests/test_plugin_workflows.py:97`, `tests/test_plugin_workflows.py:243` |
| Append-only plugin transitions | `src/zuat/gitcore/repository.py:492`, `src/zuat/pub/plugins.py:73` | `tests/test_plugin_recovery.py:11`, `tests/test_plugin_end_to_end.py:12` |
| Exact profile and restore resolution | `src/zuat/specs/base.py:213`, `src/zuat/specs/pi_plugins.py:79` | `tests/test_pi_exact_plugins.py:44`, `tests/test_pi_exact_plugins.py:56`, `tests/test_plugin_end_to_end.py:12` |
| Honest partial outcomes and recovery | `src/zuat/pub/plugins.py:283`, `src/zuat/gitcore/repository.py:649` | `tests/test_plugin_recovery.py:38`, `tests/test_plugin_recovery.py:63`, `tests/test_plugin_recovery.py:112` |

## Issues

### Critical

None found in this review. No missing normative requirement implementation or incomplete task was identified.

### Warning

Design decision 4 describes a separate optional exact-revision installation input and optional expected-revision guards for update/removal. The actual public signatures in `src/zuat/pub/service.py:116` and `src/zuat/pub/__init__.py:220` accept a native reference, trust and force, but not those separate arguments. Supported native pins supply exact installation requests; profiles restore exact revisions, and artifact status accepts a stale-revision guard. Those paths do not provide optimistic concurrency guards for ordinary update/remove calls.

Recommendation: reconcile decision 4 with the intended public API in a follow-up, or add explicitly specified expected-revision inputs with failing-first behavioral tests. This design-only mismatch does not remove a requirement from the three capability specs being promoted. It remains documented rather than silently changing the archived design or claiming the arguments exist.

### Suggestion

Expand the provider-collision fixture at `tests/test_plugin_artifacts.py:74` to include two simultaneous same-named plugin providers in addition to the global declaration. The present tests exercise global/plugin ambiguity and distinct plugin revision identity separately; a combined fixture would more directly mirror the three-provider scenario.

## Scope and limitations

- No verification dimension was skipped. Tests use isolated homes, registries and injected native managers; this is not a live native installation acceptance test.
- Native limitations and inspected format provenance remain in `native-capabilities.md`, including Pi's local Node incompatibility and unsupported exact acquisition for Claude/Codex and lifecycle mutation for Kimi.
- Only this change's three new capabilities are synced. Earlier superseded plugin artifacts are not promoted.
- User requested automatic archiving. Assessment: no critical issues; ready for archive with the noted warning and coverage suggestion retained.

## Archive-time checks

- `uv run --extra cli pytest -q --tb=short`: 263 passed in 77.74s.
- `uv run --extra cli behave --format progress`: 1 feature, 4 scenarios and 23 steps passed; no failures or skips.
- `openspec validate model-plugin-provider-revisions --strict`: valid.
- `openspec validate --specs --strict`: all 3 canonical specs passed.
- Compared all three canonical specs to their complete delta requirements and Purpose sections after converting the delta header to the canonical Requirements header: no differences remaining to apply. No prior canonical spec was overwritten.
