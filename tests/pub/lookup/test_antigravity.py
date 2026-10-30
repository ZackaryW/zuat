"""Antigravity installed-skill lookup: documented priority, conservative elsewhere."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.pub.lookup.helpers import LookupWorld
from tests.pub.lookup.test_scenarios import NAME, run


@pytest.fixture
def world(tmp_path: Path) -> LookupWorld:
    return LookupWorld(tmp_path)


def unified(world: LookupWorld) -> Path:
    return world.home / ".gemini/config/skills"


def test_single_user_copy_is_located(world):
    copy = world.skill(unified(world), NAME)

    result = run(world, "antigravity", world.project("a"))

    assert (result.outcome, result.root, result.provenance) == ("located", copy.resolve(), "single-candidate")


@pytest.mark.parametrize("spelling", [".agents", ".agent", "_agents", "_agent"])
def test_project_copy_beats_user_copy_in_every_spelling(world, spelling):
    world.skill(unified(world), NAME)
    project = world.project("a")
    mine = world.skill(project / spelling / "skills", NAME)

    result = run(world, "antigravity", project)

    assert (result.outcome, result.root, result.provenance) == ("located", mine.resolve(), "native-rule")


def test_project_copy_is_found_from_a_subdirectory(world):
    project = world.project("a")
    mine = world.skill(project / ".agents/skills", NAME)
    nested = project / "src/deep"
    nested.mkdir(parents=True)

    result = run(world, "antigravity", nested)

    assert (result.outcome, result.root) == ("located", mine.resolve())


def test_copies_in_two_user_directories_are_unresolved(world):
    world.skill(unified(world), NAME)
    world.skill(world.home / ".gemini/antigravity/skills", NAME)

    result = run(world, "antigravity", world.project("a"))

    assert result.outcome == "unresolved" and len(result.candidates) == 2


def test_cli_user_directory_is_searched(world):
    copy = world.skill(world.home / ".gemini/antigravity-cli/skills", NAME)

    assert run(world, "antigravity", world.project("a")).root == copy.resolve()


def test_copies_at_two_project_levels_are_unresolved(world):
    project = world.project("a")
    world.skill(project / ".agents/skills", NAME)
    nested = project / "pkg"
    world.skill(nested / ".agents/skills", NAME)

    result = run(world, "antigravity", nested)

    assert result.outcome == "unresolved" and len(result.candidates) == 2


def test_declared_skill_directory_shadows_a_project_copy(world):
    project = world.project("a")
    world.skill(project / ".agents/skills", NAME)
    world.skill(project / "tools/agents/skills", NAME)
    (project / ".agents/skills.json").write_text(
        json.dumps({"entries": [{"path": "tools/agents/skills"}]}), encoding="utf-8"
    )

    result = run(world, "antigravity", project)

    assert result.outcome == "unresolved"
    assert any("tools" in item for item in result.diagnostics)


def test_inherited_and_global_declarations_are_followed_without_looping(world):
    project = world.project("a")
    world.skill(project / ".agents/skills", NAME)
    shared = world.base / "shared"
    world.skill(shared / "skills", NAME)
    (shared / "base.json").write_text(
        json.dumps({"entries": [{"path": str(shared / "skills")}],
                    "inherits": [{"path": str(shared / "base.json")}]}), encoding="utf-8"
    )
    config = world.home / ".gemini/config"
    config.mkdir(parents=True)
    (config / "skills.json").write_text(
        json.dumps({"inherits": [{"path": str(shared / "base.json")}]}), encoding="utf-8"
    )

    assert run(world, "antigravity", project).outcome == "unresolved"


def test_unreadable_declaration_blocks_a_confident_answer(world):
    project = world.project("a")
    world.skill(project / ".agents/skills", NAME)
    (project / ".agents/skills.json").write_text("{nope", encoding="utf-8")

    result = run(world, "antigravity", project)

    assert result.outcome == "unresolved"
    assert any("skills.json" in item for item in result.diagnostics)


@pytest.mark.skipif(os.name == "nt" and not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_symlinked_skill_is_unsupported(world):
    target = world.skill(world.base / "elsewhere", NAME)
    unified(world).mkdir(parents=True)
    try:
        (unified(world) / NAME).symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted")

    assert run(world, "antigravity", world.project("a")).outcome == "unsupported"
