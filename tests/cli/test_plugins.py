from click.testing import CliRunner
import json
import pytest

from zuat import pub
from zuat.cli.app import cli


@pytest.fixture(autouse=True)
def prohibit_real_native_manager(monkeypatch):
    from zuat.utils.process import SubprocessRunner
    def unexpected(*args, **kwargs):
        raise AssertionError("CLI routing tests must not invoke a real native manager")
    monkeypatch.setattr(SubprocessRunner, "run", unexpected)


def test_cli_routes_separate_trust_controls_through_public_api(monkeypatch, tmp_path):
    seen = {}
    def install(ref, **kwargs):
        seen["ref"] = ref
        seen.update(kwargs)
        return pub.OperationResult("plugin-install", pub.OperationStatus.SUCCESS)
    monkeypatch.setattr(pub, "install_plugin", install, raising=False)
    result = CliRunner().invoke(cli, ["--root", str(tmp_path), "plugin", "--agent", "pi", "--project-root", str(tmp_path / "project"), "--trust-project", "install", "npm:review", "--scope", "project", "--trust", "--force", "--json"])
    assert result.exit_code == 0, result.output
    assert seen["ref"].native_ref == "npm:review"
    assert seen["trust"] is True
    assert seen["trust_project"] is True
    assert seen["force"] is True
    assert seen["project_root"] == tmp_path / "project"


def test_python_plugin_functions_are_exported():
    for name in ("discover_plugins", "install_plugin", "update_plugin", "remove_plugin", "artifact_status", "set_artifact_policy", "clear_artifact_policy", "resolve_artifacts"):
        assert callable(getattr(pub, name))


@pytest.mark.parametrize("command", ["update", "remove"])
def test_cli_mutations_dispatch_current_public_function(monkeypatch, tmp_path, command):
    seen = []
    def operation(ref, **kwargs):
        seen.append((ref, kwargs))
        return pub.OperationResult("plugin-" + command, pub.OperationStatus.FAILED, diagnostics=("unsupported",))
    monkeypatch.setattr(pub, command + "_plugin", operation)
    result = CliRunner().invoke(cli, ["--root", str(tmp_path), "plugin", "--agent", "claude", command, "review@team", "--force", "--json"])
    assert result.exit_code == 1
    assert seen[0][0] == pub.PluginRef("claude", "review@team")
    assert seen[0][1]["force"]
    assert json.loads(result.stdout)["result"]["status"] == "failed"


def test_cli_discover_returns_catalog_metadata(monkeypatch):
    seen = []
    record = pub.PluginRecord(pub.PluginRef("claude", "review@team"), "review", False, "unknown", available_version="2")
    def discover(agent, **kwargs):
        seen.append((agent, kwargs))
        return pub.OperationResult("plugin-discover", pub.OperationStatus.SUCCESS, plugins=(record,))
    monkeypatch.setattr(pub, "discover_plugins", discover)
    result = CliRunner().invoke(cli, ["plugin", "--agent", "claude", "discover", "--available", "--json"])
    assert json.loads(result.stdout)["result"]["plugins"] == [record.to_dict()]
    assert seen[0][1]["include_available"]
    human = CliRunner().invoke(cli, ["plugin", "--agent", "claude", "discover", "--available"])
    assert "review@team" in human.stdout


@pytest.mark.parametrize("policy", ["disabled", "enabled", "inherit"])
def test_cli_artifact_policy_and_status_use_public_outcome(monkeypatch, policy):
    seen = []
    def set_policy(ref, identifier, value, **kwargs):
        seen.append((ref, identifier, value))
        return pub.OperationResult("artifact-policy", pub.OperationStatus.SUCCESS)
    monkeypatch.setattr(pub, "set_artifact_policy", set_policy)
    result = CliRunner().invoke(cli, ["plugin", "--agent", "claude", "artifact", "set", "review@team", "prompts", policy, "--json"])
    assert result.exit_code == 0
    assert seen == [(pub.PluginRef("claude", "review@team"), "prompts", policy)]
    monkeypatch.setattr(pub, "artifact_status", lambda *a, **kw: pub.ArtifactStatus(a[0], a[1], policy=policy, reason="native-disabled"))
    result = CliRunner().invoke(cli, ["plugin", "--agent", "claude", "artifact", "status", "review@team", "prompts", "--json"])
    assert json.loads(result.stdout)["result"]["reason"] == "native-disabled"


@pytest.mark.parametrize("command", ["list-assets", "adopt-all", "uninstall-all", "restore-all"])
def test_cli_provider_filters_are_routed_to_asset_helpers(monkeypatch, command):
    seen = []
    def operation(**kwargs):
        seen.append(kwargs)
        return pub.OperationResult(command, pub.OperationStatus.SUCCESS)
    monkeypatch.setattr(pub, command.replace("-", "_"), operation)
    args = [command, "--agent", "claude", "--kind", "skill", "--provider", "plugin", "--plugin-id", "review@team", "--version", "1", "--name", "review"]
    if command == "restore-all":
        args.extend(["--operation-id", "operation"])
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert {key:seen[0][key] for key in ("provider", "plugin_id", "version", "name")} == {"provider":"plugin", "plugin_id":"review@team", "version":"1", "name":"review"}
