import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from tests.pub.lookup.helpers import LookupWorld
from zuat.pub import SkillLocation, locate_skill


def test_unknown_agent_is_unsupported_without_touching_any_agent_location(
    tmp_path: Path,
) -> None:
    world = LookupWorld(tmp_path)
    world.skill(world.home / ".claude" / "skills", "pspec-tdd")
    project = world.project("a")
    before = world.snapshot()

    result = locate_skill("nonexistent", "pspec-tdd", cwd=project, home=world.home)

    assert isinstance(result, SkillLocation)
    assert result.outcome == "unsupported"
    assert result.root is None and result.entrypoint is None
    assert any("nonexistent" in message for message in result.diagnostics)
    assert result.candidates == ()
    assert world.snapshot() == before


@pytest.mark.parametrize("name", ["plugin:skill", "my-plugin:review"])
def test_plugin_qualified_name_is_unsupported(tmp_path: Path, name: str) -> None:
    world = LookupWorld(tmp_path)
    result = locate_skill("claude", name, cwd=world.project("a"), home=world.home)
    assert result.outcome == "unsupported"
    assert any(name in message for message in result.diagnostics)


def test_result_is_frozen_and_carries_requested_identity(tmp_path: Path) -> None:
    world = LookupWorld(tmp_path)
    result = locate_skill("bogus", "x", cwd=world.project("a"), home=world.home)
    assert result.agent == "bogus" and result.name == "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = "located"  # type: ignore[misc]


def test_lookup_does_not_load_the_service_or_git_registry(tmp_path: Path) -> None:
    script = f"""
import sys
from zuat.pub import locate_skill
result = locate_skill("nonexistent", "x", cwd=r"{tmp_path}", home=r"{tmp_path}")
assert result.outcome == "unsupported"
assert "zuat.pub.service" not in sys.modules
assert "zuat.gitcore.repository" not in sys.modules
assert "git" not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
