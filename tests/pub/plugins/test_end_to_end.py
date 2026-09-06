import json
import pytest

from tests.specs.plugins.test_pi_revisions import PiManager
from zuat.pub import Zuat, ZuatRequest, AssetSelector, PluginRef
from zuat import pub
from zuat.specs.pi import PiResolver
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.utils.ownership import OwnershipStore


@pytest.mark.parametrize("available", [True, False])
def test_public_plugin_profile_restart_and_policy_exclude_payloads(tmp_path, available):
    home = tmp_path / "home"
    global_skill = home / ".pi/agent/skills/global/SKILL.md"
    global_skill.parent.mkdir(parents=True)
    global_body = "---\nname: global\ndescription: global\n---\nGLOBAL RECOVERABLE"
    global_skill.write_text(global_body)
    runner = PiManager(tmp_path / "package")
    runner.source, runner.version = "npm:@team/review", "1.0.0"
    (runner.root / "skills/review").mkdir(parents=True)
    (runner.root / "skills/review/SKILL.md").write_text("PLUGIN NEVER DURABLE")
    (runner.root / "prompts").mkdir()
    (runner.root / "prompts/review.md").write_text("ARTIFACT NEVER DURABLE")
    root = tmp_path / "registry"
    adapter = PiPluginAdapter(home=home, store=OwnershipStore(root / ".git/zuat/native", "pi"), runner=runner)
    resolver = PiResolver(home=home, plugins=adapter)
    ref = PluginRef("pi", "npm:@team/review")
    class Prompts(pub.ZuatExtension):
        identifier = "prompts"
        version = "1"

        def locate_artifacts(self, context):
            return (context.runtime_root / "prompts/review.md",)

    extension = Prompts()
    with Zuat(root=root, home=home, resolvers={"pi": resolver}) as service:
        assert service.install_plugin(ref).ok
        assert service.adopt_all(AssetSelector("pi", provider="global")).ok
        assert service.create_profile(ZuatRequest(agents=("pi",), profile="original")).ok
        service.register_extension(extension)
        assert service.set_artifact_policy(ref, "prompts", "disabled").ok
        updated = service.update_plugin(ref)
        assert updated.ok, updated.diagnostics
        assert runner.version == "2.0.0"
    with Zuat(root=root, home=home, resolvers={"pi": resolver}) as service:
        service.register_extension(extension)
        assert service.artifact_status(ref, "prompts").policy == "disabled"
        if not available:
            runner.available.remove("1.0.0")
        restored = service.switch_profile(ZuatRequest(agents=("pi",), profile="original", force=True))
        if not available:
            assert not restored.ok
            assert runner.version == "2.0.0"
            assert service.registry.projected_state().selected_profile == "default"
            assert service.registry.recovery_marker.exists()
            assert service.recover_plugins().completeness == "indeterminate"
            assert runner.version == "2.0.0"
            return
        assert restored.ok, restored.diagnostics
        assert runner.version == "1.0.0"
        assert service.registry.projected_state().selected_profile == "original"
        assert service.artifact_status(ref, "prompts").policy == "disabled"
        assert service.clear_artifact_policy(ref, "prompts").ok
        assert service.resolve_artifacts("pi", "prompts")[0].revision.version == "1.0.0"
        assert global_skill.read_text() == global_body
        current = service.list_assets(AssetSelector("pi"))
        selected = tuple(item.ref.id for item in current.assets if item.ref.kind == "plugin" or item.evidence.get("provider") != "plugin")
        removed = service.uninstall(ZuatRequest(agents=("pi",), asset_refs=selected))
        assert removed.ok, removed.diagnostics
        assert runner.version is None and not global_skill.exists()
        restored = service.restore_all(removed.operation_id, selector=AssetSelector("pi"), force=True)
        assert restored.ok, restored.diagnostics
        assert runner.version == "1.0.0"
        assert global_skill.read_text() == global_body
        # Inspect actual Git objects and private sinks, not just working-tree filenames.
        objects = service.registry.repo.git.cat_file("--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
        blobs = [service.registry.repo.odb.stream(bytes.fromhex(line.split()[0])).read() for line in objects.splitlines() if line.split()[1] == "blob"]
        durable = blobs + [path.read_bytes() for path in service.registry.control_root.rglob("*") if path.is_file()]
        assert any(b"GLOBAL RECOVERABLE" in value for value in durable)
        for value in durable:
            assert b"PLUGIN NEVER DURABLE" not in value
            assert b"ARTIFACT NEVER DURABLE" not in value
            assert str(runner.root).encode() not in value
        assert service.registry.event(updated.operation_id).after[0].evidence["revision"]["version"] == "2.0.0"
