from pathlib import Path

from tests.pub.lookup.helpers import LookupWorld, snapshot_tree


def test_snapshot_is_equal_when_nothing_changes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("x")
    assert snapshot_tree(tmp_path) == snapshot_tree(tmp_path)


def test_snapshot_detects_created_file_directory_and_content_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "f.txt").write_text("x")
    before = snapshot_tree(tmp_path)

    (tmp_path / "new.txt").write_text("y")
    assert snapshot_tree(tmp_path) != before

    (tmp_path / "new.txt").unlink()
    assert snapshot_tree(tmp_path) == before

    (tmp_path / "empty-dir").mkdir()
    assert snapshot_tree(tmp_path) != before

    (tmp_path / "empty-dir").rmdir()
    (tmp_path / "f.txt").write_text("changed")
    assert snapshot_tree(tmp_path) != before


def test_snapshot_records_absent_paths_so_their_creation_is_detected(
    tmp_path: Path,
) -> None:
    absent = tmp_path / "registry"
    before = snapshot_tree(tmp_path, watch=(absent,))
    absent.mkdir()
    assert snapshot_tree(tmp_path, watch=(absent,)) != before


def test_world_provides_isolated_home_projects_and_absent_registry(
    tmp_path: Path,
) -> None:
    world = LookupWorld(tmp_path)
    assert world.home.is_dir()
    assert world.project("a").is_dir() and world.project("b").is_dir()
    assert world.project("a") != world.project("b")
    assert not world.registry.exists()
    assert not world.control.exists()
    assert world.registry not in world.home.parents


def test_world_writes_skill_with_declared_name_distinct_from_folder(
    tmp_path: Path,
) -> None:
    world = LookupWorld(tmp_path)
    root = world.skill(world.home / ".claude" / "skills", "folder", declared="declared")
    text = (root / "SKILL.md").read_text()
    assert root.name == "folder"
    assert "name: declared" in text
