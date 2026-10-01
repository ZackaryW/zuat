"""Lookup must never reach registries, stores, plugin adapters, or subprocesses."""

import subprocess
from pathlib import Path

import pytest

from tests.pub.lookup.helpers import LookupWorld
from zuat.gitcore.repository import GitRegistry
from zuat.pub import locate_skill
from zuat.specs.base import ResolverSupport
from zuat.utils.ownership import OwnershipStore
from zuat.utils.process import SubprocessRunner

USER_SKILL_DIRS = {
    "claude": ".claude/skills",
    "codex": ".codex/skills",
    "kimi": ".kimi-code/skills",
    "pi": ".pi/agent/skills",
}


@pytest.fixture
def forbid_side_effect_machinery(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("lookup reached forbidden machinery")

    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)
    monkeypatch.setattr(SubprocessRunner, "run", fail, raising=False)
    monkeypatch.setattr(OwnershipStore, "__init__", fail)
    monkeypatch.setattr(GitRegistry, "__init__", fail)
    for method in ("bind", "plugins", "observe"):
        monkeypatch.setattr(ResolverSupport, method, fail)


@pytest.mark.parametrize("agent", sorted(USER_SKILL_DIRS))
def test_lookup_uses_no_registry_store_plugin_adapter_or_subprocess(
    tmp_path: Path, agent: str, forbid_side_effect_machinery: None
) -> None:
    world = LookupWorld(tmp_path)
    found = world.skill(world.home / USER_SKILL_DIRS[agent], "pspec-tdd")
    project = world.project("a")
    before = world.snapshot()

    located = locate_skill(agent, "pspec-tdd", cwd=project, home=world.home)
    missing = locate_skill(agent, "absent", cwd=project, home=world.home)
    evidence = locate_skill(
        agent, "pspec-tdd", cwd=project, home=world.home, selected=found
    )

    assert located.outcome == "located" and located.root == found.resolve()
    assert located.entrypoint == found.resolve() / "SKILL.md"
    assert located.agent == agent and located.name == "pspec-tdd"
    assert located.scope == "user" and located.provider == "global"
    assert located.provenance == "single-candidate"
    assert missing.outcome == "missing"
    assert evidence.outcome == "located" and evidence.provenance == "caller-evidence"
    assert world.snapshot() == before
