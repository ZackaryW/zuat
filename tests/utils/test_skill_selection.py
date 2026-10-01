from pathlib import Path

import pytest

from zuat.utils.skill_lookup import SkillSearch, SkillTier, select_skill


def _skill(root: Path, folder: str, declared: str | None = None) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {declared or folder}\n---\nbody\n", encoding="utf-8"
    )
    return path


def _tier(tmp_path: Path, label: str, scope: str | None = None) -> SkillTier:
    return SkillTier(label, scope or label, tmp_path / label)


def _search(tmp_path: Path, *labels: str, **kwargs) -> SkillSearch:
    return SkillSearch(tiers=tuple(_tier(tmp_path, label) for label in labels), **kwargs)


def test_no_copy_is_missing(tmp_path: Path) -> None:
    result = select_skill(_search(tmp_path, "user", "project"), "x", agent="claude")
    assert result.outcome == "missing" and result.selected is None
    assert any("x" in message and "claude" in message for message in result.diagnostics)


def test_single_copy_is_located_with_single_candidate_provenance(tmp_path: Path) -> None:
    found = _skill(tmp_path / "project", "x")
    result = select_skill(_search(tmp_path, "user", "project"), "x", agent="claude")
    assert result.outcome == "located"
    assert result.selected and result.selected.path == found
    assert result.provenance == "single-candidate"
    assert result.selected.scope == "project"


def test_same_directory_reached_twice_is_one_installation(tmp_path: Path) -> None:
    found = _skill(tmp_path / "user", "x")
    twin = SkillTier("project", "project", tmp_path / "user")
    search = SkillSearch(tiers=(_tier(tmp_path, "user"), twin))
    result = select_skill(search, "x", agent="claude")
    assert result.outcome == "located" and result.selected.path == found
    assert len(result.candidates) == 1


@pytest.mark.parametrize(
    ("prefer", "expected"),
    [(("user", "project"), "user"), (("project", "user"), "project")],
)
def test_prefer_order_selects_the_native_winner(
    tmp_path: Path, prefer: tuple[str, ...], expected: str
) -> None:
    _skill(tmp_path / "user", "x")
    _skill(tmp_path / "project", "x")
    result = select_skill(
        _search(tmp_path, "user", "project", prefer=prefer), "x", agent="a"
    )
    assert result.outcome == "located"
    assert result.selected.scope == expected
    assert result.provenance == "native-rule"
    assert len(result.candidates) == 2


def test_two_copies_in_the_preferred_scope_are_unresolved(tmp_path: Path) -> None:
    _skill(tmp_path / "user", "x")
    first = _skill(tmp_path / "project", "x")
    second = _skill(tmp_path / "project", "y", declared="x")
    search = SkillSearch(
        tiers=(
            _tier(tmp_path, "user"),
            SkillTier("project", "project", tmp_path / "project"),
        ),
        prefer=("project", "user"),
    )
    result = select_skill(search, "x", agent="a")
    assert result.outcome == "unresolved"
    assert str(first) in " ".join(result.diagnostics)
    assert str(second) in " ".join(result.diagnostics)


def test_without_a_native_rule_two_copies_are_unresolved_and_listed(
    tmp_path: Path,
) -> None:
    user = _skill(tmp_path / "user", "x")
    project = _skill(tmp_path / "project", "x")
    result = select_skill(_search(tmp_path, "user", "project"), "x", agent="codex")
    assert result.outcome == "unresolved" and result.selected is None
    assert {candidate.path for candidate in result.candidates} == {user, project}
    joined = " ".join(result.diagnostics)
    assert str(user) in joined and str(project) in joined


def test_native_disable_evidence_leaves_one_copy(tmp_path: Path) -> None:
    user = _skill(tmp_path / "user", "x")
    project = _skill(tmp_path / "project", "x")
    search = _search(tmp_path, "user", "project", disabled=frozenset({user.resolve()}))
    result = select_skill(search, "x", agent="codex")
    assert result.outcome == "located"
    assert result.selected.path == project
    assert result.provenance == "native-config"


def test_only_copy_disabled_is_missing_with_a_diagnostic(tmp_path: Path) -> None:
    user = _skill(tmp_path / "user", "x")
    search = _search(tmp_path, "user", disabled=frozenset({user.resolve()}))
    result = select_skill(search, "x", agent="codex")
    assert result.outcome == "missing"
    assert any("disabled" in message and str(user) in message for message in result.diagnostics)


def test_unreadable_evidence_blocks_selection_only_when_copies_compete(
    tmp_path: Path,
) -> None:
    _skill(tmp_path / "user", "x")
    search = _search(tmp_path, "user", "project", evidence_errors=("config unreadable",))
    assert select_skill(search, "x", agent="codex").outcome == "located"

    _skill(tmp_path / "project", "x")
    result = select_skill(search, "x", agent="codex")
    assert result.outcome == "unresolved"
    assert "config unreadable" in " ".join(result.diagnostics)


def test_blocking_reason_makes_every_unselected_lookup_unresolved(
    tmp_path: Path,
) -> None:
    _skill(tmp_path / "user", "x")
    search = _search(tmp_path, "user", blocking=("extra dirs unreadable",))
    result = select_skill(search, "x", agent="kimi")
    assert result.outcome == "unresolved"
    assert "extra dirs unreadable" in " ".join(result.diagnostics)


def test_unmodeled_location_with_a_match_blocks_a_confident_answer(
    tmp_path: Path,
) -> None:
    _skill(tmp_path / "user", "x")
    shadow = _skill(tmp_path / "admin", "x")
    search = _search(tmp_path, "user", unmodeled=(_tier(tmp_path, "admin"),))
    result = select_skill(search, "x", agent="codex")
    assert result.outcome == "unresolved"
    assert str(tmp_path / "admin") in " ".join(result.diagnostics)
    assert str(shadow) in " ".join(result.diagnostics)


def test_unmodeled_location_without_a_match_is_harmless(tmp_path: Path) -> None:
    _skill(tmp_path / "user", "x")
    _skill(tmp_path / "admin", "other")
    search = _search(tmp_path, "user", unmodeled=(_tier(tmp_path, "admin"),))
    assert select_skill(search, "x", agent="codex").outcome == "located"


def test_broken_copy_named_for_the_skill_is_invalid_even_with_a_valid_one(
    tmp_path: Path,
) -> None:
    _skill(tmp_path / "user", "x")
    broken = tmp_path / "project" / "x"
    broken.mkdir(parents=True)
    result = select_skill(_search(tmp_path, "user", "project"), "x", agent="claude")
    assert result.outcome == "invalid" and result.selected is None
    assert str(broken) in " ".join(result.diagnostics)


def test_symlink_in_a_non_following_tier_is_unsupported(tmp_path: Path) -> None:
    import os

    target = _skill(tmp_path / "elsewhere", "real", declared="x")
    (tmp_path / "user").mkdir()
    try:
        os.symlink(target, tmp_path / "user" / "x", target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")
    result = select_skill(_search(tmp_path, "user"), "x", agent="pi")
    assert result.outcome == "unsupported"
    assert "symbolic link" in " ".join(result.diagnostics)


def test_caller_evidence_selects_a_listed_candidate(tmp_path: Path) -> None:
    user = _skill(tmp_path / "user", "x")
    project = _skill(tmp_path / "project", "x")
    search = _search(tmp_path, "user", "project")
    for given in (project, project / "SKILL.md", str(project)):
        result = select_skill(search, "x", agent="codex", selected=given)
        assert result.outcome == "located"
        assert result.selected.path == project
        assert result.provenance == "caller-evidence"
    other = select_skill(search, "x", agent="codex", selected=user)
    assert other.selected.path == user


def test_caller_evidence_overrides_an_unmodeled_shadow_and_blocking_reason(
    tmp_path: Path,
) -> None:
    user = _skill(tmp_path / "user", "x")
    _skill(tmp_path / "admin", "x")
    search = _search(
        tmp_path, "user", unmodeled=(_tier(tmp_path, "admin"),), blocking=("why",)
    )
    result = select_skill(search, "x", agent="codex", selected=user)
    assert result.outcome == "located" and result.selected.path == user


def test_caller_evidence_may_name_a_copy_in_an_unmodeled_location(
    tmp_path: Path,
) -> None:
    _skill(tmp_path / "user", "x")
    admin = _skill(tmp_path / "admin", "x")
    search = _search(tmp_path, "user", unmodeled=(_tier(tmp_path, "admin"),))
    result = select_skill(search, "x", agent="codex", selected=admin)
    assert result.outcome == "located" and result.selected.path == admin


@pytest.mark.parametrize("case", ["outside", "wrong-name", "absent"])
def test_caller_evidence_that_is_not_a_candidate_is_invalid_without_substitution(
    tmp_path: Path, case: str
) -> None:
    _skill(tmp_path / "user", "x")
    if case == "outside":
        given = _skill(tmp_path / "stray", "x")
    elif case == "wrong-name":
        given = _skill(tmp_path / "user", "y")
    else:
        given = tmp_path / "nowhere" / "x"
    result = select_skill(
        _search(tmp_path, "user"), "x", agent="codex", selected=given
    )
    assert result.outcome == "invalid"
    assert result.selected is None
    assert str(given) in " ".join(result.diagnostics)


def test_caller_evidence_naming_a_broken_candidate_is_invalid(tmp_path: Path) -> None:
    broken = tmp_path / "user" / "x"
    broken.mkdir(parents=True)
    result = select_skill(
        _search(tmp_path, "user"), "x", agent="codex", selected=broken
    )
    assert result.outcome == "invalid"
    assert str(broken) in " ".join(result.diagnostics)
