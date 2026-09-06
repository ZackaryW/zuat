"""Transient runtime-path validation shared by artifact and contribution readers."""

from pathlib import Path


def contained_path(root: Path, candidate: Path) -> Path:
    selected_root = root.resolve(strict=True)
    path = candidate if candidate.is_absolute() else selected_root / candidate
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(selected_root):
        raise ValueError("path escapes installed plugin root")
    return resolved


def installed_root(value: object) -> Path | None:
    if not isinstance(value, (str, Path)):
        return None
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        return None
    return path.resolve()
