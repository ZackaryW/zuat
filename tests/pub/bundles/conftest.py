import pytest

from zuat import pub
from zuat.specs.claude import ClaudeResolver
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.codex import CodexResolver
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.pi import PiResolver
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.utils.ownership import OwnershipStore
from tests.pub.bundles.native import CatalogManager, PiManager
from tests.pub.bundles.test_build import source


@pytest.fixture
def native_service(tmp_path):
    home = tmp_path / "home"
    root = tmp_path / "tracking"
    native_root = root / ".git/zuat/native"
    managers = {
        "codex": CatalogManager(home, "codex"),
        "claude": CatalogManager(home, "claude"),
        "pi": PiManager(),
    }
    resolvers = {}
    for agent, adapter_cls, resolver_cls in (
        ("codex", CodexPluginAdapter, CodexResolver),
        ("claude", ClaudePluginAdapter, ClaudeResolver),
        ("pi", PiPluginAdapter, PiResolver),
    ):
        adapter = adapter_cls(
            home=home, store=OwnershipStore(native_root, agent), runner=managers[agent]
        )
        resolvers[agent] = resolver_cls(
            home=home, state_root=native_root, plugins=adapter
        )
    with pub.Zuat(root=root, home=home, resolvers=resolvers) as service:
        yield service, managers
