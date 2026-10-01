from pathlib import Path

import pytest

from zuat.utils.skill_lookup import SkillIdentityError, read_skill_identity


def _skill(tmp_path: Path, text: bytes | str, folder: str = "folder") -> Path:
    root = tmp_path / folder
    root.mkdir()
    data = text.encode() if isinstance(text, str) else text
    (root / "SKILL.md").write_bytes(data)
    return root


def test_declared_name_is_returned_independent_of_folder(tmp_path: Path) -> None:
    root = _skill(tmp_path, "---\nname: declared-name\ndescription: x\n---\nbody\n")
    assert read_skill_identity(root) == "declared-name"


def test_crlf_frontmatter_is_accepted(tmp_path: Path) -> None:
    root = _skill(tmp_path, "---\r\nname: crlf\r\n---\r\nbody\r\n")
    assert read_skill_identity(root) == "crlf"


def test_only_skill_md_is_opened_and_resources_are_never_listed_or_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _skill(tmp_path, "---\nname: lean\n---\n")
    (root / "big.bin").write_bytes(b"\0" * 1024)
    (root / "sub").mkdir()
    (root / "sub" / "more.md").write_text("resource")
    opened: list[Path] = []
    original = Path.read_bytes

    def spy(self: Path) -> bytes:
        opened.append(self)
        return original(self)

    def forbidden(self: Path, *args, **kwargs):
        raise AssertionError(f"resource listing is not allowed: {self}")

    monkeypatch.setattr(Path, "read_bytes", spy)
    monkeypatch.setattr(Path, "iterdir", forbidden)
    monkeypatch.setattr(Path, "rglob", forbidden)

    assert read_skill_identity(root) == "lean"
    assert opened == [root / "SKILL.md"]


@pytest.mark.parametrize(
    "case",
    ["no-directory", "no-skill-md", "skill-md-is-directory"],
)
def test_missing_entrypoint_is_reported_as_missing(tmp_path: Path, case: str) -> None:
    root = tmp_path / "folder"
    if case != "no-directory":
        root.mkdir()
    if case == "skill-md-is-directory":
        (root / "SKILL.md").mkdir()
    with pytest.raises(SkillIdentityError) as error:
        read_skill_identity(root)
    assert error.value.kind == "missing"
    assert str(root) in str(error.value)


def test_unreadable_entrypoint_is_reported_as_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _skill(tmp_path, "---\nname: locked\n---\n")

    def deny(self: Path) -> bytes:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", deny)
    with pytest.raises(SkillIdentityError) as error:
        read_skill_identity(root)
    assert error.value.kind == "unreadable"
    assert str(root) in str(error.value)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        (b"\xff\xfe---\nname: x\n---\n", "UTF-8"),
        ("no frontmatter\n", "frontmatter"),
        ("---\nname: x\n", "not terminated"),
        ("---\nname: [unclosed\n---\n", "YAML"),
        ("---\n- list\n---\n", "mapping"),
        ("---\ndescription: no name\n---\n", "name"),
        ("---\nname: 12\n---\n", "name"),
        ("---\nname: has space\n---\n", "name"),
    ],
)
def test_malformed_metadata_is_reported_as_malformed(
    tmp_path: Path, text: bytes | str, fragment: str
) -> None:
    root = _skill(tmp_path, text)
    with pytest.raises(SkillIdentityError) as error:
        read_skill_identity(root)
    assert error.value.kind == "malformed"
    assert fragment in str(error.value)
    assert str(root / "SKILL.md") in str(error.value)
