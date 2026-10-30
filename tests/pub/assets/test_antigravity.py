"""Antigravity skills and name-keyed hooks through the public lifecycle API."""

import json
from pathlib import Path

import pytest

from zuat.pub import SUPPORTED_AGENTS, AssetInput, AssetSelector, Zuat, ZuatRequest

SKILL = "---\nname: reviewer\ndescription: Review changes\n---\n"
ENTRY = {"SessionStart": [{"type": "command", "command": "pspec resolve hook sessionStart --agent antigravity --stdin-workspace", "timeout": 5}]}
OTHER = {"PostToolUse": [{"matcher": "run_command", "hooks": [{"command": "./lint.sh"}]}]}


def skill_source(tmp_path: Path, body: str = "A") -> AssetInput:
    package = tmp_path / "package/reviewer"
    package.mkdir(parents=True, exist_ok=True)
    (package / "SKILL.md").write_text(SKILL + body, encoding="utf-8")
    return AssetInput("antigravity", "skill", scope="user", source=str(package))


def hook_source(tmp_path: Path, entry=ENTRY, scope="user") -> AssetInput:
    path = tmp_path / "sources/powerspec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"powerspec": entry}), encoding="utf-8")
    return AssetInput("antigravity", "hook", scope=scope, source=str(path))


def state(tmp_path: Path, project: Path | None = None) -> Zuat:
    return Zuat(root=tmp_path / "registry", home=tmp_path / "home", project_root=project)


def hooks_file(tmp_path: Path) -> Path:
    return tmp_path / "home/.gemini/config/hooks.json"


def test_antigravity_is_a_supported_agent_listed_last():
    assert SUPPORTED_AGENTS[-1] == "antigravity"
    assert set(SUPPORTED_AGENTS[:-1]) == {"codex", "claude", "kimi", "pi"}


def test_user_skill_installs_to_the_unified_config_directory(tmp_path):
    legacy = tmp_path / "home/.gemini/antigravity/skills/reviewer"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text(SKILL + "legacy", encoding="utf-8")
    asset = skill_source(tmp_path)

    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
        assert current.inspect_asset(asset).classification == "current"

    installed = tmp_path / "home/.gemini/config/skills/reviewer/SKILL.md"
    assert installed.read_text(encoding="utf-8") == SKILL + "A"
    assert (legacy / "SKILL.md").read_text(encoding="utf-8") == SKILL + "legacy"
    assert not (tmp_path / "home/.claude").exists()


def test_project_skills_install_under_dot_agents_and_stay_isolated(tmp_path):
    asset = AssetInput("antigravity", "skill", scope="project", source=skill_source(tmp_path).source)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()

    with state(tmp_path, a) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
    with state(tmp_path, b) as current:
        assert current.inspect_asset(asset).classification == "absent"

    assert (a / ".agents/skills/reviewer/SKILL.md").is_file()
    assert not (b / ".agents").exists()


def test_project_scope_without_a_project_root_writes_nothing(tmp_path):
    asset = AssetInput("antigravity", "skill", scope="project", source=skill_source(tmp_path).source)

    with state(tmp_path) as current:
        assert current.inspect_asset(asset).classification in {"unsupported", "indeterminate"}
        assert not current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok

    assert not (tmp_path / "home/.gemini/config/skills").exists()


def test_hook_installs_into_an_absent_document_and_reports_current(tmp_path):
    asset = hook_source(tmp_path)

    with state(tmp_path) as current:
        assert current.inspect_asset(asset).classification == "absent"
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
        inspection = current.inspect_asset(asset)

    assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {"powerspec": ENTRY}
    assert (inspection.classification, inspection.owned, inspection.source_matches) == ("current", True, True)


def test_hook_install_preserves_other_named_hooks(tmp_path):
    hooks_file(tmp_path).parent.mkdir(parents=True)
    hooks_file(tmp_path).write_text(json.dumps({"other": OTHER}), encoding="utf-8")
    asset = hook_source(tmp_path)

    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok

    assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {"other": OTHER, "powerspec": ENTRY}


def test_outdated_hook_updates_and_restores_only_its_entry(tmp_path):
    hooks_file(tmp_path).parent.mkdir(parents=True)
    hooks_file(tmp_path).write_text(json.dumps({"other": OTHER}), encoding="utf-8")
    asset = hook_source(tmp_path)
    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
    changed = {"SessionStart": [{"type": "command", "command": "pspec resolve hook sessionStart", "timeout": 4}]}
    asset = hook_source(tmp_path, changed)

    with state(tmp_path) as current:
        assert current.inspect_asset(asset).classification == "outdated"
        updated = current.update_asset(asset)
        assert updated.ok, updated.diagnostics
        assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {"other": OTHER, "powerspec": changed}
        restored = current.restore_all(updated.operation_id, AssetSelector("antigravity", kind="hook"), force=True)
        assert restored.ok, restored.diagnostics

    assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {"other": OTHER, "powerspec": ENTRY}


def test_locally_edited_owned_hook_is_a_conflict(tmp_path):
    asset = hook_source(tmp_path)
    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
    hooks_file(tmp_path).write_text(json.dumps({"powerspec": OTHER}), encoding="utf-8")
    asset = hook_source(tmp_path, {"Stop": []})

    with state(tmp_path) as current:
        assert current.inspect_asset(asset).classification == "conflict"
        assert not current.update_asset(asset).ok

    assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {"powerspec": OTHER}


def test_matching_unowned_entry_is_adopted_without_rewriting(tmp_path):
    hooks_file(tmp_path).parent.mkdir(parents=True)
    hooks_file(tmp_path).write_text(json.dumps({"powerspec": ENTRY}, indent=8), encoding="utf-8")
    before = hooks_file(tmp_path).read_bytes()
    asset = hook_source(tmp_path)

    with state(tmp_path) as current:
        inspection = current.inspect_asset(asset)
        assert (inspection.classification, inspection.source_matches) == ("unowned", True)
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
        assert current.inspect_asset(asset).classification == "current"

    assert hooks_file(tmp_path).read_bytes() == before


@pytest.mark.parametrize(
    "text",
    ['{"powerspec": {"Stop": []}, "powerspec": {"Stop": []}}', "[]", '{"powerspec": ["x"]}'],
)
def test_ambiguous_documents_are_indeterminate_and_untouched(tmp_path, text):
    hooks_file(tmp_path).parent.mkdir(parents=True)
    hooks_file(tmp_path).write_text(text, encoding="utf-8")
    asset = hook_source(tmp_path)

    with state(tmp_path) as current:
        assert current.inspect_asset(asset).classification == "indeterminate"
        assert not current.install(ZuatRequest(agents=("antigravity",), assets=(asset,), force=True)).ok

    assert hooks_file(tmp_path).read_text(encoding="utf-8") == text


def test_removing_hooks_touches_only_owned_entries(tmp_path):
    hooks_file(tmp_path).parent.mkdir(parents=True)
    hooks_file(tmp_path).write_text(json.dumps({"other": OTHER}), encoding="utf-8")
    asset = hook_source(tmp_path)
    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
        assert current.uninstall_all(AssetSelector("antigravity", kind="hook", name="powerspec")).ok
    assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {"other": OTHER}

    hooks_file(tmp_path).write_text("{}", encoding="utf-8")
    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
        assert current.uninstall_all(AssetSelector("antigravity", kind="hook", name="powerspec")).ok
    assert json.loads(hooks_file(tmp_path).read_text(encoding="utf-8")) == {}


def test_project_hooks_live_in_dot_agents_and_stay_isolated(tmp_path):
    asset = hook_source(tmp_path, scope="project")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()

    with state(tmp_path, a) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
    with state(tmp_path, b) as current:
        assert current.inspect_asset(asset).classification == "absent"

    assert json.loads((a / ".agents/hooks.json").read_text(encoding="utf-8")) == {"powerspec": ENTRY}
    assert not hooks_file(tmp_path).exists()


def test_observation_reports_unowned_named_hooks(tmp_path):
    hooks_file(tmp_path).parent.mkdir(parents=True)
    hooks_file(tmp_path).write_text(json.dumps({"other": OTHER}), encoding="utf-8")

    with state(tmp_path) as current:
        observed = current.status(ZuatRequest(agents=("antigravity",))).assets

    hooks = [item for item in observed if item.ref.kind == "hook"]
    assert [item.ref.locator for item in hooks] == ["hooks/other"]


def test_other_agents_never_touch_antigravity_paths(tmp_path):
    asset = AssetInput("kimi", "skill", scope="user", source=skill_source(tmp_path).source)

    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("kimi",), assets=(asset,))).ok

    assert not (tmp_path / "home/.gemini").exists()


def test_registry_created_before_antigravity_still_manages_it(tmp_path):
    kimi = AssetInput("kimi", "skill", scope="user", source=skill_source(tmp_path).source)
    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("kimi",), assets=(kimi,))).ok
    for marker in sorted((tmp_path / "registry").rglob("antigravity"), reverse=True):
        if ".git" not in marker.parts:
            for item in sorted(marker.rglob("*"), reverse=True):
                item.unlink() if item.is_file() else item.rmdir()
            marker.rmdir()
    asset = skill_source(tmp_path)

    with state(tmp_path) as current:
        assert current.install(ZuatRequest(agents=("antigravity",), assets=(asset,))).ok
        assert current.inspect_asset(asset).classification == "current"
