"""Opt-in native catalog contract probes; every write stays in a temporary home."""

import os
import shutil

import pytest

from zuat import pub
from tests.pub.bundles.test_build import source
from zuat.utils.process import SubprocessRunner


class DiagnosticRunner(SubprocessRunner):
    def run(self, args, **context):
        result = super().run(args, **context)
        # This opt-in fixture contains only synthetic source and isolated homes.
        if result.returncode:
            pytest.fail(result.stderr)
        return result


@pytest.mark.skipif(
    os.environ.get("ZUAT_TEST_NATIVE_CATALOGS") != "1",
    reason="explicit isolated native probe only",
)
@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_installed_local_catalog_contract(tmp_path, source, agent):
    if not shutil.which(agent):
        pytest.skip("native manager is unavailable")
    home = tmp_path / "home"
    home.mkdir()
    with pub.Zuat(root=tmp_path / "tracking", home=home) as service:
        build = service.build_bundle(source)
        record = service.get_bundle(build.bundle_id)
        native = service._resolver(agent).plugin_adapter()
        native.runner = DiagnosticRunner()
        adapter = service._resolver(agent).bundle_adapter()
        output = service.resolve_bundle(build.bundle_id, agent=agent)
        first = adapter.prepare(native, record, output, service._bundles.root)
        second = adapter.prepare(native, record, output, service._bundles.root)
        assert first == second
        assert "@zuat-" in first.native_ref
        installed = service.bootstrap_bundle(
            build.bundle_id, agents=[agent], trust=True
        )
        assert installed.ok, installed
        current = service.bootstrap_bundle(build.bundle_id, agents=[agent], trust=True)
        assert current.targets[0].status == "current"
        removed = service.remove_bundle(build.bundle_id)
        assert removed.ok, removed
