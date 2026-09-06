import json
from pathlib import Path

import pytest

from zuat.specs.native import Agent, PluginOperationError, PluginRef, Scope, UnsupportedNativeOperation
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.specs.kimi_plugins import KimiPluginAdapter
from zuat.utils.ownership import OwnershipStore
from zuat.utils.process import ProcessResult


class QueueRunner:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    def run(self, args, *, cwd=None, environment=None):
        del cwd
        self.calls.append((args, environment))
        return ProcessResult(args, 0, self.outputs.pop(0), "")


def codex_inventory(*, installed: bool) -> str:
    entries = []
    if installed:
        entries.append(
            {
                "pluginId": "reviewer@market",
                "name": "reviewer",
                "marketplaceName": "market",
                "installed": True,
                "enabled": True,
                "version": "1.0",
            }
        )
    return json.dumps({"installed": entries, "available": []})


def test_codex_plugin_mutation_uses_argv_private_home_and_rediscovery(tmp_path: Path) -> None:
    runner = QueueRunner(
        [codex_inventory(installed=False), "{}", codex_inventory(installed=True)]
    )
    store = OwnershipStore(tmp_path / "control", "codex")
    adapter = CodexPluginAdapter(home=tmp_path / "home", store=store, runner=runner)
    ref = PluginRef(Agent.CODEX, "reviewer@market", Scope.USER, "market")

    result = adapter.install(ref)

    assert result.verified
    assert runner.calls[0][0] == ("codex", "plugin", "list", "--json")
    assert runner.calls[1][0] == (
        "codex",
        "plugin",
        "add",
        "reviewer@market",
        "--json",
    )
    assert runner.calls[0][1] == {"CODEX_HOME": str(tmp_path / "home/.codex")}
    assert store.load("plugin", "reviewer@market") is not None


def test_direct_plugin_source_requires_explicit_trust(tmp_path: Path) -> None:
    runner = QueueRunner([])
    adapter = CodexPluginAdapter(
        home=tmp_path / "home",
        store=OwnershipStore(tmp_path / "control", "codex"),
        runner=runner,
    )

    with pytest.raises(PluginOperationError, match="require trust"):
        adapter.install(PluginRef(Agent.CODEX, "https://example.invalid/plugin"))
    assert runner.calls == []


def test_equivalent_plugin_is_adopted_as_provenance_without_mutation(
    tmp_path: Path,
) -> None:
    runner = QueueRunner([codex_inventory(installed=True)])
    store = OwnershipStore(tmp_path / "control", "codex")
    adapter = CodexPluginAdapter(home=tmp_path / "home", store=store, runner=runner)
    ref = PluginRef(Agent.CODEX, "reviewer@market", Scope.USER, "market")

    result = adapter.install(ref)

    assert result.status == "current"
    assert result.verified
    assert store.load("plugin", ref.native_ref, ref.scope.value) is not None
    assert len(runner.calls) == 1


def test_forced_domain_removal_does_not_require_legacy_ownership_gate(
    tmp_path: Path,
) -> None:
    runner = QueueRunner(
        [codex_inventory(installed=True), "{}", codex_inventory(installed=False)]
    )
    adapter = CodexPluginAdapter(
        home=tmp_path / "home",
        store=OwnershipStore(tmp_path / "control", "codex"),
        runner=runner,
    )
    ref = PluginRef(Agent.CODEX, "reviewer@market", Scope.USER, "market")

    result = adapter.remove(ref)

    assert result.status == "removed"
    assert result.verified


def test_claude_plugin_install_uses_scope_and_rediscovery(tmp_path: Path) -> None:
    before = "[]"
    after = json.dumps(
        [
            {
                "id": "reviewer@market",
                "scope": "project",
                "enabled": True,
                "version": "1.0",
            }
        ]
    )
    runner = QueueRunner([before, "", after])
    adapter = ClaudePluginAdapter(
        home=tmp_path / "home",
        project_root=tmp_path / "project",
        store=OwnershipStore(tmp_path / "control", "claude"),
        runner=runner,
    )
    ref = PluginRef(Agent.CLAUDE, "reviewer@market", Scope.PROJECT, "market")

    result = adapter.install(ref)

    assert result.verified
    assert runner.calls[1][0] == (
        "claude",
        "plugin",
        "install",
        "reviewer@market",
        "--scope",
        "project",
    )


def test_pi_missing_runtime_root_cannot_verify_installation(
    tmp_path: Path,
) -> None:
    empty = "User packages:\nProject packages:\n"
    installed = (
        "User packages:\n"
        "  npm:reviewer\n"
        "    C:/plugins/reviewer\n"
        "Project packages:\n"
    )
    runner = QueueRunner([empty, "", installed])
    adapter = PiPluginAdapter(
        home=tmp_path / "home",
        store=OwnershipStore(tmp_path / "control", "pi"),
        runner=runner,
    )
    ref = PluginRef(Agent.PI, "npm:reviewer", Scope.USER, "npm")

    result = adapter.install(ref)

    assert result.status == "indeterminate"
    assert not result.verified


def test_missing_post_install_rediscovery_is_indeterminate(tmp_path: Path) -> None:
    runner = QueueRunner(
        [codex_inventory(installed=False), "{}", codex_inventory(installed=False)]
    )
    adapter = CodexPluginAdapter(
        home=tmp_path / "home",
        store=OwnershipStore(tmp_path / "control", "codex"),
        runner=runner,
    )

    result = adapter.install(
        PluginRef(Agent.CODEX, "reviewer@market", Scope.USER, "market")
    )

    assert result.status == "indeterminate"
    assert not result.verified


def test_kimi_plugins_are_discovery_only(tmp_path: Path) -> None:
    inventory = tmp_path / "home" / ".kimi-code" / "plugins" / "installed.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": [
                    {
                        "id": "reviewer",
                        "root": "ignored-runtime",
                        "enabled": True,
                        "source": "market",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = KimiPluginAdapter(
        home=tmp_path / "home",
        store=OwnershipStore(tmp_path / "control", "kimi"),
    )
    ref = PluginRef(Agent.KIMI, "reviewer")

    assert adapter.discover()[0].ref.native_ref == ref.native_ref
    with pytest.raises(UnsupportedNativeOperation, match="no supported"):
        adapter.install(ref)
