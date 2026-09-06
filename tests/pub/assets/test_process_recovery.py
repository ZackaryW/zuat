import json
import subprocess
import sys

from zuat.pub import AssetSelector, Zuat, ZuatRequest


def test_process_exit_releases_registry_lock_and_retains_restorable_update(tmp_path):
    script = """
import os, sys
from pathlib import Path
from zuat.pub import Zuat, AssetInput, ZuatRequest
base = Path(sys.argv[1])
source = base / "package/reviewer"
source.mkdir(parents=True)
document = source / "SKILL.md"
document.write_text("---\\nname: reviewer\\ndescription: Review\\n---\\nA", encoding="utf-8")
with Zuat(root=base / "registry", home=base / "home", project_root=base / "a") as state:
    asset = AssetInput("kimi", "skill", scope="project", source=str(source))
    assert state.install(ZuatRequest(agents=("kimi",), assets=(asset,))).ok
    document.write_text(document.read_text(encoding="utf-8") + "B", encoding="utf-8")
    resolver = state._resolver("kimi")
    replace = resolver.replace_asset
    def terminate(target):
        replace(target)
        os._exit(73)
    resolver.replace_asset = terminate
    state.update_asset(asset)
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 73, process.stderr
    pending = json.loads(
        (tmp_path / "registry/.git/zuat/pending-operation.json").read_text(
            encoding="utf-8"
        )
    )
    with Zuat(
        root=tmp_path / "registry", home=tmp_path / "home", project_root=tmp_path / "a"
    ) as state:
        status = state.status(ZuatRequest(agents=("kimi",)))
        assert not status.ok and status.completeness == "partial"
        assert status.data["pending_operation_id"] == pending["operation_id"]
        result = state.restore_all(
            pending["operation_id"], AssetSelector("kimi", kind="skill"), force=True
        )
        assert result.ok, result.diagnostics
        assert (
            (tmp_path / "a/.kimi-code/skills/reviewer/SKILL.md")
            .read_text(encoding="utf-8")
            .endswith("A")
        )
