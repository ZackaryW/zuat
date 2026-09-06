import json
from dataclasses import replace

import pytest

from zuat.pub import AssetSelector, Zuat, ZuatRequest
from zuat.specs.claude import ClaudeResolver
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.native import PluginRef
from zuat.utils.ownership import OwnershipStore
from zuat.utils.process import ProcessResult


class NativeManager:
    """Stateful native boundary: public operations must change and rediscover state."""
    def __init__(self, root):
        self.root = root
        self.version = None
        self.enabled = True
        self.calls = []
        self.fail_discovery = False
        root.mkdir()
        (root / "skills/review").mkdir(parents=True)
        (root / "skills/review/SKILL.md").write_text("PLUGIN SKILL BODY")
        (root / "hooks").mkdir()
        (root / "hooks/hooks.json").write_text('{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"PLUGIN HOOK BODY"}]}]}}')

    def run(self, args, *, cwd=None, environment=None):
        self.calls.append(args)
        command = args[2]
        if command == "list":
            if self.fail_discovery:
                return ProcessResult(args, 1, "", "PLUGIN HOOK BODY credential")
            entries = [] if self.version is None else [{"id": "review@team", "scope": "user", "enabled": self.enabled, "version": self.version, "installPath": str(self.root), "rawSecret": "credential"}]
            return ProcessResult(args, 0, json.dumps(entries), "")
        if command == "install":
            self.version = "1"
        elif command == "update":
            self.version = "2"
        elif command == "uninstall":
            self.version = None
        return ProcessResult(args, 0, "", "")


@pytest.fixture
def setup(tmp_path):
    manager = NativeManager(tmp_path / "native-plugin")
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "registry"
    store = OwnershipStore(root / ".git/zuat/native", "claude")
    adapter = ClaudePluginAdapter(home=home, store=store, runner=manager)
    resolver = ClaudeResolver(home=home, state_root=root / ".git/zuat/native", plugins=adapter)
    with Zuat(root=root, home=home, resolvers={"claude": resolver}) as service:
        yield service, manager, adapter


def test_observe_adopt_and_remove_plugin_without_payload_archive(setup):
    service, native, adapter = setup
    native.version = "1"
    observed = service.list_assets(AssetSelector("claude", kind="plugin"))
    assert observed.ok
    adopted = service.adopt_all(AssetSelector("claude", kind="plugin"))
    assert adopted.ok, adopted.diagnostics
    item = adopted.assets[0]
    assert service.registry.projected_state().profile("default").assets == (item.ref.id,)
    assert not (service.registry.control_root / "payloads" / item.ref.id).exists()
    receipt = adapter.store.load("plugin", "review@team")
    assert receipt.fragment == adapter.discover()[0].to_dict()
    assert native.version == "1"
    removed = service.uninstall_all(AssetSelector("claude", kind="plugin"))
    assert removed.ok, removed.diagnostics
    assert native.version is None
    assert not (service.registry.control_root / "payloads" / item.ref.id).exists()


def test_public_plugin_lifecycle_and_separate_activation(setup):
    service, native, _ = setup
    ref = PluginRef("claude", "review@team")
    native.enabled = False
    installed = service.install_plugin(ref)
    assert installed.ok, installed.diagnostics
    assert installed.plugins[0].revision.version == "1"
    assert installed.plugins[0].activation == "inactive"
    updated = service.update_plugin(ref)
    assert updated.ok, updated.diagnostics
    assert updated.plugins[0].revision.version == "2"
    removed = service.remove_plugin(ref)
    assert removed.ok, removed.diagnostics
    assert native.version is None
    history = service.history().history
    event = next(item for item in history if item.operation_id == updated.operation_id)
    assert event.before[0].evidence["revision"]["version"] == "1"
    assert event.after[0].evidence["revision"]["version"] == "2"


def test_external_plugin_requires_force_for_public_remove(setup):
    service, native, _ = setup
    native.version = "1"
    ref = PluginRef("claude", "review@team")
    rejected = service.remove_plugin(ref)
    assert not rejected.ok
    assert native.version == "1"
    assert service.remove_plugin(ref, force=True).ok
    assert native.version is None


def test_restore_unavailable_exact_revision_does_not_install_latest(setup):
    service, native, _ = setup
    native.version = "1"
    removed = service.remove_plugin(PluginRef("claude", "review@team"), force=True)
    assert removed.ok
    restored = service.restore_all(removed.operation_id, selector=AssetSelector("claude", kind="plugin"), force=True)
    assert not restored.ok
    assert native.version is None
    assert not any(call[2] == "install" for call in native.calls)


def test_untrusted_project_observation_preserves_previous_evidence(tmp_path):
    from zuat.specs.pi import PiResolver
    from zuat.specs.pi_plugins import PiPluginAdapter
    from zuat.specs.native import PluginRecord, PluginActivation
    from zuat.gitcore import AssetEvidence, Authority

    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    class EmptyRunner:
        def run(self, args, **kwargs):
            return ProcessResult(args, 0, "No packages installed.\n", "")

    with Zuat(root=tmp_path / "registry", home=home, project_root=project, trust_project=False) as service:
        plugin = PiPluginAdapter(home=home, store=OwnershipStore(tmp_path / "control", "pi"), project_root=project, runner=EmptyRunner())
        service._resolvers["pi"] = PiResolver(home=home, project_root=project, plugins=plugin)
        ref = service.registry.ensure_asset_ref(agent="pi", kind="plugin", scope="project", locator="plugins/npm:review")
        evidence = AssetEvidence(ref, "sha256:test", Authority.UNAUTHORITATIVE, evidence=PluginRecord(PluginRef("pi", "npm:review", "project"), "review", True, PluginActivation.UNKNOWN, "1").to_dict())
        service.registry.record_observation((evidence,), agents=("pi",))
        result = service.status(ZuatRequest(agents=("pi",)))
        assert result.completeness == "partial"
        assert service.registry.latest_observation()[0].present


def test_old_plugin_document_is_rejected_without_rewriting(setup, tmp_path):
    service, _, _ = setup
    root = tmp_path / "bad-profile"
    path = root / "claude/user/plugins/old.json"
    path.parent.mkdir(parents=True)
    original = '{"ref":{"agent":"claude","native_ref":"review@team"},"native_evidence":{"body":"old"}}'
    path.write_text(original)
    with pytest.raises(Exception, match="fresh registry"):
        service._resolver("claude").plan(root)
    assert path.read_text() == original


@pytest.mark.parametrize("behavior", ["unchanged", "unresolved", "false-remove", "neighbor-change"])
def test_public_lifecycle_reports_only_verified_postconditions(setup, monkeypatch, behavior):
    service, native, _ = setup
    ref = PluginRef("claude", "review@team")
    assert service.install_plugin(ref).ok
    original = native.run
    neighbor = "1"
    def run(args, **kwargs):
        nonlocal neighbor
        if args[2] == "uninstall" and behavior == "false-remove":
            return ProcessResult(args, 0, "", "")
        result = original(args, **kwargs)
        if args[2] == "update":
            if behavior == "unchanged":
                native.version = "1"
            if behavior == "unresolved":
                native.version = ""
            if behavior == "neighbor-change":
                neighbor = "2"
        if args[2] == "list":
            entries = json.loads(result.stdout)
            if behavior == "unresolved" and native.version == "":
                entries[0].pop("version", None)
            if behavior == "neighbor-change":
                entries.append({"id":"neighbor@team", "scope":"user", "version":neighbor, "enabled":True})
            result = ProcessResult(args, 0, json.dumps(entries), "")
        return result
    monkeypatch.setattr(native, "run", run)
    result = service.remove_plugin(ref) if behavior == "false-remove" else service.update_plugin(ref)
    if behavior == "unchanged":
        assert result.ok
        assert result.plugins[0].revision.version == "1"
    else:
        assert not result.ok
        assert service.registry.recovery_marker.exists()


@pytest.mark.parametrize("error,code", [(FileNotFoundError("credential"), "manager-unavailable"), (ValueError("secret"), "discovery-failed")])
def test_public_discovery_failure_is_distinct_from_empty_inventory(setup, monkeypatch, error, code):
    service, native, _ = setup
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(native, "run", fail)
    result = service.discover_plugins("claude")
    assert not result.ok
    assert result.data["reason"] == code
    assert result.plugins == ()


def test_public_force_does_not_grant_source_trust_or_leave_pending_mutation(setup):
    service, native, _ = setup
    result = service.install_plugin(PluginRef("claude", "https://example.org/plugin"), force=True)
    assert not result.ok
    assert native.calls == []
    assert not service.registry.recovery_marker.exists()


def test_trusted_pi_source_can_install_without_fabricating_durable_identity(tmp_path):
    from zuat.specs.pi import PiResolver
    from zuat.specs.pi_plugins import PiPluginAdapter
    home = tmp_path / "home"
    home.mkdir()
    plugin = tmp_path / "native"
    plugin.mkdir()
    (plugin / "package.json").write_text('{"name":"review","version":"1"}')
    installed = False
    source = "https://example.org/team/review"
    class Manager:
        def run(self, args, **kwargs):
            nonlocal installed
            if args[1] == "install":
                assert args[2] == source
                installed = True
            return ProcessResult(args, 0, f"User packages:\n  {source}\n    {plugin}\n" if installed else "No packages installed.", "")
    root = tmp_path / "registry"
    adapter = PiPluginAdapter(home=home, store=OwnershipStore(root / ".git/zuat/native", "pi"), runner=Manager())
    with Zuat(root=root, home=home, resolvers={"pi": PiResolver(home=home, plugins=adapter)}) as service:
        result = service.install_plugin(PluginRef("pi", source), trust=True)
        assert installed
        assert not result.ok
        assert result.completeness == "indeterminate"
        assert result.plugins == ()
        marker = json.loads(service.registry.recovery_marker.read_text())
        assert marker["metadata"].get("plugin_ref") is None


def test_simple_discovery_records_external_ownership_without_adoption(setup):
    service, native, _ = setup
    native.version = "1"
    result = service.discover_plugins("claude")
    assert result.ok
    installation = next(item for item in result.assets if item.ref.kind == "plugin")
    assert installation.authority == "unauthoritative"
    assert installation.evidence["revision"] == result.plugins[0].revision.to_dict()
    assert installation in service.registry.latest_observation()
    assert service.registry.projected_state().profile("default").assets == ()
