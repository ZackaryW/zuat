import pytest

from zuat.specs.native import PluginRef, UnsupportedNativeOperation
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.specs.kimi_plugins import KimiPluginAdapter
from zuat.utils.ownership import OwnershipStore


class NeverRun:
    def run(self, *args, **kwargs):
        raise AssertionError("unsupported operation reached native execution")


@pytest.mark.parametrize("adapter_type,agent,scope,operation", [
    (ClaudePluginAdapter, "claude", "managed", "install"),
    (ClaudePluginAdapter, "claude", "managed", "remove"),
    (CodexPluginAdapter, "codex", "project", "install"),
    (KimiPluginAdapter, "kimi", "user", "update"),
])
def test_operation_specific_scope_rejects_before_native_execution(tmp_path, adapter_type, agent, scope, operation):
    adapter = adapter_type(home=tmp_path, store=OwnershipStore(tmp_path / "state", agent), runner=NeverRun())
    with pytest.raises(UnsupportedNativeOperation):
        getattr(adapter, operation)(PluginRef(agent, "review@team", scope))


def test_capabilities_do_not_treat_all_claude_scopes_as_mutable(tmp_path):
    adapter = ClaudePluginAdapter(home=tmp_path, store=OwnershipStore(tmp_path / "state", "claude"))
    assert adapter.capabilities.supports("update", "managed")
    assert not adapter.capabilities.supports("install", "managed")
    assert not adapter.capabilities.supports("remove", "managed")
    assert adapter.capabilities.available
    assert not adapter.capabilities.exact_versions


def test_discovery_only_capability_is_explicit(tmp_path):
    adapter = KimiPluginAdapter(home=tmp_path, store=OwnershipStore(tmp_path / "state", "kimi"))
    assert adapter.capabilities.supports("discover", "user")
    assert not adapter.capabilities.supports("install", "user")
    assert not adapter.capabilities.available
