import os
from pathlib import Path

import pytest

from zuat.utils.skill_lookup import SkillTier, scan_tier


def _skill(root: Path, folder: str, declared: str | None = None) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {declared or folder}\n---\nbody\n", encoding="utf-8"
    )
    return path


def _link(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symbolic links unavailable: {error}")


def _tier(root: Path, *, follow: bool = False) -> SkillTier:
    return SkillTier(label="user", scope="user", root=root, follow_symlinks=follow)


def test_absent_or_non_directory_root_has_no_candidates(tmp_path: Path) -> None:
    assert scan_tier(_tier(tmp_path / "absent"), "x").candidates == ()
    (tmp_path / "file").write_text("x")
    assert scan_tier(_tier(tmp_path / "file"), "x").candidates == ()


def test_matches_declared_name_not_folder_name(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    folder = _skill(root, "review-helper", declared="pspec-review")
    _skill(root, "pspec-review", declared="something-else")

    found = scan_tier(_tier(root), "pspec-review")

    assert [candidate.path for candidate in found.candidates] == [folder]
    assert found.candidates[0].root == folder.resolve()
    assert found.candidates[0].tier == "user" and found.candidates[0].scope == "user"
    assert found.invalid == () and found.unsupported == ()


def test_unrelated_broken_skills_do_not_interfere(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    wanted = _skill(root, "wanted")
    (root / "broken").mkdir()
    (root / "broken" / "SKILL.md").write_text("no frontmatter")
    (root / "empty").mkdir()
    (root / "stray.txt").write_text("not a skill")
    (root / ".hidden").mkdir()
    _skill(root, "other")

    found = scan_tier(_tier(root), "wanted")

    assert [candidate.path for candidate in found.candidates] == [wanted]
    assert found.invalid == ()


@pytest.mark.parametrize("breakage", ["no-skill-md", "malformed", "unreadable"])
def test_unverifiable_folder_named_for_the_skill_is_invalid(
    tmp_path: Path, breakage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    broken = root / "wanted"
    broken.mkdir(parents=True)
    if breakage == "malformed":
        (broken / "SKILL.md").write_text("---\ndescription: no name\n---\n")
    if breakage == "unreadable":
        (broken / "SKILL.md").write_text("---\nname: wanted\n---\n")
        original = Path.read_bytes

        def deny(self: Path) -> bytes:
            if self.parent == broken:
                raise PermissionError("denied")
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", deny)

    found = scan_tier(_tier(root), "wanted")

    assert found.candidates == ()
    assert len(found.invalid) == 1
    path, message = found.invalid[0]
    assert path == broken and str(broken) in message


def test_two_copies_in_one_root_are_both_candidates(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    first = _skill(root, "a", declared="dup")
    second = _skill(root, "b", declared="dup")
    found = scan_tier(_tier(root), "dup")
    assert [candidate.path for candidate in found.candidates] == [first, second]


def test_symlinked_skill_is_followed_only_where_the_tier_allows(
    tmp_path: Path,
) -> None:
    target = _skill(tmp_path / "elsewhere", "real", declared="linked")
    root = tmp_path / "skills"
    link = root / "linked"
    _link(target, link)

    followed = scan_tier(_tier(root, follow=True), "linked")
    assert [candidate.path for candidate in followed.candidates] == [link]
    assert followed.candidates[0].root == target.resolve()
    assert followed.candidates[0].via_symlink is True
    assert followed.unsupported == ()

    refused = scan_tier(_tier(root, follow=False), "linked")
    assert refused.candidates == ()
    assert len(refused.unsupported) == 1
    path, message = refused.unsupported[0]
    assert path == link and "symbolic link" in message and str(link) in message


def test_unrelated_symlink_in_a_non_following_tier_is_ignored(tmp_path: Path) -> None:
    target = _skill(tmp_path / "elsewhere", "real", declared="other")
    root = tmp_path / "skills"
    _link(target, root / "other")
    wanted = _skill(root, "wanted")

    found = scan_tier(_tier(root), "wanted")

    assert [candidate.path for candidate in found.candidates] == [wanted]
    assert found.unsupported == ()


def test_dangling_symlink_named_for_the_skill_is_invalid(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    _link(tmp_path / "gone", root / "wanted")
    found = scan_tier(_tier(root, follow=True), "wanted")
    assert found.candidates == ()
    assert [path for path, _ in found.invalid] == [root / "wanted"]
