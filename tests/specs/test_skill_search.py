"""Per-agent native skill search roots and selection rules, with disposable homes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zuat.specs.claude import ClaudeResolver
from zuat.specs.codex import CodexResolver
from zuat.specs.registry import resolver_for
from zuat.utils.skill_lookup import select_skill


@pytest.fixture(autouse=True)
def isolated_system_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point managed/admin skill roots at disposable paths, never the real machine."""
    system = tmp_path / "system"
    monkeypatch.setattr(ClaudeResolver, "MANAGED_ROOT", system / "claude-managed")
    monkeypatch.setattr(CodexResolver, "ADMIN_ROOT", system / "codex-admin")
    return system


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return home


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    return repo


def _skill(root: Path, folder: str, declared: str | None = None) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {declared or folder}\n---\nbody\n", encoding="utf-8"
    )
    return path


def _lookup(agent: str, name: str, cwd: Path, home: Path, **kwargs):
    resolver = resolver_for(agent, home=home)
    return select_skill(resolver.skill_search(cwd), name, agent=agent, **kwargs)


def _symlink(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")


# --- Claude -----------------------------------------------------------------


def test_claude_locates_a_user_skill(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(home / ".claude" / "skills", "pspec-tdd")
    result = _lookup("claude", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "user"


def test_claude_locates_a_project_skill_from_a_subdirectory(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(repo / ".claude" / "skills", "pspec-tdd")
    nested = repo / "packages" / "web"
    nested.mkdir(parents=True)
    result = _lookup("claude", "pspec-tdd", nested, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "project"


def test_claude_user_copy_beats_project_copy(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    user = _skill(home / ".claude" / "skills", "pspec-tdd")
    _skill(repo / ".claude" / "skills", "pspec-tdd")
    result = _lookup("claude", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == user
    assert result.provenance == "native-rule"


def test_claude_same_name_at_two_project_levels_is_unresolved(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    top = _skill(repo / ".claude" / "skills", "pspec-tdd")
    nested = repo / "app"
    inner = _skill(nested / ".claude" / "skills", "pspec-tdd")
    result = _lookup("claude", "pspec-tdd", nested, home)
    assert result.outcome == "unresolved"
    assert str(top) in " ".join(result.diagnostics)
    assert str(inner) in " ".join(result.diagnostics)


def test_claude_one_directory_seen_as_user_and_project_is_one_installation(
    tmp_path: Path,
) -> None:
    home = _home(tmp_path)
    (home / ".git").mkdir()
    found = _skill(home / ".claude" / "skills", "pspec-tdd")
    result = _lookup("claude", "pspec-tdd", home, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.provenance == "single-candidate"


def test_claude_follows_symlinked_skill_folders(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    target = _skill(tmp_path / "shared", "real", declared="pspec-tdd")
    link = home / ".claude" / "skills" / "pspec-tdd"
    _symlink(target, link)
    result = _lookup("claude", "pspec-tdd", repo, home)
    assert result.outcome == "located"
    assert result.selected.root == target.resolve()
    assert result.selected.path == link and result.selected.via_symlink


def test_claude_managed_location_with_a_match_makes_selection_unresolved(
    tmp_path: Path, isolated_system_locations: Path
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".claude" / "skills", "pspec-tdd")
    managed = _skill(
        isolated_system_locations / "claude-managed" / ".claude" / "skills", "pspec-tdd"
    )
    result = _lookup("claude", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved"
    assert str(managed) in " ".join(result.diagnostics)
    chosen = _lookup("claude", "pspec-tdd", repo, home, selected=managed)
    assert chosen.outcome == "located" and chosen.selected.path == managed


def test_claude_skills_of_another_project_are_never_candidates(tmp_path: Path) -> None:
    home = _home(tmp_path)
    mine, other = _repo(tmp_path, "mine"), _repo(tmp_path, "other")
    _skill(other / ".claude" / "skills", "pspec-tdd")
    assert _lookup("claude", "pspec-tdd", mine, home).outcome == "missing"


# --- Codex ------------------------------------------------------------------


def _codex_config(home: Path, text: str) -> None:
    (home / ".codex").mkdir(exist_ok=True)
    (home / ".codex" / "config.toml").write_text(text, encoding="utf-8")


@pytest.mark.parametrize("relative", [".codex/skills", ".agents/skills"])
def test_codex_locates_a_user_skill_in_either_native_user_location(
    tmp_path: Path, relative: str
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(home / relative, "pspec-tdd")
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "user"


def test_codex_locates_a_project_skill_from_a_subdirectory(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(repo / ".agents" / "skills", "pspec-tdd")
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    result = _lookup("codex", "pspec-tdd", nested, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "project"


def test_codex_never_chooses_between_user_and_project_copies(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    user = _skill(home / ".codex" / "skills", "pspec-tdd")
    project = _skill(repo / ".agents" / "skills", "pspec-tdd")
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved" and result.selected is None
    assert {c.path for c in result.candidates} == {user, project}


def test_codex_two_native_user_locations_are_also_unresolved(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".codex" / "skills", "pspec-tdd")
    _skill(home / ".agents" / "skills", "pspec-tdd")
    assert _lookup("codex", "pspec-tdd", repo, home).outcome == "unresolved"


def test_codex_caller_evidence_selects_the_intended_copy(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".codex" / "skills", "pspec-tdd")
    project = _skill(repo / ".agents" / "skills", "pspec-tdd")
    result = _lookup("codex", "pspec-tdd", repo, home, selected=project)
    assert result.outcome == "located" and result.selected.path == project
    assert result.provenance == "caller-evidence"


def test_codex_native_disable_leaves_the_enabled_copy(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    user = _skill(home / ".codex" / "skills", "pspec-tdd")
    project = _skill(repo / ".agents" / "skills", "pspec-tdd")
    _codex_config(
        home,
        f'[[skills.config]]\npath = "{(user / "SKILL.md").as_posix()}"\nenabled = false\n',
    )
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == project
    assert result.provenance == "native-config"


def test_codex_enabled_entries_and_other_tables_do_not_disable(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    user = _skill(home / ".codex" / "skills", "pspec-tdd")
    _skill(repo / ".agents" / "skills", "pspec-tdd")
    _codex_config(
        home,
        f'model = "x"\n[[skills.config]]\npath = "{(user / "SKILL.md").as_posix()}"\n'
        'enabled = true\n',
    )
    assert _lookup("codex", "pspec-tdd", repo, home).outcome == "unresolved"


def test_codex_only_copy_disabled_is_missing(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    user = _skill(home / ".codex" / "skills", "pspec-tdd")
    _codex_config(
        home,
        f'[[skills.config]]\npath = "{(user / "SKILL.md").as_posix()}"\nenabled = false\n',
    )
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "missing"
    assert "disabled" in " ".join(result.diagnostics)


def test_codex_malformed_config_matters_only_when_copies_compete(
    tmp_path: Path,
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".codex" / "skills", "pspec-tdd")
    _codex_config(home, "this is = = not toml")
    assert _lookup("codex", "pspec-tdd", repo, home).outcome == "located"
    _skill(repo / ".agents" / "skills", "pspec-tdd")
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved"
    assert "config.toml" in " ".join(result.diagnostics)


def test_codex_admin_location_with_a_match_names_that_location(
    tmp_path: Path, isolated_system_locations: Path
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".codex" / "skills", "pspec-tdd")
    admin = _skill(isolated_system_locations / "codex-admin", "pspec-tdd")
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved"
    assert str(isolated_system_locations / "codex-admin") in " ".join(result.diagnostics)
    assert str(admin) in " ".join(result.diagnostics)


def test_codex_follows_symlinked_skill_folders(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    target = _skill(tmp_path / "shared", "real", declared="pspec-tdd")
    _symlink(target, repo / ".agents" / "skills" / "pspec-tdd")
    result = _lookup("codex", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.root == target.resolve()


# --- Kimi -------------------------------------------------------------------


def _kimi_config(home: Path, text: str) -> None:
    (home / ".kimi-code").mkdir(exist_ok=True)
    (home / ".kimi-code" / "config.toml").write_text(text, encoding="utf-8")


@pytest.mark.parametrize("relative", [".kimi-code/skills", ".agents/skills"])
def test_kimi_locates_a_user_skill_in_either_native_user_location(
    tmp_path: Path, relative: str
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(home / relative, "pspec-tdd")
    result = _lookup("kimi", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "user"


@pytest.mark.parametrize("relative", [".kimi-code/skills", ".agents/skills"])
def test_kimi_project_skills_are_found_from_a_subdirectory_at_the_project_root(
    tmp_path: Path, relative: str
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(repo / relative, "pspec-tdd")
    nested = repo / "deep" / "er"
    nested.mkdir(parents=True)
    result = _lookup("kimi", "pspec-tdd", nested, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "project"


def test_kimi_project_copy_beats_user_copy(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".kimi-code" / "skills", "pspec-tdd")
    project = _skill(repo / ".kimi-code" / "skills", "pspec-tdd")
    result = _lookup("kimi", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == project
    assert result.provenance == "native-rule"


def test_kimi_two_project_locations_have_no_documented_winner(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(repo / ".kimi-code" / "skills", "pspec-tdd")
    _skill(repo / ".agents" / "skills", "pspec-tdd")
    assert _lookup("kimi", "pspec-tdd", repo, home).outcome == "unresolved"


def test_kimi_extra_skill_dirs_with_a_match_make_selection_unresolved(
    tmp_path: Path,
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".kimi-code" / "skills", "pspec-tdd")
    extra = _skill(tmp_path / "team", "pspec-tdd")
    _kimi_config(home, f'extra_skill_dirs = ["{(tmp_path / "team").as_posix()}"]\n')
    result = _lookup("kimi", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved"
    assert str(extra) in " ".join(result.diagnostics)


def test_kimi_relative_extra_dir_is_resolved_against_the_project_root(
    tmp_path: Path,
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    _skill(home / ".kimi-code" / "skills", "pspec-tdd")
    extra = _skill(repo / ".agents" / "team", "pspec-tdd")
    _kimi_config(home, 'extra_skill_dirs = [".agents/team"]\n')
    nested = repo / "sub"
    nested.mkdir()
    result = _lookup("kimi", "pspec-tdd", nested, home)
    assert result.outcome == "unresolved" and str(extra) in " ".join(result.diagnostics)


def test_kimi_extra_dirs_without_a_match_are_harmless(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(home / ".kimi-code" / "skills", "pspec-tdd")
    _skill(tmp_path / "team", "other")
    _kimi_config(home, f'extra_skill_dirs = ["{(tmp_path / "team").as_posix()}"]\n')
    result = _lookup("kimi", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == found


@pytest.mark.parametrize("config", ["not = = toml", "extra_skill_dirs = 3\n"])
def test_kimi_unreadable_extra_dirs_make_selection_unresolved(
    tmp_path: Path, config: str
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(home / ".kimi-code" / "skills", "pspec-tdd")
    _kimi_config(home, config)
    result = _lookup("kimi", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved"
    assert "config.toml" in " ".join(result.diagnostics)
    chosen = _lookup("kimi", "pspec-tdd", repo, home, selected=found)
    assert chosen.outcome == "located"


def test_kimi_symlinked_skill_is_unsupported(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    target = _skill(tmp_path / "shared", "real", declared="pspec-tdd")
    _symlink(target, home / ".kimi-code" / "skills" / "pspec-tdd")
    result = _lookup("kimi", "pspec-tdd", repo, home)
    assert result.outcome == "unsupported"
    assert "symbolic link" in " ".join(result.diagnostics)


# --- Pi ---------------------------------------------------------------------


@pytest.mark.parametrize("relative", [".pi/agent/skills", ".agents/skills"])
def test_pi_locates_a_user_skill_in_either_native_user_location(
    tmp_path: Path, relative: str
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(home / relative, "pspec-tdd")
    result = _lookup("pi", "pspec-tdd", repo, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "user"


@pytest.mark.parametrize("relative", [".pi/skills", ".agents/skills"])
def test_pi_locates_project_skills_from_cwd_and_ancestors(
    tmp_path: Path, relative: str
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    found = _skill(repo / relative, "pspec-tdd")
    nested = repo / "x" / "y"
    nested.mkdir(parents=True)
    result = _lookup("pi", "pspec-tdd", nested, home)
    assert result.outcome == "located" and result.selected.path == found
    assert result.selected.scope == "project"


def test_pi_same_name_copies_are_unresolved_until_its_order_is_verified(
    tmp_path: Path,
) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    user = _skill(home / ".pi" / "agent" / "skills", "pspec-tdd")
    project = _skill(repo / ".agents" / "skills", "pspec-tdd")
    result = _lookup("pi", "pspec-tdd", repo, home)
    assert result.outcome == "unresolved" and result.selected is None
    assert {c.path for c in result.candidates} == {user, project}
    chosen = _lookup("pi", "pspec-tdd", repo, home, selected=user)
    assert chosen.outcome == "located" and chosen.provenance == "caller-evidence"


def test_pi_symlinked_skill_is_unsupported(tmp_path: Path) -> None:
    home, repo = _home(tmp_path), _repo(tmp_path)
    target = _skill(tmp_path / "shared", "real", declared="pspec-tdd")
    _symlink(target, repo / ".pi" / "skills" / "pspec-tdd")
    result = _lookup("pi", "pspec-tdd", repo, home)
    assert result.outcome == "unsupported"
