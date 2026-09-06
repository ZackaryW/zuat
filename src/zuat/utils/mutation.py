"""Atomic file and staged directory mutation with rollback."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from zuat.specs.native import AssetFile, NativeError


def atomic_write(destination: Path, content: bytes) -> None:
    destination = Path(destination)
    if destination.is_symlink():
        raise NativeError(f"refusing to replace symbolic link: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def replace_tree(destination: Path, files: tuple[AssetFile, ...]) -> None:
    destination = Path(destination)
    if destination.is_symlink():
        raise NativeError(f"refusing to replace symbolic link: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.new-", dir=destination.parent)
    )
    backup: Path | None = None
    try:
        for item in files:
            relative = Path(item.relative_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise NativeError(f"asset path escapes destination: {item.relative_path}")
            assert staged is not None
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content)
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.old-", dir=destination.parent)) / destination.name
            os.replace(destination, backup)
        assert staged is not None
        os.replace(staged, destination)
        staged = None
        if backup is not None:
            shutil.rmtree(backup.parent)
    except BaseException:
        if staged is not None and staged.exists():
            shutil.rmtree(staged)
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
            shutil.rmtree(backup.parent, ignore_errors=True)
        raise


def remove_tree(destination: Path) -> None:
    if destination.is_symlink():
        raise NativeError(f"refusing to remove symbolic link: {destination}")
    if not destination.exists():
        return
    backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.remove-", dir=destination.parent)) / destination.name
    try:
        os.replace(destination, backup)
        shutil.rmtree(backup.parent)
    except BaseException:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise


def mirror_files(destination: Path, files: tuple[AssetFile, ...]) -> None:
    """Write a normalized asset into registry space."""
    replace_tree(destination, files)


def remove_absent(root: Path, names: set[str]) -> None:
    if not root.is_dir() or root.is_symlink():
        return
    for path in root.iterdir():
        if path.name in names or path.name == ".gitkeep" or path.name.endswith(".zuat.json"):
            continue
        if path.is_symlink():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
