"""Disposable homes/projects and filesystem snapshots for read-only lookup tests."""

from __future__ import annotations

import hashlib
from pathlib import Path


def snapshot_tree(root: Path, *, watch: tuple[Path, ...] = ()) -> dict[str, str]:
    """Record every entry under root, plus the presence of explicitly watched paths.

    Directories, files (by content digest) and symlinks (by target) are all
    distinguished, so creating even an empty directory changes the snapshot.
    Watched paths outside the tree, or absent ones, are recorded as such.
    """
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries[key] = f"link:{path.readlink()}"
        elif path.is_dir():
            entries[key] = "dir"
        else:
            entries[key] = "file:" + hashlib.sha256(path.read_bytes()).hexdigest()
    for path in watch:
        entries[f"watch:{path}"] = "present" if path.exists() or path.is_symlink() else "absent"
    return entries


class LookupWorld:
    """An isolated native home and projects with an intentionally absent registry."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.home = base / "home"
        self.home.mkdir()
        self._projects = base / "projects"
        self.registry = base / "registry"
        self.control = base / ".registry.zuat.lock"

    def project(self, name: str) -> Path:
        """A project that looks like a repository root so upward walks stop here."""
        path = self._projects / name
        (path / ".git").mkdir(parents=True, exist_ok=True)
        return path

    def skill(
        self,
        skills_root: Path,
        folder: str,
        *,
        declared: str | None = None,
        body: str = "Procedure.\n",
    ) -> Path:
        """Write a valid skill whose declared name defaults to its folder name."""
        root = skills_root / folder
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(
            f"---\nname: {declared or folder}\ndescription: test skill\n---\n{body}",
            encoding="utf-8",
        )
        return root

    def snapshot(self) -> dict[str, str]:
        return snapshot_tree(self.base, watch=(self.registry, self.control))
