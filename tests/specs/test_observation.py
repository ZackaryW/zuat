import json
from pathlib import Path

import pytest

from zuat.specs.interface import AssetKind
from zuat.specs.native import Agent, PluginActivation, PluginRecord, PluginRef, Scope
from zuat.specs.registry import resolver_for


SKILL = "---\nname: {name}\ndescription: Test skill\n---\nRun.\n"


class Inventory:
    def __init__(self, agent: Agent) -> None:
        self.record = PluginRecord(
            PluginRef(agent, "reviewer@market", Scope.USER, "market"),
            "reviewer",
            True,
            PluginActivation.ACTIVE,
            installed_version="1.0",
        )

    def discover(self, *, include_available=False):
        return (self.record,)

    def contributions(self, record):
        return ()


def write_skill(root: Path, name: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(SKILL.format(name=name), encoding="utf-8")


def write_json_hooks(path: Path, commands: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "model": "unrelated",
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": command}]}
                        for command in commands
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("agent", ("codex", "claude"))
def test_json_agents_observe_unknown_assets_in_every_supported_scope(
    tmp_path: Path, agent: str
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    if agent == "codex":
        write_skill(home / ".codex/skills/user-skill", "user-skill")
        write_skill(project / ".agents/skills/project-skill", "project-skill")
        write_json_hooks(home / ".codex/hooks.json", ("one", "two"))
        write_json_hooks(project / ".codex/hooks.json", ("project",))
        native_agent = Agent.CODEX
    else:
        write_skill(home / ".claude/skills/user-skill", "user-skill")
        write_skill(project / ".claude/skills/project-skill", "project-skill")
        write_json_hooks(home / ".claude/settings.json", ("one", "two"))
        write_json_hooks(project / ".claude/settings.json", ("project",))
        native_agent = Agent.CLAUDE

    registry = tmp_path / "observations"
    observation = resolver_for(
        agent,
        home=home,
        project_root=project,
        state_root=tmp_path / "control",
        plugins=Inventory(native_agent),
    ).observe(registry)

    skills = [asset for asset in observation.assets if asset.kind is AssetKind.SKILL]
    hooks = [asset for asset in observation.assets if asset.kind is AssetKind.HOOK]
    plugins = [asset for asset in observation.assets if asset.kind is AssetKind.PLUGIN]
    assert {(asset.name, asset.scope) for asset in skills} == {
        ("user-skill", "user"),
        ("project-skill", "project"),
    }
    assert [asset.scope for asset in hooks].count("user") == 2
    assert [asset.scope for asset in hooks].count("project") == 1
    assert len(plugins) == 1
    assert all("native_locator" in asset.evidence for asset in observation.assets)
    for asset in hooks:
        normalized = registry / asset.path
        assert "unrelated" not in normalized.read_text(encoding="utf-8")


def test_kimi_observes_unknown_skills_hooks_and_plugins(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    write_skill(home / ".kimi-code/skills/user-skill", "user-skill")
    write_skill(project / ".kimi-code/skills/project-skill", "project-skill")
    config = home / ".kimi-code/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        'model = "unrelated"\n\n[[hooks]]\nevent = "Start"\ncommand = "one"\n\n[[hooks]]\nevent = "Stop"\ncommand = "two"\n',
        encoding="utf-8",
    )

    observation = resolver_for(
        "kimi",
        home=home,
        project_root=project,
        state_root=tmp_path / "control",
        plugins=Inventory(Agent.KIMI),
    ).observe(tmp_path / "observations")

    assert {(asset.name, asset.scope) for asset in observation.assets if asset.kind is AssetKind.SKILL} == {
        ("user-skill", "user"),
        ("project-skill", "project"),
    }
    assert len([asset for asset in observation.assets if asset.kind is AssetKind.HOOK]) == 2
    assert len([asset for asset in observation.assets if asset.kind is AssetKind.PLUGIN]) == 1
    assert all("native_locator" in asset.evidence for asset in observation.assets)


def test_pi_observes_skills_extensions_and_plugins_in_both_scopes(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    write_skill(home / ".pi/agent/skills/user-skill", "user-skill")
    write_skill(project / ".pi/skills/project-skill", "project-skill")
    user_extension = home / ".pi/agent/extensions/user.ts"
    project_extension = project / ".pi/extensions/project.js"
    user_extension.parent.mkdir(parents=True)
    project_extension.parent.mkdir(parents=True)
    user_extension.write_text("export default {}", encoding="utf-8")
    project_extension.write_text("export default {}", encoding="utf-8")

    observation = resolver_for(
        "pi",
        home=home,
        project_root=project,
        state_root=tmp_path / "control",
        plugins=Inventory(Agent.PI),
    ).observe(tmp_path / "observations")

    assert {(asset.name, asset.scope) for asset in observation.assets if asset.kind is AssetKind.SKILL} == {
        ("user-skill", "user"),
        ("project-skill", "project"),
    }
    assert {asset.scope for asset in observation.assets if asset.kind is AssetKind.HOOK} == {
        "user",
        "project",
    }
    assert len([asset for asset in observation.assets if asset.kind is AssetKind.PLUGIN]) == 1
    assert all("native_locator" in asset.evidence for asset in observation.assets)
