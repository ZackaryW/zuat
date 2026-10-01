from pathlib import Path

from zuat.utils.skill_lookup import directory_chain


def test_chain_runs_from_subdirectory_up_to_repository_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "packages" / "web"
    nested.mkdir(parents=True)
    assert directory_chain(nested) == (nested.resolve(), (repo / "packages").resolve(), repo.resolve())


def test_chain_at_repository_root_is_just_the_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert directory_chain(repo) == (repo.resolve(),)


def test_worktree_style_git_file_marks_the_root(tmp_path: Path) -> None:
    repo = tmp_path / "worktree"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: elsewhere\n")
    nested = repo / "a"
    nested.mkdir()
    assert directory_chain(nested) == (nested.resolve(), repo.resolve())


def test_without_repository_only_the_invocation_directory_is_searched(
    tmp_path: Path,
) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    assert directory_chain(inner) == (inner.resolve(),)


def test_nearest_repository_wins_over_an_enclosing_one(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    (outer / ".git").mkdir(parents=True)
    inner = outer / "vendor" / "lib"
    (inner / ".git").mkdir(parents=True)
    deep = inner / "src"
    deep.mkdir()
    assert directory_chain(deep) == (deep.resolve(), inner.resolve())


def test_relative_and_dotted_paths_are_normalized(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "sub"
    sub.mkdir()
    assert directory_chain(sub / ".." / "sub") == (sub.resolve(), repo.resolve())
