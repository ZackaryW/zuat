## 1. Establish executable boundaries and revision contracts

- [x] 1.1 Record the baseline pytest and existing qualifying Behave results, and create a test coverage map from the three capability specs to public/native boundaries. Verify the map identifies isolated agent homes, project contexts, native fixtures, and every plugin persistence sink; do not treat pre-existing green tests as red evidence. Select the cross-boundary workflow from task 7.3 now, and author/run any justified Behave scenario red before implementing its related behavior; task 7.3 reruns that evidence rather than adding retroactive red claims.
- [x] 1.2 Add and run failing pytest cases for exact revision identity, namespaced IDs, opaque versions, separate installation contexts, and unresolved native evidence; implement the small revision/installation/provider contracts and rerun to green. Verify equal revisions can belong to separate installations without merging their state.
- [x] 1.3 Add failing behavioral tests for transient native context versus durable plugin records, including invalid allowed-field values and arbitrary native evidence; implement validated allowlist serialization and safe diagnostics, then verify the tests pass without persisting runtime paths, credentials, or bodies.

## 2. Implement native capability and discovery boundaries

- [x] 2.1 Establish a source-backed operation-by-scope capability matrix using current native help, supported local formats, or official documentation; deliver isolated fixtures recording their provenance. Add failing capability tests, implement the shared protocol with per-agent policy ownership, and verify unsupported requests never invoke native mutation.
- [x] 2.2 Add failing discovery tests for each supported agent covering canonical IDs, installed/available distinction, missing versions, disabled or unknown activation, malformed output, absent managers, and successful empty inventory; implement adapter decoding and explicit catalog support, then verify structured outcomes and unchanged native state.
- [x] 2.3 Add failing tests with separate temporary user homes and two project roots; correct agent configuration-root derivation and explicit subprocess working directories, add independent default-false project trust, and verify incomplete untrusted discovery does not imply absence, project A operations leave project B untouched, and non-isolatable project updates are rejected.
- [x] 2.4 Add failing tests for supported URL, Git SSH, absolute and relative local source forms, ambiguous references, and force without trust; implement agent-owned source classification using shared neutral primitives, then verify trust rejection occurs before native mutation and safe source metadata survives round trips.

## 3. Replace plugin payload persistence

- [x] 3.1 Add failing mixed-provider observation tests that snapshot real fixture global content alongside plugin source trees and bundled skills/hooks; replace full plugin JSON observation with pointer records and verify global content remains recoverable while plugin bodies and raw evidence never enter observations or provenance stores.
- [x] 3.2 Add failing profile storage, catalog, and payload-archive tests for plugin installation and contribution pointers; implement distinct pointer/payload dispatch and verify profile creation/adoption retains exact references without copying plugin-owned contents into any archive.
- [x] 3.3 Add failing event and recovery-marker tests covering success, rejection, subprocess failure, and interrupted mutation with sensitive native output; implement safe before/after and metadata persistence and verify reopened state contains only allowed plugin fields and honest outcomes.
- [x] 3.4 Add failing tests for incompatible old plugin records in an isolated registry; reject them with fresh-registry guidance and verify no compatibility reader, automatic deletion, or history rewrite is used. Keep unrelated valid global-content behavior covered by regression tests.

## 4. Add public plugin lifecycle orchestration

- [x] 4.1 Add failing public install tests for trusted sources, externally installed plugins, authority/force gates, already-present revisions, and installed-but-disabled outcomes; implement focused orchestration and public exports, then verify native rediscovery, safe journal state, and no nested-operation failure.
- [x] 4.2 Add failing public update tests for before/after revision transitions, unchanged versions, unresolved versions, failed rediscovery, and unrelated installations; implement targeted native update and verify only established postconditions are reported as successful.
- [x] 4.3 Add failing public remove tests for selected scope, already-absent state, native restrictions, and false-success command exits; implement removal and verify absence through rediscovery while preserving other installations and global declarations.

## 5. Resolve provider contributions and artifacts

- [x] 5.1 Add failing discovery tests for global and plugin skills/hooks sharing names, native namespaces, disabled providers, and unknown versions; implement per-agent contribution discovery and verify provider identity is retained without copying bundled declarations into global state.
- [x] 5.2 Add failing helper tests for provider-filtered listing, adoption, removal, and restoration, including ambiguous names and unsupported bundled targets; implement selector/dispatch changes and verify complete preflight prevents partial mutation and implicit whole-plugin removal.
- [x] 5.3 Add failing public artifact extension tests for registration, conflicting duplicates, unknown identifiers, and immutable runtime context; implement the extension registry and resolution interface, then verify the host receives provider-bound results without loading plugin-supplied Python code.
- [x] 5.4 Add failing artifact resolution tests for stale revisions, missing and moved runtime roots, catalog-only providers, traversal, and symlink escapes; implement current-root validation and safe path resolution, then verify only eligible in-root paths are returned and no artifact bodies are persisted.
- [x] 5.5 Add failing public policy/status tests for inherit/enabled/disabled, clear, native-disablement precedence, unknown activation, scope isolation, and upgrades; implement scoped policy storage and verify effective eligibility, safe append-only policy history, and unchanged native plugin contents/state.

## 6. Reconcile profiles and recover through exact pointers

- [x] 6.1 Add failing tests for mixed global/plugin profile reconciliation with available, unavailable, unsupported, and unresolved exact revisions; implement capability/trust preflight and native pointer resolution, then verify no latest-version substitution or unverified profile publication occurs.
- [x] 6.2 Add failing public revert and bulk-restore tests that move a plugin from A to B and back to A alongside global assets; implement reference-based inverse operations and verify restored native state, provider isolation, preserved policy, and forward-appended history without plugin payload restoration.
- [x] 6.3 Add failing restart tests interrupting native mutation before result persistence and failing subsequent verification or compensation; implement orchestration-level recovery and verify safe pending evidence, fresh discovery, honest partial outcomes, and no blind replay or erased prior operation.

## 7. Complete CLI and cross-boundary verification

- [x] 7.1 Add failing Click runner tests for plugin discovery with available catalogs, independent source trust/project trust/force, update, remove, artifact status, and policy set/inherit; implement thin handlers and verify calls pass through the public interface and produce the same domain outcomes as Python operations.
- [x] 7.2 Build and install the package into isolated base-only and CLI-extra environments; verify public plugin operations without Click or agent-router, CLI-extra functionality, and concise missing-extra guidance. If behavior changes are needed, first record the corresponding failing packaging test and then rerun it to green.
- [x] 7.3 Exercise an isolated public lifecycle spanning discovery, update, restart, profile restoration, and artifact policy; verify native state, global/provider isolation, exact revisions, and every durable sink including private Git objects. Use pytest unless a genuinely cross-component Behave workflow adds evidence a focused test cannot establish; author and run any such scenario red before its implementation, never as a duplicate presentation test or source/string/count proxy.
- [x] 7.4 Run the affected and full pytest suites, existing qualifying Behave suite plus any justified additions, packaging checks, and `openspec validate model-plugin-provider-revisions --strict`; record commands/results and scenario coverage, leaving failures or unsupported native capabilities explicit. Verify no real agent home was modified and do not mark tasks complete without observed evidence.
