"""Isolated Antigravity skill and keyed-hook lifecycle; never uses a real agent home."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from zuat.pub import AssetInput, AssetSelector, Zuat, ZuatRequest


def main():
    with TemporaryDirectory(prefix="zuat-antigravity-") as temporary:
        base = Path(temporary)
        context = {"root": base / "registry", "home": base / "home"}
        package = base / "package/reviewer"
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            "---\nname: reviewer\ndescription: Review changes\n---\nRevision A.\n", encoding="utf-8"
        )
        skill = AssetInput("antigravity", "skill", scope="user", source=str(package))

        # A keyed hook source is exactly the entry it contributes, named for its file.
        hook_path = base / "sources/powerspec.json"
        hook_path.parent.mkdir(parents=True)

        def write_hook(timeout):
            entry = {"SessionStart": [{"type": "command", "command": "pspec resolve hook sessionStart --agent antigravity --stdin-workspace", "timeout": timeout}]}
            hook_path.write_text(json.dumps({"powerspec": entry}), encoding="utf-8")

        write_hook(5)
        hook = AssetInput("antigravity", "hook", scope="user", source=str(hook_path))
        hooks_file = base / "home/.gemini/config/hooks.json"
        hooks_file.parent.mkdir(parents=True)
        hooks_file.write_text(json.dumps({"lint": {"PostToolUse": []}}), encoding="utf-8")

        with Zuat(**context) as state:
            assert state.install(ZuatRequest(agents=("antigravity",), assets=(skill, hook))).ok
            assert (base / "home/.gemini/config/skills/reviewer/SKILL.md").is_file()
            assert set(json.loads(hooks_file.read_text(encoding="utf-8"))) == {"lint", "powerspec"}

        write_hook(4)
        with Zuat(**context) as state:
            assert state.inspect_asset(hook).classification == "outdated"
            updated = state.update_asset(hook)
            assert updated.ok, updated.diagnostics

        # Reopen: restore by operation ID, then remove only the owned entry.
        with Zuat(**context) as state:
            selector = AssetSelector("antigravity", kind="hook")
            assert state.restore_all(updated.operation_id, selector, force=True).ok
            assert state.inspect_asset(hook).classification == "outdated"
            assert state.uninstall_all(AssetSelector("antigravity", kind="hook", name="powerspec")).ok
            assert state.uninstall_all(AssetSelector("antigravity", kind="skill")).ok
            assert state.inspect_asset(hook).classification == "absent"

        assert json.loads(hooks_file.read_text(encoding="utf-8")) == {"lint": {"PostToolUse": []}}
        print("Antigravity skill and keyed hook install, update, restart, restore and removal verified.")


if __name__ == "__main__":
    main()
