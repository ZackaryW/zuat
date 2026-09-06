from dataclasses import replace

import pytest

from test_plugin_workflows import setup
from zuat.pub import AssetSelector, Zuat, ZuatRequest
from zuat.specs.native import PluginRef, PluginLifecycleResult


@pytest.mark.parametrize("operation", ["restore", "revert"])
def test_restore_exact_pointer_appends_history_without_plugin_payload(setup, monkeypatch, operation):
    service, native, adapter = setup
    ref = PluginRef("claude", "review@team")
    assert service.install_plugin(ref).ok
    updated = service.update_plugin(ref)
    assert updated.ok
    # This isolated native boundary supports exact acquisition; production
    # Claude remains unsupported and is covered by the rejection workflow.
    def preflight(ref, operation, *, desired=None):
        if desired:
            assert desired.revision.version in {"1", "2"}
    def reconcile(desired):
        before = adapter.discover()[0]
        native.version = desired.revision.version
        after = adapter.discover()[0]
        return PluginLifecycleResult("install", desired.ref, "installed", before, after)
    monkeypatch.setattr(adapter, "preflight", preflight)
    monkeypatch.setattr(adapter, "reconcile", reconcile)
    restored = (service.restore_all(updated.operation_id, selector=AssetSelector("claude", kind="plugin"), force=True)
                if operation == "restore" else service.revert(ZuatRequest(agents=("claude",), operation_id=updated.operation_id, force=True)))
    assert restored.ok, restored.diagnostics
    assert native.version == "1"
    assert service.history().history[-1].operation_id == restored.operation_id
    assert service.registry.event(updated.operation_id).after[0].evidence["revision"]["version"] == "2"
    assert not (service.registry.control_root / "payloads" / restored.assets[0].ref.id).exists()


def test_interrupted_update_is_observed_on_restart_not_replayed(setup, monkeypatch):
    service, native, adapter = setup
    assert service.install_plugin(PluginRef("claude", "review@team")).ok
    def interrupted(ref):
        native.version = "2"
        raise KeyboardInterrupt
    monkeypatch.setattr(adapter, "update", interrupted)
    with pytest.raises(KeyboardInterrupt):
        service.update_plugin(PluginRef("claude", "review@team"))
    assert service.registry.recovery_marker.exists()
    root = service.registry.root
    resolver = service._resolver("claude")
    service.close()
    previous_mutations = [call for call in native.calls if call[2] != "list"]
    with Zuat(root=root, home=service.home, resolvers={"claude": resolver}) as restarted:
        recovered = restarted.recover_plugins()
        assert recovered.completeness == "indeterminate"
        event = restarted.registry.event(recovered.operation_id)
        assert event.kind == "recovery"
        assert event.before[0].evidence["revision"]["version"] == "1"
        assert event.after[0].evidence["revision"]["version"] == "2"
        assert not restarted.registry.recovery_marker.exists()
    assert [call for call in native.calls if call[2] != "list"] == previous_mutations


def test_failed_rediscovery_keeps_pending_evidence_until_fresh_recovery(setup, monkeypatch):
    service, native, adapter = setup
    ref = PluginRef("claude", "review@team")
    assert service.install_plugin(ref).ok
    original = native.run
    def failing(args, **kwargs):
        result = original(args, **kwargs)
        if args[2] == "update":
            native.fail_discovery = True
        return result
    monkeypatch.setattr(native, "run", failing)
    result = service.update_plugin(ref)
    assert not result.ok
    assert service.registry.recovery_marker.exists()
    pending_id = __import__("json").loads(service.registry.recovery_marker.read_text())["operation_id"]
    assert service.registry.event(pending_id).outcome == "indeterminate"
    incomplete = service.recover_plugins()
    assert not incomplete.ok
    assert service.registry.recovery_marker.exists()
    native.fail_discovery = False
    recovered = service.recover_plugins()
    assert not service.registry.recovery_marker.exists()
    assert recovered.assets[0].evidence["revision"]["version"] == "2"
    assert service.registry.event(pending_id).outcome == "indeterminate"


def test_project_recovery_requires_original_context_before_rediscovery(setup, monkeypatch, tmp_path):
    import json
    service, native, adapter = setup
    project = tmp_path / "project"
    project.mkdir()
    service.project_root = project
    adapter.project_root = project
    def interrupted(ref, *, trust=False):
        native.version = "1"
        raise KeyboardInterrupt
    monkeypatch.setattr(adapter, "install", interrupted)
    with pytest.raises(KeyboardInterrupt):
        service.install_plugin(PluginRef("claude", "review@team", "project"))
    pending = json.loads(service.registry.recovery_marker.read_text())
    assert pending["metadata"]["plugin_ref"]["context"]
    service.project_root = None
    calls = list(native.calls)
    result = service.recover_plugins()
    assert not result.ok
    assert service.registry.recovery_marker.exists()
    assert native.calls == calls


def test_native_command_failure_reports_uncertain_operation_reference(setup, monkeypatch):
    from zuat.utils.process import ProcessResult
    service, native, _ = setup
    ref = PluginRef("claude", "review@team")
    assert service.install_plugin(ref).ok
    original = native.run
    def failed(args, **kwargs):
        result = original(args, **kwargs)
        return ProcessResult(args, 1, "", "credential") if args[2] == "update" else result
    monkeypatch.setattr(native, "run", failed)
    result = service.update_plugin(ref)
    assert not result.ok
    assert result.completeness == "indeterminate"
    assert result.operation_id
    assert service.registry.event(result.operation_id).outcome == "indeterminate"
    assert service.registry.recovery_marker.exists()
