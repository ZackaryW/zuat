import json

import pytest

from test_plugin_adapters import adapter
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.specs.native import PluginRecord, PluginRef, PluginOperationError
from zuat.utils.process import ProcessResult


class PiManager:
    def __init__(self, root):
        self.root = root
        root.mkdir()
        self.source = "npm:@team/review@2.0.0"
        self.version = "2.0.0"
        self.calls = []
        self.available = {"1.0.0", "2.0.0"}

    def run(self, args, **kwargs):
        self.calls.append(args)
        if args[1] == "update":
            self.version = "2.0.0"
        if args[1] == "remove":
            self.version = None
        if args[1] == "install":
            version = args[2].rsplit("@", 1)[1]
            if version not in self.available:
                return ProcessResult(args, 1, "", "sensitive native error")
            self.source, self.version = args[2], version
        (self.root / "package.json").write_text(json.dumps({"name": "@team/review", "version": self.version}))
        inventory = f"User packages:\n  {self.source}\n    {self.root}\n" if self.version else "No packages installed."
        return ProcessResult(args, 0, inventory if args[1] == "list" else "", "")


def test_pi_npm_revision_identity_is_independent_of_version_pin(tmp_path):
    runner = PiManager(tmp_path / "package")
    native = adapter(PiPluginAdapter, tmp_path, runner)
    record = native.discover()[0]
    assert record.ref.native_ref == "npm:@team/review"
    assert record.revision.version == "2.0.0"


def test_pi_exact_npm_reconcile_installs_and_verifies_requested_version(tmp_path):
    runner = PiManager(tmp_path / "package")
    native = adapter(PiPluginAdapter, tmp_path, runner)
    desired = PluginRecord(PluginRef("pi", "npm:@team/review", source="npm"), "review", True, "partial", "1.0.0")
    native.preflight(desired.ref, "install", desired=desired)
    outcome = native.reconcile(desired)
    assert outcome.verified
    assert outcome.after.revision == desired.revision
    assert runner.source == "npm:@team/review@1.0.0"
    assert runner.version == "1.0.0"


def test_pi_unavailable_exact_version_does_not_fall_back_to_latest(tmp_path):
    runner = PiManager(tmp_path / "package")
    native = adapter(PiPluginAdapter, tmp_path, runner)
    desired = PluginRecord(PluginRef("pi", "npm:@team/review", source="npm"), "review", True, "partial", "0.0.0")
    with pytest.raises(PluginOperationError):
        native.reconcile(desired)
    assert runner.version == "2.0.0"
    assert [call[2] for call in runner.calls if call[1] == "install"] == ["npm:@team/review@0.0.0"]


def test_pi_install_pin_updates_existing_identity_instead_of_adopting_wrong_version(tmp_path):
    runner = PiManager(tmp_path / "package")
    native = adapter(PiPluginAdapter, tmp_path, runner)
    outcome = native.install(PluginRef("pi", "npm:@team/review@1.0.0"))
    assert outcome.verified
    assert outcome.after.revision.version == "1.0.0"
    assert runner.source == "npm:@team/review@1.0.0"


def test_public_pi_pin_requires_force_to_replace_external_revision(tmp_path):
    from zuat.pub import Zuat
    from zuat.specs.pi import PiResolver
    runner = PiManager(tmp_path / "package")
    native = adapter(PiPluginAdapter, tmp_path, runner)
    with Zuat(root=tmp_path / "registry", home=tmp_path / "home", resolvers={"pi": PiResolver(home=tmp_path / "home", plugins=native)}) as service:
        ref = PluginRef("pi", "npm:@team/review@1.0.0")
        rejected = service.install_plugin(ref)
        assert not rejected.ok
        assert runner.version == "2.0.0"
        assert not service.registry.recovery_marker.exists()
        assert service.install_plugin(ref, force=True).ok
        assert runner.version == "1.0.0"


def test_interrupted_pin_preserves_intended_revision_for_recovery(tmp_path, monkeypatch):
    from zuat.pub import Zuat
    from zuat.specs.pi import PiResolver
    runner = PiManager(tmp_path / "package")
    native = adapter(PiPluginAdapter, tmp_path, runner)
    original = runner.run
    def interrupt(args, **kwargs):
        result = original(args, **kwargs)
        if args[1] == "install":
            raise KeyboardInterrupt
        return result
    monkeypatch.setattr(runner, "run", interrupt)
    with Zuat(root=tmp_path / "registry", home=tmp_path / "home", resolvers={"pi": PiResolver(home=tmp_path / "home", plugins=native)}) as service:
        with pytest.raises(KeyboardInterrupt):
            service.install_plugin(PluginRef("pi", "npm:@team/review@1.0.0"), force=True)
        marker = json.loads(service.registry.recovery_marker.read_text())
        assert marker["metadata"]["intended_revision"] == {"agent_kind":"pi", "plugin_id":"npm:@team/review", "version":"1.0.0"}
        recovered = service.recover_plugins()
        event = service.registry.event(recovered.operation_id)
        assert event.metadata["intended_revision"] == marker["metadata"]["intended_revision"]
        assert event.after[0].evidence["revision"] == event.metadata["intended_revision"]
