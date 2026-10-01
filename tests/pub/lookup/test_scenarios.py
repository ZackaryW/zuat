"""One public-API test per installed-skill-lookup scenario, each proving no state is created."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.pub.lookup.helpers import LookupWorld
from zuat.pub import AssetInput, Zuat, ZuatRequest, locate_skill

NAME = "pspec-tdd"


@pytest.fixture
def world(tmp_path: Path) -> LookupWorld:
    return LookupWorld(tmp_path)


def run(world: LookupWorld, agent: str, cwd: Path, name: str = NAME, **kwargs):
    """Look up, asserting that the lookup left every file and directory entry untouched."""
    before = world.snapshot()
    result = locate_skill(agent, name, cwd=cwd, home=world.home, **kwargs)
    assert world.snapshot() == before
    return result


def codex_disable(world: LookupWorld, skill: Path) -> None:
    config = world.home / ".codex"
    config.mkdir(exist_ok=True)
    (config / "config.toml").write_text(
        f'[[skills.config]]\npath = "{(skill / "SKILL.md").as_posix()}"\nenabled = false\n',
        encoding="utf-8",
    )


# --- read-only query ---------------------------------------------------------


def test_lookup_without_a_registry_locates_a_user_skill_and_creates_nothing(
    world: LookupWorld,
) -> None:
    found = world.skill(world.home / ".claude" / "skills", NAME)
    project = world.project("a")
    assert not world.registry.exists() and not world.control.exists()

    result = run(world, "claude", project)

    assert result.outcome == "located" and result.root == found.resolve()
    assert not world.registry.exists() and not world.control.exists()


def test_repeated_lookup_returns_equal_results_with_no_cache_state(
    world: LookupWorld,
) -> None:
    world.skill(world.home / ".codex" / "skills", NAME)
    project = world.project("a")
    first = run(world, "codex", project)
    second = run(world, "codex", project)
    assert first == second and first.outcome == "located"


# --- outcomes ----------------------------------------------------------------


def test_missing_skill_names_the_agent_and_requested_skill(world: LookupWorld) -> None:
    world.skill(world.home / ".claude" / "skills", "something-else")
    result = run(world, "claude", world.project("a"))
    assert result.outcome == "missing" and result.root is None
    assert any(NAME in message and "claude" in message for message in result.diagnostics)


def test_unsupported_agent_searches_no_agent_location(world: LookupWorld) -> None:
    for directory in (".claude/skills", ".codex/skills", ".kimi-code/skills", ".pi/agent/skills"):
        world.skill(world.home / directory, NAME)
    result = run(world, "gemini", world.project("a"))
    assert result.outcome == "unsupported" and result.candidates == ()


# --- identity ----------------------------------------------------------------


def test_declared_name_may_differ_from_the_folder_name(world: LookupWorld) -> None:
    folder = world.skill(world.home / ".claude" / "skills", "review-helper", declared=NAME)
    result = run(world, "claude", world.project("a"))
    assert result.outcome == "located" and result.root == folder.resolve()
    assert result.entrypoint == folder.resolve() / "SKILL.md"


# --- search ------------------------------------------------------------------


def test_project_skill_at_the_repository_root_is_found_from_a_subdirectory(
    world: LookupWorld,
) -> None:
    project = world.project("a")
    found = world.skill(project / ".claude" / "skills", NAME)
    nested = project / "packages" / "web"
    nested.mkdir(parents=True)
    result = run(world, "claude", nested)
    assert result.outcome == "located" and result.root == found.resolve()
    assert result.scope == "project"


def test_two_projects_share_one_user_installation_without_leaking_context(
    world: LookupWorld,
) -> None:
    user = world.skill(world.home / ".codex" / "skills", NAME)
    a, b = world.project("a"), world.project("b")
    own = world.skill(b / ".agents" / "skills", NAME)

    from_a = run(world, "codex", a)
    assert from_a.outcome == "located" and from_a.root == user.resolve()
    assert [c.path for c in from_a.candidates] == [user]

    from_b = run(world, "codex", b)
    assert from_b.outcome == "unresolved"
    assert {c.path for c in from_b.candidates} == {user, own}


# --- native selection --------------------------------------------------------


def test_claude_user_copy_is_selected_over_a_project_copy(world: LookupWorld) -> None:
    user = world.skill(world.home / ".claude" / "skills", NAME)
    project = world.project("a")
    world.skill(project / ".claude" / "skills", NAME)
    result = run(world, "claude", project)
    assert result.outcome == "located" and result.root == user.resolve()
    assert result.provenance == "native-rule" and len(result.candidates) == 2


def test_kimi_project_copy_is_selected_over_a_user_copy(world: LookupWorld) -> None:
    world.skill(world.home / ".kimi-code" / "skills", NAME)
    project = world.project("a")
    mine = world.skill(project / ".kimi-code" / "skills", NAME)
    result = run(world, "kimi", project)
    assert result.outcome == "located" and result.root == mine.resolve()
    assert result.provenance == "native-rule"


def test_codex_copies_without_evidence_are_unresolved_and_listed(
    world: LookupWorld,
) -> None:
    user = world.skill(world.home / ".codex" / "skills", NAME)
    project = world.project("a")
    mine = world.skill(project / ".agents" / "skills", NAME)
    result = run(world, "codex", project)
    assert result.outcome == "unresolved" and result.root is None
    assert {c.path for c in result.candidates} == {user, mine}
    assert str(user) in " ".join(result.diagnostics)
    assert str(mine) in " ".join(result.diagnostics)


def test_codex_copy_disabled_natively_leaves_the_enabled_copy(
    world: LookupWorld,
) -> None:
    user = world.skill(world.home / ".codex" / "skills", NAME)
    project = world.project("a")
    mine = world.skill(project / ".agents" / "skills", NAME)
    codex_disable(world, user)
    result = run(world, "codex", project)
    assert result.outcome == "located" and result.root == mine.resolve()
    assert result.provenance == "native-config"


def test_profile_install_scope_does_not_decide_selection(world: LookupWorld) -> None:
    world.skill(world.home / ".codex" / "skills", NAME)
    project = world.project("a")
    source = world.skill(world.base / "source", NAME)
    with Zuat(root=world.registry, home=world.home, project_root=project) as state:
        installed = state.install(
            ZuatRequest(
                agents=("codex",),
                assets=(AssetInput("codex", "skill", scope="project", source=str(source)),),
            )
        )
        assert installed.ok, installed.diagnostics
    assert (project / ".agents" / "skills" / NAME / "SKILL.md").is_file()

    result = run(world, "codex", project)

    assert result.outcome == "unresolved"
    assert {c.tier for c in result.candidates} == {"user", "project"}


# --- caller evidence ---------------------------------------------------------


def test_evidence_selects_the_intended_codex_copy(world: LookupWorld) -> None:
    world.skill(world.home / ".codex" / "skills", NAME)
    project = world.project("a")
    mine = world.skill(project / ".agents" / "skills", NAME)
    result = run(world, "codex", project, selected=mine)
    assert result.outcome == "located" and result.root == mine.resolve()
    assert result.provenance == "caller-evidence"


def test_evidence_outside_the_candidates_is_invalid_and_substitutes_nothing(
    world: LookupWorld,
) -> None:
    world.skill(world.home / ".codex" / "skills", NAME)
    stray = world.skill(world.base / "stray", NAME)
    result = run(world, "codex", world.project("a"), selected=stray)
    assert result.outcome == "invalid" and result.root is None
    assert str(stray) in " ".join(result.diagnostics)


# --- invalid installations ---------------------------------------------------


def test_folder_named_for_the_skill_with_malformed_metadata_is_invalid(
    world: LookupWorld,
) -> None:
    broken = world.home / ".claude" / "skills" / NAME
    broken.mkdir(parents=True)
    (broken / "SKILL.md").write_text("---\ndescription: no name\n---\n")
    result = run(world, "claude", world.project("a"))
    assert result.outcome == "invalid" and str(broken) in " ".join(result.diagnostics)


def test_folder_named_for_the_skill_without_an_entrypoint_is_invalid(
    world: LookupWorld,
) -> None:
    broken = world.home / ".claude" / "skills" / NAME
    broken.mkdir(parents=True)
    result = run(world, "claude", world.project("a"))
    assert result.outcome == "invalid" and str(broken) in " ".join(result.diagnostics)


def test_unrelated_broken_skill_does_not_affect_the_requested_one(
    world: LookupWorld,
) -> None:
    root = world.home / ".claude" / "skills"
    found = world.skill(root, NAME)
    (root / "garbage").mkdir()
    (root / "garbage" / "SKILL.md").write_bytes(b"\xff\xfe not utf-8")
    (root / "empty").mkdir()
    result = run(world, "claude", world.project("a"))
    assert result.outcome == "located" and result.root == found.resolve()


# --- symlinks and providers --------------------------------------------------


def test_claude_symlinked_skill_reports_target_root_and_keeps_the_link_path(
    world: LookupWorld,
) -> None:
    target = world.skill(world.base / "shared", "real", declared=NAME)
    link = world.home / ".claude" / "skills" / NAME
    link.parent.mkdir(parents=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    result = run(world, "claude", world.project("a"))
    assert result.outcome == "located" and result.root == target.resolve()
    assert [c.path for c in result.candidates] == [link]
    assert result.provider == "global"


def test_pi_symlinked_skill_is_unsupported(world: LookupWorld) -> None:
    target = world.skill(world.base / "shared", "real", declared=NAME)
    link = world.home / ".pi" / "agent" / "skills" / NAME
    link.parent.mkdir(parents=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    result = run(world, "pi", world.project("a"))
    assert result.outcome == "unsupported"
    assert "symbolic link" in " ".join(result.diagnostics)


@pytest.mark.parametrize("agent", ["claude", "codex", "kimi", "pi"])
def test_plugin_qualified_names_are_unsupported(world: LookupWorld, agent: str) -> None:
    result = run(world, agent, world.project("a"), name="my-plugin:review")
    assert result.outcome == "unsupported"


# --- unmodeled locations -----------------------------------------------------


def test_codex_admin_location_with_a_match_makes_selection_unresolved(
    world: LookupWorld, isolated_system_locations: Path
) -> None:
    world.skill(world.home / ".codex" / "skills", NAME)
    admin = world.skill(isolated_system_locations / "codex-admin", NAME)
    result = run(world, "codex", world.project("a"))
    assert result.outcome == "unresolved"
    assert str(isolated_system_locations / "codex-admin") in " ".join(result.diagnostics)
    assert str(admin) in " ".join(result.diagnostics)
