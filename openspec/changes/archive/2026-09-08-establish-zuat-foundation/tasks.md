## 1. Retained Package Foundation

- [x] 1.1 Keep GitPython and PyYAML as base dependencies and Click only in the `cli` optional extra, and verify base and `zuat[cli]` installations resolve on Python 3.12.
- [x] 1.2 Keep `cli`, `pub`, `utils`, `specs`, and `gitcore` as one-way package boundaries, and verify architecture tests require CLI handlers to call only `zuat.pub` while `zuat.utils` remains internal.
- [x] 1.3 Keep the lazy console shim for missing Click, and verify importing the base package and invoking the command without the extra produce no Click traceback.

## 2. Domain Journal and State Projection

- [x] 2.1 Add focused failing tests for stable domain operation IDs, immutable journal events, projected profile state, authority evidence, and results without Git identifiers; run them and confirm they fail for the missing domain models before implementation.
- [x] 2.2 Implement the Zuat-owned event, operation, projected-state, authority, and verification models without compatibility aliases, and verify the tests from 2.1 pass.
- [x] 2.3 Add focused failing tests for isolated private-registry initialization and one linear append-only event stream whose internal Git hashes and refs never enter domain values; confirm the tests are red before changing `gitcore`.
- [x] 2.4 Replace the existing working-tree/index facade with internal event serialization, projected-state persistence, atomic journal advancement, and explicit Zuat authorship, and verify the tests from 2.3 pass without global Git identity configuration.
- [x] 2.5 Add failing tests for changed-observation events, identical-observation deduplication, partial-observation preservation, and unauthoritative observations that do not change profile membership; confirm each missing behavior is red.
- [x] 2.6 Implement automatic observation journaling and latest-observation identity comparison, and verify the tests from 2.5 pass while every changed observation appends and unchanged observations do not.
- [x] 2.7 Add a failing interruption test, then implement operation recovery markers and startup classification or pending-evidence preservation for operation-specific recovery so native changes cannot appear as successfully accepted profile state without a journal outcome; verify the recovery test passes.
- [x] 2.8 Adapt the registry-wide lock and hostile-path validation to cover observation, planning, native mutation, verification, and journal advancement, and verify concurrent and path-escape tests fail before interleaved or out-of-root mutation.

## 3. Named Profiles, History, and Revert

- [x] 3.1 Add failing tests for named desired-state profiles represented as journal projections rather than public branches, then implement profile creation and listing and verify only names and selected-profile state are returned.
- [x] 3.2 Add failing tests for profile-switch preflight against authoritative and unauthoritative observations, then implement verified switching with an explicit force policy and verify a blocked or partial switch never selects the target profile.
- [x] 3.3 Add failing history tests for ordered domain events, rejected attempts, force evidence, before-and-after asset evidence, and stable operation lookup, then implement public-safe history queries and verify no Git values are returned.
- [x] 3.4 Add failing tests for reverting install, uninstall, profile switch, and a prior revert as new inverse operations, then implement forward-only revert and verify prior journal events and internal history remain unchanged.
- [x] 3.5 Add a failing intervening-drift test, then require a fresh explicit force decision when revert would displace conflicting unauthoritative state and verify an unforced revert leaves profile and native state unchanged.

## 4. Complete Agent Asset Resolution

- [x] 4.1 Add failing tests for stable asset references keyed by agent, kind, scope, and native locator with separate mutable fingerprint evidence, then implement the durable asset catalog and verify content changes preserve identity at the same locator.
- [x] 4.2 Add failing Codex observation tests for every manageable skill, shared hook fragment, extension, and plugin declaration regardless of ownership, then implement complete bounded Codex enumeration and verify unknown assets receive stable references.
- [x] 4.3 Add failing Claude observation tests using real-format skill and settings fixtures with multiple pre-existing hooks, then implement complete bounded Claude enumeration and verify every hook fragment is captured independently without reading unrelated settings.
- [x] 4.4 Add failing Kimi observation tests for skills, TOML hook fragments, and plugin declarations regardless of ownership, then implement complete bounded Kimi enumeration and verify unsupported plugin mutation capabilities remain explicit.
- [x] 4.5 Add failing Pi observation tests for skills, file or directory extensions, and plugin declarations regardless of ownership, then implement complete bounded Pi enumeration and verify entry-point and symlink constraints remain enforced.
- [x] 4.6 Add failing mixed-state tests, then derive authoritative, unauthoritative, conflicting, partial, and indeterminate classifications from selected-profile intent and observation evidence and verify missing ownership records no longer hide manageable content.
- [x] 4.7 Add failing install tests for new content and equivalent unauthoritative content, then implement profile adoption plus verified native installation and verify equivalent content becomes authoritative without unnecessary replacement or force.
- [x] 4.8 Add failing uninstall tests for authoritative and unauthoritative assets, then implement reference-scoped native and profile removal and verify conflicting unauthoritative removal is rejected without force and succeeds with force.
- [x] 4.9 Add failing forced-install and forced-switch tests, then implement reference-scoped overwrite behavior and verify displaced evidence plus the force decision are journaled while unrelated native content survives.
- [x] 4.10 Add failing shared-document tests for multiple known and unknown hooks, then implement fragment-level JSON and TOML reconciliation and verify install, uninstall, force, and revert preserve unrelated fragments and settings.
- [x] 4.11 Add failing plugin lifecycle tests per agent, then implement or retain only supported noninteractive operations with rediscovery verification and verify uncertain external outcomes are recorded as partial or indeterminate rather than converged.
- [x] 4.12 Verify the four concrete resolver modules own their native locations, formats, scopes, planning, mutation, and verification while internal helpers remain agent-neutral; run architecture and resolver-contract tests proving no shared utility switches behavior on agent identity.

## 5. Public Python and Optional Click Surfaces

- [x] 5.1 Add failing public-contract tests for observation or status, install, uninstall, profile list and create, profile switch, history, and revert requests and results, then implement the domain types in `zuat.pub` and verify they import without Click or GitPython values.
- [x] 5.2 Add failing orchestration tests for the applicable asset/profile observed-transaction stages, then implement those public lifecycle operations through resolvers and `gitcore` and verify rejected, forced, partial, and successful outcomes have deterministic domain semantics without imposing mutation stages on read-only queries.
- [x] 5.3 Add failing API and command-discovery tests showing private-journal stage, commit, branch checkout, raw Git revision, Git status, snapshot history, and snapshot recovery are absent; remove those surfaces and verify no backward-compatibility aliases remain.
- [x] 5.4 Add failing Click runner tests for each domain command and explicit asset, agent, profile, operation-ID, force, and JSON options, then implement thin handlers that call only mocked `zuat.pub` operations and verify incomplete mutation input fails before orchestration.
- [x] 5.5 Add failing presentation tests, then implement concise human output and exactly one JSON result envelope on standard output with diagnostics on standard error, and verify private journal Git hashes, refs, branches, indexes, and working-tree terms never appear as result fields; source-provenance fields belong to their separate capability contract.
- [x] 5.6 Re-run isolated base-install and `zuat[cli]` tests after the command replacement and verify optional Click behavior and missing-extra guidance remain correct.

## 6. Remove the Discarded Implementation Model

- [x] 6.1 Remove obsolete status, staging, commit, branch-checkout, alternate-index snapshot, snapshot-recovery, and desired-revision code after their domain replacements are green, and verify imports and tests reference only the journal and domain-operation architecture.
- [x] 6.2 Remove ownership-as-permission-gate logic while retaining provenance and verification records, and verify unauthoritative assets are manageable only through adoption or an explicitly forced conflicting mutation.
- [x] 6.3 Remove obsolete Git-shaped request, result, CLI, and test fixtures rather than deprecating them, and verify installed package exports describe only the fresh Zuat contract.

## 7. End-to-End Behavioral Verification

- [x] 7.1 Add a Behave workflow that observes pre-existing Claude skills and multiple shared hooks, adopts equivalent content, force-replaces a conflict, uninstalls by stable reference, and verifies the ordered domain history without inspecting source text or counting files.
- [x] 7.2 Add a Behave workflow that creates and switches profiles, encounters unauthoritative drift, rejects an unforced transition, succeeds with force, reverts by operation ID, and verifies revert is a new visible operation with the expected native state.
- [x] 7.3 Exercise Codex, Claude, Kimi, and Pi through isolated temporary application and native roots and verify independent asset identities, complete bounded observation, shared-setting preservation, and per-agent outcomes without touching real user paths or the retained manual Claude simulation.
- [x] 7.4 Build the package and run the full pytest suite plus only the genuinely cross-component Behave scenarios on Python 3.12, and verify all suites pass with no structural-proxy Behave assertions.
- [x] 7.5 Run strict OpenSpec validation and verify the implementation matches all three capability specs before marking the change complete.

## 8. Concrete Private Repository Projection

- [x] 8.1 Add focused failing tests that initialize a fresh registry, observe Claude assets, and require concrete top-level agent trees, `operations/`, `catalog.json`, and plain-text `selected-profile` while rejecting the discarded `observations/`, `events/`, and `state.json` shape.
- [x] 8.2 Implement concrete top-level observation materialization and ordered operation filenames, then rerun the tests from 8.1 to green without changing public domain results.
- [x] 8.3 Add focused failing tests that require profile membership to be recoverable from concrete profile assets and adjacent stable-reference metadata without a monolithic projected-state document.
- [x] 8.4 Replace `state.json` profile and observation persistence with the compact catalog, selected-profile marker, concrete profile metadata, and operation-stream recovery, then rerun the tests from 8.3 to green.
- [x] 8.5 Add focused failing tests for unchanged-observation deduplication, partial-observation preservation, history, revert lookup, and startup recovery against the concrete projection, then adapt those behaviors without private-layout compatibility code and rerun them to green.
- [x] 8.6 Exercise a fresh isolated Claude registry through observation, adoption or install, uninstall, and history; verify concrete files and forward-appending operations through behavior rather than source inspection.
- [x] 8.7 Run the complete pytest and qualifying Behave suites, build wheel and sdist, and run strict OpenSpec validation before marking the corrected foundation complete.
