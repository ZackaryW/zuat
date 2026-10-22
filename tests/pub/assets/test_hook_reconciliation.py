import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.pub.assets.test_context import EmptyPlugins
from zuat.pub import AssetInput, AssetSelector, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for
from zuat.utils.documents import write_toml


def fragment(agent, *commands):
    if agent == "kimi":
        return [{"event": "Start", "command": command} for command in commands]
    return {"SessionStart": [
        {"hooks": [{"type": "command", "command": command}]} for command in commands
    ]}


def encode(agent, hooks):
    document = {"hooks": hooks, "model": "unrelated"}
    return write_toml(document) if agent == "kimi" else json.dumps(document).encode()


def setup(tmp_path, agent="claude"):
    home, root = tmp_path / "home", tmp_path / "registry"
    resolver = resolver_for(agent, home=home, project_root=tmp_path / "project",
                            state_root=root / ".git/zuat/native", plugins=EmptyPlugins())
    current = Zuat(root=root, home=home, project_root=tmp_path / "project",
                   bundle_root=tmp_path / "bundles", resolvers={agent: resolver})
    source = tmp_path / ("reviewer.toml" if agent == "kimi" else "reviewer.json")
    source.write_bytes(encode(agent, fragment(agent, "old-one", "old-two")))
    asset = AssetInput(agent, "hook", source=str(source))
    destination = home / {"claude": ".claude/settings.json", "codex": ".codex/hooks.json",
                          "kimi": ".kimi-code/config.toml"}[agent]
    return current, asset, source, destination


def stale(current, asset, source, destination):
    assert current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,))).ok
    baseline = current.inspect_asset(asset).baseline_fingerprint
    desired = fragment(asset.agent, "new-one", "new-two")
    source.write_bytes(encode(asset.agent, desired))
    destination.write_bytes(source.read_bytes())
    return baseline


@pytest.mark.parametrize("agent", ["claude", "codex", "kimi"])
@pytest.mark.parametrize("missing", ["empty", "file", "unrelated"])
def test_reinstall_verified_absent_owned_group(tmp_path, agent, missing):
    current, asset, source, destination = setup(tmp_path, agent)
    with current:
        request = ZuatRequest(agents=(agent,), assets=(asset,))
        assert current.install(request).ok
        unrelated = ([{"event": "Stop", "command": "foreign"}] if agent == "kimi"
                     else {"Stop": [{"hooks": [{"type": "command", "command": "foreign"}]}]})
        if missing == "file":
            destination.unlink()
        else:
            destination.write_bytes(encode(agent, unrelated if missing == "unrelated"
                                           else ([] if agent == "kimi" else {})))
        observed = current.inspect_asset(asset)
        assert observed.classification == "absent" and observed.owned
        result = current.install(request)
        assert result.ok, result.diagnostics
        assert current.inspect_asset(asset).classification == "current"
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        assert current.install(request).ok
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        if missing != "file":
            assert "unrelated" in destination.read_text()
        if missing == "unrelated":
            assert "foreign" in destination.read_text()


@pytest.mark.parametrize("agent", ["claude", "codex", "kimi"])
def test_stale_receipt_keeps_identity_and_source_match_without_writes(tmp_path, agent):
    current, asset, source, destination = setup(tmp_path, agent)
    with current:
        baseline = stale(current, asset, source, destination)
        history = current.registry.history()
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        result = current.inspect_asset(asset)
        assert result.classification == "conflict"
        assert result.owned and result.source_matches
        assert result.baseline_fingerprint == baseline
        assert result.observed_fingerprint != baseline
        assert current.registry.history() == history
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before


@pytest.mark.parametrize("case", ["partial", "duplicate", "coexisting", "coexisting-duplicate", "owner"])
def test_ambiguous_groups_retain_valid_baseline_but_cannot_authorize(tmp_path, case):
    current, asset, source, destination = setup(tmp_path)
    with current:
        baseline = stale(current, asset, source, destination)
        commands = {"partial": ("new-one", "other"),
                    "duplicate": ("new-one", "new-one", "new-two"),
                    "coexisting": ("old-one", "old-two", "new-one", "new-two"),
                    "coexisting-duplicate": ("old-one", "old-two", "new-one", "new-one", "new-two"),
                    "owner": ("new-one", "new-two")}[case]
        destination.write_bytes(encode(asset.agent, fragment(asset.agent, *commands)))
        if case == "owner":
            support = current._resolver(asset.agent)._support
            store = support.bind(support.state_root)
            record = store.load("hook", "reviewer")
            from zuat.utils.inspection import fragment_fingerprint
            hooks = fragment(asset.agent, "new-one")
            store.save(replace(record, name="another", fragment=hooks,
                               fingerprint=fragment_fingerprint(hooks)))
        result = current.inspect_asset(asset)
        assert result.classification == "indeterminate"
        assert result.owned and result.baseline_fingerprint == baseline
        assert result.observed_fingerprint is None and result.source_matches is None
        assert result.completeness == "partial" and result.diagnostics
        before = destination.read_bytes()
        assert not current.update_asset(asset, force=True).ok
        assert destination.read_bytes() == before


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("case", ["legacy", "duplicate", "stale", "owner"])
def test_install_never_appends_or_adopts_ambiguous_groups(tmp_path, force, case):
    current, asset, source, destination = setup(tmp_path)
    with current:
        if case in {"stale", "owner"}:
            stale(current, asset, source, destination)
            if case == "owner":
                source = source.with_name("another.json")
                source.write_bytes(destination.read_bytes())
                asset = replace(asset, source=str(source))
        else:
            destination.parent.mkdir(parents=True)
            commands = ("legacy-one", "legacy-two") if case == "legacy" else (
                "old-one", "old-one", "old-two")
            destination.write_bytes(encode(asset.agent, fragment(asset.agent, *commands)))
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        profile = current.registry.projected_state().profile("default")
        result = current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,), force=force))
        assert not result.ok, result
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        assert current.registry.projected_state().profile("default") == profile


@pytest.mark.parametrize("agent", ["claude", "codex", "kimi"])
def test_exact_group_adoption_does_not_rewrite_native(tmp_path, agent):
    current, asset, source, destination = setup(tmp_path, agent)
    with current:
        destination.parent.mkdir(parents=True)
        destination.write_bytes(source.read_bytes())
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        assert current.inspect_asset(asset).classification == "unowned"
        result = current.install(ZuatRequest(agents=(agent,), assets=(asset,)))
        assert result.ok, result.diagnostics
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        assert current.inspect_asset(asset).classification == "current"


@pytest.mark.parametrize("agent", ["claude", "codex", "kimi"])
def test_receipt_only_update_is_explicit_and_preserves_native_bytes(tmp_path, agent):
    current, asset, source, destination = setup(tmp_path, agent)
    with current:
        stale(current, asset, source, destination)
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        assert not current.update_asset(asset).ok
        repaired = current.update_asset(asset, force=True)
        assert repaired.ok, repaired.diagnostics
        assert repaired.operation_id
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        assert repaired.data == {"changed": True, "native_changed": False, "ownership_changed": True}
        assert current.inspect_asset(asset).classification == "current"
        history = current.registry.history()
        repeated = current.update_asset(asset, force=True)
        assert repeated.ok and repeated.data == {
            "changed": False, "native_changed": False, "ownership_changed": False}
        assert current.registry.history() == history


def test_content_update_reports_both_effects(tmp_path):
    current, asset, source, destination = setup(tmp_path)
    with current:
        assert current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,))).ok
        source.write_bytes(encode(asset.agent, fragment(asset.agent, "new-one", "new-two")))
        result = current.update_asset(asset)
        assert result.ok, result.diagnostics
        assert result.data == {"changed": True, "native_changed": True, "ownership_changed": True}


@pytest.mark.parametrize("agent", ["codex", "claude", "kimi"])
def test_guarded_receipt_repair_and_repeat(tmp_path, agent):
    current, asset, source, destination = setup(tmp_path, agent)
    with current:
        stale(current, asset, source, destination)
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        assert not current.update_asset(asset, receipt_only=True).ok
        result = current.update_asset(asset, force=True, receipt_only=True)
        assert result.ok and result.operation_id, result.diagnostics
        assert result.data["ownership_changed"] and not result.data["native_changed"]
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        history = current.registry.history()
        repeated = current.update_asset(asset, receipt_only=True)
        assert repeated.ok and not repeated.data["changed"]
        assert current.registry.history() == history


@pytest.mark.parametrize("boundary", ["before-call", "capture", "replace"])
def test_guarded_repair_preserves_concurrently_restored_baseline(tmp_path, monkeypatch, boundary):
    current, asset, source, destination = setup(tmp_path)
    with current:
        original = source.read_bytes()
        baseline = stale(current, asset, source, destination)
        assert current.inspect_asset(asset).source_matches
        if boundary == "before-call":
            destination.write_bytes(original)
        else:
            resolver = current._resolver(asset.agent)
            method = "capture_asset" if boundary == "capture" else "replace_asset"
            real = getattr(resolver, method)
            def change(*args, **kwargs):
                if boundary == "capture":
                    result = real(*args, **kwargs)
                    destination.write_bytes(original)
                    return result
                destination.write_bytes(original)
                return real(*args, **kwargs)
            monkeypatch.setattr(resolver, method, change)
        result = current.update_asset(asset, force=True, receipt_only=True)
        assert not result.ok and result.diagnostics
        assert destination.read_bytes() == original
        assert current.inspect_asset(asset).baseline_fingerprint == baseline


@pytest.mark.parametrize("state", ["absent", "unowned", "outdated", "ambiguous"])
def test_guarded_repair_rejects_noneligible_hook_state(tmp_path, state):
    current, asset, source, destination = setup(tmp_path)
    with current:
        if state == "unowned":
            destination.parent.mkdir(parents=True)
            destination.write_bytes(source.read_bytes())
        elif state != "absent":
            assert current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,))).ok
            if state == "outdated":
                source.write_bytes(encode(asset.agent, fragment(asset.agent, "new-one", "new-two")))
            else:
                destination.write_bytes(encode(asset.agent, fragment(asset.agent, "old-one", "old-one", "old-two")))
        before = destination.read_bytes() if destination.exists() else None
        result = current.update_asset(asset, force=True, receipt_only=True)
        assert not result.ok and result.diagnostics
        assert (destination.read_bytes() if destination.exists() else None) == before


def test_guarded_repair_public_function_forwards_option(tmp_path):
    from zuat.pub import update_asset
    current, asset, source, destination = setup(tmp_path)
    with current:
        stale(current, asset, source, destination)
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    result = update_asset(asset, force=True, receipt_only=True,
                          root=tmp_path / "registry", home=tmp_path / "home",
                          project_root=tmp_path / "project")
    assert result.ok and not result.data["native_changed"], result.diagnostics
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before


def test_receipt_only_guard_rejects_current_skill_without_effects(tmp_path):
    from tests.pub.assets.test_context import service
    from tests.pub.assets.test_inspection import source_asset
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "project") as current:
        assert current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,))).ok
        observed = current.inspect_asset(asset)
        history = current.registry.history()
        result = current.update_asset(asset, force=True, receipt_only=True)
        assert not result.ok and "receipt-only" in " ".join(result.diagnostics)
        assert current.inspect_asset(asset) == observed
        assert current.registry.history() == history


@pytest.mark.parametrize("agent", ["claude", "codex", "kimi"])
def test_restore_receipt_only_update_recovers_stale_authority_without_rewrite(tmp_path, agent):
    current, asset, source, destination = setup(tmp_path, agent)
    with current:
        baseline = stale(current, asset, source, destination)
        previous_profile = current.registry.projected_state().profile("default")
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        repaired = current.update_asset(asset, force=True)
        assert repaired.ok, repaired.diagnostics
        restored = current.restore_all(repaired.operation_id, AssetSelector(agent, kind="hook"), force=True)
        assert restored.ok, restored.diagnostics
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        inspected = current.inspect_asset(asset)
        assert inspected.classification == "conflict" and inspected.source_matches
        assert inspected.baseline_fingerprint == baseline
        assert current.registry.projected_state().profile("default") == previous_profile


def test_reordering_keeps_group_identity_and_neighbors_do_not_join_group(tmp_path):
    current, asset, source, destination = setup(tmp_path)
    with current:
        assert current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,))).ok
        original = current.inspect_asset(asset)
        destination.write_bytes(encode(asset.agent, fragment(asset.agent, "neighbor", "old-one", "old-two")))
        assert current.inspect_asset(asset) == original
        destination.write_bytes(encode(asset.agent, fragment(asset.agent, "neighbor", "old-two", "old-one")))
        reordered = current.inspect_asset(asset)
        assert reordered.owned and reordered.classification == "conflict"
        assert reordered.baseline_fingerprint == original.baseline_fingerprint


@pytest.mark.parametrize("boundary", ["receipt-before", "receipt-after", "profile-before", "profile-after", "event", "finish"])
def test_failed_receipt_repair_compensates_distinct_prior_states(tmp_path, monkeypatch, boundary):
    current, asset, source, destination = setup(tmp_path)
    with current:
        baseline = stale(current, asset, source, destination)
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        profile = current.registry.projected_state().profile("default")
        if boundary.startswith("receipt"):
            from zuat.utils.ownership import OwnershipStore
            host, attribute = OwnershipStore, "save"
        else:
            host = current.registry
            attribute = {"event": "record_asset_operation", "finish": "finish_operation"}.get(boundary, "store_profile_asset")
        original = getattr(host, attribute)
        called = False
        def interrupt(*args, **kwargs):
            nonlocal called
            if called:
                return original(*args, **kwargs)
            called = True
            if boundary.endswith("after"):
                original(*args, **kwargs)
            raise OSError("injected publication failure")
        monkeypatch.setattr(host, attribute, interrupt)
        result = current.update_asset(asset, force=True)
        assert not result.ok and result.operation_id
        assert result.completeness == "complete", result.diagnostics
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        inspected = current.inspect_asset(asset)
        assert inspected.classification == "conflict" and inspected.baseline_fingerprint == baseline
        assert current.registry.projected_state().profile("default") == profile
        assert not current.registry.recovery_marker.exists()


@pytest.mark.parametrize("change", ["native", "receipt", "source", "neighbor"])
def test_concurrent_change_at_receipt_publication_is_not_overwritten(tmp_path, monkeypatch, change):
    from zuat.utils.ownership import OwnershipStore
    from zuat.utils.inspection import fragment_fingerprint
    current, asset, source, destination = setup(tmp_path)
    with current:
        baseline = stale(current, asset, source, destination)
        original = OwnershipStore.save
        called = False
        concurrent = None
        def publish(store, record):
            nonlocal called, concurrent
            original(store, record)
            if called:
                return
            called = True
            if change == "receipt":
                hooks = fragment(asset.agent, "external-one", "external-two")
                concurrent = replace(record, fragment=hooks, fingerprint=fragment_fingerprint(hooks))
                original(store, concurrent)
            else:
                hooks = fragment(asset.agent, *(('new-one', 'new-two', 'neighbor') if change == "neighbor"
                                               else ('external-one', 'external-two')))
                path = source if change == "source" else destination
                concurrent = encode(asset.agent, hooks)
                path.write_bytes(concurrent)
        monkeypatch.setattr(OwnershipStore, "save", publish)
        result = current.update_asset(asset, force=True)
        if change == "neighbor":
            assert result.ok, result.diagnostics
            assert destination.read_bytes() == concurrent
        else:
            assert not result.ok
            if change == "receipt":
                support = current._resolver(asset.agent)._support
                assert support.bind(support.state_root).load("hook", "reviewer") == concurrent
                assert result.completeness == "partial"
                assert current.registry.recovery_marker.exists()
            elif change == "native":
                assert destination.read_bytes() == concurrent
                assert result.completeness == "partial"
            else:
                assert source.read_bytes() == concurrent
                assert current.inspect_asset(asset).baseline_fingerprint == baseline


def test_positional_hint_does_not_authorize_duplicate_adoption(tmp_path):
    from tests.pub.assets.test_shared_hooks import claude_service, hook_at
    current, registry, destination = claude_service(tmp_path, ("one", "one"))
    with current:
        observed = hook_at(current, 0)
        before = destination.read_bytes()
        result = current.install(ZuatRequest(agents=("claude",), asset_refs=(observed.ref.id,), force=True))
        assert not result.ok
        assert destination.read_bytes() == before


@pytest.mark.parametrize("boundary", ["profile", "event"])
def test_change_during_final_publication_never_reports_success(tmp_path, monkeypatch, boundary):
    current, asset, source, destination = setup(tmp_path)
    with current:
        stale(current, asset, source, destination)
        attribute = "store_profile_asset" if boundary == "profile" else "record_asset_operation"
        original = getattr(current.registry, attribute)
        edited = encode(asset.agent, fragment(asset.agent, "external-one", "external-two"))
        def publish(*args, **kwargs):
            result = original(*args, **kwargs)
            destination.write_bytes(edited)
            return result
        monkeypatch.setattr(current.registry, attribute, publish)
        result = current.update_asset(asset, force=True)
        assert not result.ok and result.completeness == "partial"
        assert destination.read_bytes() == edited
        assert current.registry.recovery_marker.exists()


def test_receipt_repair_process_exit_is_visible_and_restorable_after_reopen(tmp_path):
    import os
    import subprocess
    import sys

    script = '''
import os, sys
from pathlib import Path
from tests.pub.assets.test_hook_reconciliation import setup, stale
from zuat.utils.ownership import OwnershipStore
base = Path(sys.argv[1])
current, asset, source, destination = setup(base)
with current:
    stale(current, asset, source, destination)
    (base / "native-before").write_bytes(destination.read_bytes())
    (base / "mtime-before").write_text(str(destination.stat().st_mtime_ns))
    original = OwnershipStore.save
    def stop(store, record):
        original(store, record)
        os._exit(73)
    OwnershipStore.save = stop
    current.update_asset(asset, force=True)
'''
    env = dict(os.environ)
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "CODEX_HOME"):
        path = tmp_path / "environment" / key
        path.mkdir(parents=True)
        env[key] = str(path)
    child = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                           env=env, capture_output=True, text=True, timeout=60)
    assert child.returncode == 73, child.stderr
    root, home = tmp_path / "registry", tmp_path / "home"
    resolver = resolver_for("claude", home=home, project_root=tmp_path / "project",
                            state_root=root / ".git/zuat/native", plugins=EmptyPlugins())
    with Zuat(root=root, home=home, project_root=tmp_path / "project",
              bundle_root=tmp_path / "bundles", resolvers={"claude": resolver}) as current:
        status = current.status(ZuatRequest(agents=("claude",)))
        assert not status.ok and status.completeness == "partial"
        operation_id = status.data["pending_operation_id"]
        result = current.restore_all(operation_id, AssetSelector("claude", kind="hook"), force=True)
        assert result.ok, result.diagnostics
        destination = home / ".claude/settings.json"
        assert destination.read_bytes() == (tmp_path / "native-before").read_bytes()
        assert destination.stat().st_mtime_ns == int((tmp_path / "mtime-before").read_text())
        asset = AssetInput("claude", "hook", source=str(tmp_path / "reviewer.json"))
        inspected = current.inspect_asset(asset)
        assert inspected.classification == "conflict" and inspected.source_matches
        assert not current.registry.recovery_marker.exists()


def test_compensation_must_verify_receipt_not_only_native_content(tmp_path, monkeypatch):
    current, asset, source, destination = setup(tmp_path)
    with current:
        stale(current, asset, source, destination)
        original = current.registry.store_profile_asset
        called = False
        def fail_once(*args, **kwargs):
            nonlocal called
            if not called:
                called = True
                raise OSError("injected profile failure")
            return original(*args, **kwargs)
        monkeypatch.setattr(current.registry, "store_profile_asset", fail_once)
        monkeypatch.setattr(current._resolver(asset.agent), "restore_asset_ownership", lambda *args: None)
        result = current.update_asset(asset, force=True)
        assert not result.ok and result.completeness == "partial"
        assert current.registry.recovery_marker.exists()


@pytest.mark.parametrize("change", ["source", "order", "owner"])
def test_changed_capture_evidence_rejects_before_mutation(tmp_path, monkeypatch, change):
    from zuat.utils.inspection import fragment_fingerprint
    current, asset, source, destination = setup(tmp_path)
    with current:
        baseline = stale(current, asset, source, destination)
        resolver = current._resolver(asset.agent)
        original = resolver.capture_asset
        def capture(target, output):
            original(target, output)
            if change == "owner":
                support = resolver._support
                store = support.bind(support.state_root)
                record = store.load("hook", "reviewer")
                hooks = fragment(asset.agent, "new-one")
                store.save(replace(record, name="competing-provider", fragment=hooks,
                                   fingerprint=fragment_fingerprint(hooks)))
            else:
                path = source if change == "source" else destination
                path.write_bytes(encode(asset.agent, fragment(asset.agent, "new-two", "new-one")))
        monkeypatch.setattr(resolver, "capture_asset", capture)
        result = current.update_asset(asset, force=True)
        assert not result.ok and result.operation_id is None
        assert not current.registry.recovery_marker.exists()
        assert current.inspect_asset(asset).baseline_fingerprint == baseline


def test_duplicate_source_members_cannot_replace_a_valid_owned_group(tmp_path):
    current, asset, source, destination = setup(tmp_path)
    with current:
        assert current.install(ZuatRequest(agents=(asset.agent,), assets=(asset,))).ok
        before = destination.read_bytes()
        source.write_bytes(encode(asset.agent, fragment(asset.agent, "old-one", "old-one")))
        result = current.update_asset(asset, force=True)
        assert not result.ok
        assert destination.read_bytes() == before
