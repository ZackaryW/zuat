import json
from pathlib import Path

import pytest

from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.kimi_plugins import KimiPluginAdapter
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.specs.native import PluginOperationError, PluginRef, UnsupportedNativeOperation
from zuat.utils.ownership import OwnershipStore
from zuat.utils.process import ProcessResult


class Runner:
    def __init__(self, outputs=(), error=None):
        self.outputs = iter(outputs)
        self.calls = []
        self.error = error

    def run(self, args, *, cwd=None, environment=None):
        self.calls.append((args, cwd, environment))
        if self.error:
            raise self.error
        return ProcessResult(args, 0, next(self.outputs), "")


def adapter(cls, tmp_path, runner, **kwargs):
    return cls(home=tmp_path / "home", store=OwnershipStore(tmp_path / "control", cls.agent.value), runner=runner, **kwargs)


@pytest.mark.parametrize("cls,body", [
    (CodexPluginAdapter, {"installed": [], "available": [{"pluginId": "review@team", "name": "review", "installed": False, "version": "2"}]}),
    (ClaudePluginAdapter, {"installed": [], "available": [{"id": "review@team", "name": "review", "version": "2"}]}),
])
def test_catalog_entries_are_available_not_installed(tmp_path, cls, body):
    runner = Runner([json.dumps(body), json.dumps(body)])
    native = adapter(cls, tmp_path, runner)
    assert native.discover() == ()
    found = native.discover(include_available=True)
    assert found[0].ref.native_ref == "review@team"
    assert not found[0].installed
    assert found[0].revision is None
    assert found[0].available_version == "2"
    assert "--available" in runner.calls[1][0]


@pytest.mark.parametrize("cls", [CodexPluginAdapter, ClaudePluginAdapter, PiPluginAdapter])
def test_missing_manager_is_safe_domain_error(tmp_path, cls):
    native = adapter(cls, tmp_path, Runner(error=FileNotFoundError("C:/private/credential")))
    with pytest.raises(PluginOperationError) as failure:
        native.discover()
    assert str(failure.value) == "plugin manager unavailable"


@pytest.mark.parametrize("cls,body", [(CodexPluginAdapter, '{"installed": [{"pluginId": 7}]}'), (ClaudePluginAdapter, '[{"id": 7, "scope": "user"}]'), (PiPluginAdapter, "nonsense")])
def test_malformed_inventory_is_not_empty_success(tmp_path, cls, body):
    with pytest.raises(PluginOperationError):
        adapter(cls, tmp_path, Runner([body])).discover()


def test_pi_successful_empty_and_configured_but_missing_package(tmp_path):
    native = adapter(PiPluginAdapter, tmp_path, Runner(["No packages installed.\n", "User packages:\n  npm:review\n"]))
    assert native.discover() == ()
    found = native.discover()
    assert found == ()
    assert native.discovery_diagnostics == ("configured plugin has no verified installation",)


def test_kimi_available_discovery_is_explicitly_unsupported(tmp_path):
    native = adapter(KimiPluginAdapter, tmp_path, Runner())
    with pytest.raises(UnsupportedNativeOperation):
        native.discover(include_available=True)


def test_pi_project_requires_separate_trust(tmp_path):
    runner = Runner()
    native = adapter(PiPluginAdapter, tmp_path, runner, project_root=tmp_path / "project")
    with pytest.raises(PluginOperationError, match="project trust"):
        native.install(PluginRef("pi", "npm:review", "project"), trust=True)
    assert runner.calls == []


def test_pi_untrusted_project_discovery_is_incomplete(tmp_path):
    runner = Runner(["No packages installed.\n"])
    native = adapter(PiPluginAdapter, tmp_path, runner, project_root=tmp_path / "project")
    assert native.discover() == ()
    assert native.discovery_diagnostics == ("project plugin discovery requires project trust",)
    assert runner.calls[0][0][-1] == "--no-approve"


def test_trusted_pi_project_install_uses_selected_project_and_private_home(tmp_path):
    project = tmp_path / "project-a"
    project.mkdir()
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "package.json").write_text('{"name":"review", "version":"1"}')
    runner = Runner(["No packages installed.\n", "", f"Project packages:\n  npm:review\n    {plugin}\n"])
    native = adapter(PiPluginAdapter, tmp_path, runner, project_root=project, trust_project=True)
    outcome = native.install(PluginRef("pi", "npm:review", "project"))
    assert outcome.verified
    assert outcome.after.revision.version == "1"
    args, cwd, environment = runner.calls[1]
    assert args == ("pi", "install", "npm:review", "--local", "--approve")
    assert cwd == project
    assert environment["PI_CODING_AGENT_DIR"] == str(tmp_path / "home/.pi/agent")


def test_pi_cross_scope_update_is_rejected_before_mutation(tmp_path):
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "package.json").write_text('{"name":"review","version":"1"}')
    inventory = f"User packages:\n  npm:review\n    {root}\nProject packages:\n  npm:review\n    {root}\n"
    runner = Runner([inventory])
    native = adapter(PiPluginAdapter, tmp_path, runner, project_root=tmp_path / "project", trust_project=True)
    with pytest.raises(UnsupportedNativeOperation, match="isolate"):
        native.update(PluginRef("pi", "npm:review", "project"))
    assert all(args[1] == "list" for args, _, _ in runner.calls)


@pytest.mark.parametrize("source", ["./plugin", "../plugin", "C:/plugin", "https://example.org/plugin", "git:git@example.org:team/repo", "ssh://git@example.org/repo"])
def test_direct_source_trust_precedes_execution(tmp_path, source):
    runner = Runner()
    native = adapter(PiPluginAdapter, tmp_path, runner)
    with pytest.raises(PluginOperationError, match="require trust"):
        native.install(PluginRef("pi", source))
    assert runner.calls == []


@pytest.mark.parametrize("cls", [CodexPluginAdapter, ClaudePluginAdapter])
def test_catalog_managers_do_not_accept_direct_sources_even_when_trusted(tmp_path, cls):
    runner = Runner()
    native = adapter(cls, tmp_path, runner)
    with pytest.raises(UnsupportedNativeOperation):
        native.install(PluginRef(cls.agent, "./plugin"), trust=True)
    assert runner.calls == []


def test_codex_explicit_marketplace_resolves_canonical_identifier(tmp_path):
    cached = tmp_path / "home/.codex/plugins/cache/team/review/1"
    cached.mkdir(parents=True)
    body = {"installed": [{"pluginId": "review@team", "name": "review", "installed": True, "enabled": True, "version": "1"}]}
    runner = Runner(['{"installed":[]}', '', json.dumps(body)])
    native = adapter(CodexPluginAdapter, tmp_path, runner)
    result = native.install(PluginRef("codex", "review", source="team"))
    assert result.verified
    assert result.after.ref.native_ref == "review@team"
    assert runner.calls[1][0] == ("codex", "plugin", "add", "review@team", "--json")


@pytest.mark.parametrize("ref", [PluginRef("codex", "review"), PluginRef("codex", "review@team", source="other")])
def test_codex_ambiguous_or_conflicting_marketplace_is_rejected_before_execution(tmp_path, ref):
    runner = Runner()
    native = adapter(CodexPluginAdapter, tmp_path, runner)
    with pytest.raises((PluginOperationError, UnsupportedNativeOperation)):
        native.install(ref)
    assert runner.calls == []


def test_kimi_malformed_identifier_is_not_coerced_into_installed_identity(tmp_path):
    path = tmp_path / "home/.kimi-code/plugins/installed.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"version":1,"plugins":[{"id":7}]}')
    native = adapter(KimiPluginAdapter, tmp_path, Runner())
    with pytest.raises(PluginOperationError):
        native.discover()


def test_pi_local_source_without_safe_identity_is_explicitly_unresolved(tmp_path):
    root = tmp_path / "local-plugin"
    root.mkdir()
    (root / "package.json").write_text('{"name":"review","version":"1"}')
    native = adapter(PiPluginAdapter, tmp_path, Runner([f"User packages:\n  {root}\n    {root}\n"]))
    assert native.discover() == ()
    assert native.discovery_diagnostics == ("plugin identity is unresolved; native source details omitted",)
    assert native.unresolved_roots == (root,)
