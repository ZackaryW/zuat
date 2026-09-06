from dataclasses import replace

import pytest

from tests.pub.plugins.test_lifecycle import setup
from zuat import pub
from zuat.pub import AssetSelector
from zuat.specs.native import PluginRef


def test_plugin_skills_and_hooks_keep_provider_identity(setup):
    service, manager, _ = setup
    manager.version = "1"
    found = service.list_assets(AssetSelector("claude", provider="plugin"))
    assert found.ok, found.diagnostics
    skills = [item for item in found.assets if item.ref.kind == "skill"]
    hooks = [item for item in found.assets if item.ref.kind == "hook"]
    assert skills[0].evidence["contribution_id"] == "skills/review"
    assert hooks[0].evidence["contribution_id"] == "hooks/Stop/0"
    assert skills[0].evidence["revision"]["plugin_id"] == "review@team"
    result = service.uninstall_all(AssetSelector("claude", kind="skill", provider="plugin"), force=True)
    assert not result.ok
    assert manager.version == "1"
    assert (manager.root / "skills/review/SKILL.md").read_text() == "PLUGIN SKILL BODY"


def test_artifact_resolution_policy_and_native_disablement(setup):
    service, manager, _ = setup
    manager.version = "1"
    ref = PluginRef("claude", "review@team")
    extension = pub.ArtifactExtension("review", "1", lambda context: (context.runtime_root / "skills/review/SKILL.md",))
    service.register_artifact(extension)
    status = service.artifact_status(ref, "review")
    assert status.effective
    assert status.paths == (manager.root / "skills/review/SKILL.md",)
    assert service.set_artifact_policy(ref, "review", "disabled").ok
    assert service.resolve_artifacts("claude", "review") == ()
    manager.version = "2"
    assert service.artifact_status(ref, "review").policy == "disabled"
    assert service.clear_artifact_policy(ref, "review").ok
    assert service.artifact_status(ref, "review").effective
    manager.enabled = False
    assert service.set_artifact_policy(ref, "review", "enabled").ok
    disabled = service.artifact_status(ref, "review")
    assert not disabled.effective
    assert disabled.reason == "native-disabled"
    assert manager.version == "2"


def test_artifact_roots_and_revision_are_revalidated(setup, tmp_path):
    service, manager, _ = setup
    manager.version = "1"
    ref = PluginRef("claude", "review@team")
    service.register_artifact(pub.ArtifactExtension("escape", "1", lambda context: (context.runtime_root / "../outside",)))
    assert service.artifact_status(ref, "escape").reason == "unsafe-artifact-path"
    service.register_artifact(pub.ArtifactExtension("safe", "1", lambda context: (context.runtime_root / "skills/review/SKILL.md",)))
    old = service.artifact_status(ref, "safe").revision
    manager.version = "2"
    assert service.artifact_status(ref, "safe", revision=old).reason == "stale-revision"
    with pytest.raises(ValueError):
        service.register_artifact(pub.ArtifactExtension("safe", "2", lambda context: ()))
    assert service.artifact_status(ref, "missing").reason == "unknown-extension"


def test_unregistered_policy_cannot_mutate_state(setup):
    service, manager, _ = setup
    manager.version = "1"
    before = service.registry.history()
    result = service.set_artifact_policy(PluginRef("claude", "review@team"), "missing", "disabled")
    assert not result.ok
    assert service.registry.history() == before


def test_global_and_plugin_name_collision_requires_explicit_mutation_provider(setup):
    service, manager, _ = setup
    manager.version = "1"
    global_skill = service.home / ".claude/skills/review/SKILL.md"
    global_skill.parent.mkdir(parents=True)
    original = "---\nname: review\ndescription: global\n---\nGLOBAL BODY"
    global_skill.write_text(original)
    assert not service.uninstall_all(AssetSelector("claude", kind="skill", name="review"), force=True).ok
    assert global_skill.read_text() == original
    adopted = service.adopt_all(AssetSelector("claude", kind="skill", provider="global"))
    assert adopted.ok
    removed = service.uninstall_all(AssetSelector("claude", kind="skill", provider="global"))
    assert removed.ok
    assert not global_skill.exists()
    restored = service.restore_all(removed.operation_id, selector=AssetSelector("claude", provider="global"))
    assert restored.ok
    assert global_skill.read_text() == original
    assert (manager.root / "skills/review/SKILL.md").read_text() == "PLUGIN SKILL BODY"


@pytest.mark.parametrize("method", ["list_assets", "adopt_all", "uninstall_all", "restore_all"])
def test_provider_filters_are_available_on_standalone_helpers(monkeypatch, method, tmp_path):
    seen = []
    monkeypatch.setattr(pub, "_call", lambda *args, **kwargs: seen.append((args, kwargs)))
    args = ("operation",) if method == "restore_all" else ()
    getattr(pub, method)(*args, agent="claude", kind="skill", provider="plugin", plugin_id="review@team", version="1", name="review", root=tmp_path)
    selected = seen[0][1]["selector"] if method == "restore_all" else seen[0][0][1]
    assert selected == AssetSelector("claude", kind="skill", provider="plugin", plugin_id="review@team", version="1", name="review")


def test_artifact_runtime_moves_and_scope_policy_remain_isolated(setup, tmp_path):
    import shutil
    from dataclasses import FrozenInstanceError
    service, manager, _ = setup
    manager.version = "1"
    manager.enabled = None
    contexts = []
    def locate(context):
        contexts.append(context)
        return (context.runtime_root / "skills/review/SKILL.md",)
    service.register_artifact(pub.ArtifactExtension("moving", "1", locate))
    ref = PluginRef("claude", "review@team")
    original = service.artifact_status(ref, "moving")
    assert original.effective  # Resolution eligibility is not a claim of native execution.
    with pytest.raises(FrozenInstanceError):
        contexts[0].runtime_root = tmp_path
    moved = tmp_path / "moved"
    shutil.move(str(manager.root), moved)
    manager.root = moved
    current = service.artifact_status(ref, "moving")
    assert current.revision == original.revision
    assert current.paths == (moved / "skills/review/SKILL.md",)
    service.project_root = tmp_path / "project"
    assert service.set_artifact_policy(PluginRef("claude", "review@team", "project"), "moving", "disabled").ok
    assert service.artifact_status(ref, "moving").policy == "inherit"
    manager.root = tmp_path / "missing"
    assert service.artifact_status(ref, "moving").reason == "runtime-root-unavailable"


def test_artifact_symlink_escape_is_rejected(setup, tmp_path):
    service, manager, _ = setup
    manager.version = "1"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.md").write_text("PRIVATE")
    link = manager.root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this filesystem")
    service.register_artifact(pub.ArtifactExtension("symlink", "1", lambda context: (context.runtime_root / "escape/private.md",)))
    status = service.artifact_status(PluginRef("claude", "review@team"), "symlink")
    assert not status.effective
    assert status.paths == ()
    assert status.reason == "unsafe-artifact-path"


def test_artifact_context_cannot_be_rebound_to_another_project(setup, tmp_path):
    from zuat.utils.contexts import project_context
    service, manager, _ = setup
    manager.version = "1"
    service.register_artifact(pub.ArtifactExtension("context", "1", lambda context: (context.runtime_root / "skills/review/SKILL.md",)))
    ref = PluginRef("claude", "review@team", "project", context=project_context(tmp_path / "project-a"))
    service.project_root = tmp_path / "project-b"
    result = service.set_artifact_policy(ref, "context", "enabled")
    assert not result.ok
    assert service.artifact_status(ref, "context").paths == ()
