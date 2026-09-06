import json

from zuat.pub import Zuat, ZuatRequest
from zuat.specs.claude import ClaudeResolver
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.native import PluginRef
from zuat.utils.ownership import OwnershipStore
from zuat.utils.process import ProcessResult


def test_two_projects_keep_distinct_installations_of_equal_revision(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    projects = [tmp_path / "project-a", tmp_path / "project-b"]
    for project in projects:
        project.mkdir()
    state = {project: None for project in projects}
    class Manager:
        def run(self, args, *, cwd, environment):
            assert environment == {"CLAUDE_CONFIG_DIR": str(home / ".claude")}
            if args[2] == "install":
                state[cwd] = "1"
            if args[2] == "uninstall":
                state[cwd] = None
            output = [] if state[cwd] is None else [{"id": "review@team", "scope": "project", "version": state[cwd], "enabled": True}]
            return ProcessResult(args, 0, json.dumps(output), "")
    root = tmp_path / "registry"
    def open_project(project):
        adapter = ClaudePluginAdapter(home=home, project_root=project, store=OwnershipStore(root / ".git/zuat/native", "claude"), runner=Manager())
        resolver = ClaudeResolver(home=home, project_root=project, plugins=adapter)
        return Zuat(root=root, home=home, project_root=project, resolvers={"claude": resolver})
    ref = PluginRef("claude", "review@team", "project")
    with open_project(projects[0]) as first:
        assert first.create_profile(ZuatRequest(agents=("claude",), profile="empty")).ok
        installed_a = first.install_plugin(ref)
        assert installed_a.ok, installed_a.diagnostics
    with open_project(projects[1]) as second:
        installed_b = second.install_plugin(ref)
        assert installed_b.ok, installed_b.diagnostics
        assert installed_a.plugins[0].revision == installed_b.plugins[0].revision
        assert installed_a.assets[0].ref.id != installed_b.assets[0].ref.id
        retained = second.registry.latest_observation()
        assert {item.ref.id for item in retained if item.ref.kind == "plugin"} == {installed_a.assets[0].ref.id, installed_b.assets[0].ref.id}
        assert second.remove_plugin(ref).ok
    assert state[projects[0]] == "1"
    assert state[projects[1]] is None
    with open_project(projects[0]) as first:
        observed = first.status(ZuatRequest(agents=("claude",)))
        assert next(item for item in observed.assets if item.ref.kind == "plugin").authority == "authoritative"
        switched = first.switch_profile(ZuatRequest(agents=("claude",), profile="empty", force=True))
        assert switched.ok, switched.diagnostics
        assert state[projects[0]] is None
