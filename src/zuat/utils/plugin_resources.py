"""Read contribution identifiers, never copy bundled resource contents."""

import json
from fnmatch import fnmatchcase
from pathlib import Path

from zuat.utils.runtime_paths import contained_path


def declared_paths(root: Path, patterns) -> tuple[Path, ...]:
    """Expand explicit resource roots and visible globs without leaving the unit."""
    if not isinstance(patterns, list) or any(
        not isinstance(item, str) for item in patterns
    ):
        raise ValueError("invalid resource patterns")
    selected = []
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        glob = any(char in pattern for char in "*?[")
        candidates = sorted(root.glob(pattern)) if glob else [root / pattern]
        for candidate in candidates:
            if not candidate.exists():
                continue
            if glob and any(
                part.startswith(".") for part in candidate.relative_to(root).parts
            ):
                continue
            selected.append(contained_path(root, candidate))
    return tuple(dict.fromkeys(selected))


def excluded_resource(identifier: str, patterns) -> bool:
    names = (identifier, identifier.rsplit("/", 1)[-1])
    return any(
        fnmatchcase(name, pattern[1:].removeprefix("./"))
        for pattern in patterns
        if pattern.startswith("!")
        for name in names
    )


def json_document(root: Path, relative: str) -> dict:
    path = root / relative
    if not path.exists():
        return {}
    document = json.loads(contained_path(root, path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("invalid plugin resource manifest")
    return document


def skill_resources(root: Path, directories) -> tuple[tuple[str, str], ...]:
    if isinstance(directories, str):
        directories = [directories]
    resources = []
    for relative in directories:
        path = root / relative
        if not path.exists():
            continue
        selected = contained_path(root, path)
        candidates = (
            (selected,) if selected.is_file() else sorted(selected.rglob("SKILL.md"))
        )
        for candidate in candidates:
            safe = contained_path(root, candidate)
            identifier = (
                safe.parent.relative_to(root).as_posix()
                if safe.name == "SKILL.md"
                else safe.relative_to(root).as_posix()
            )
            if identifier == ".":
                identifier = safe.name
            resources.append(("skill", identifier))
    return tuple(resources)


def markdown_resources(root: Path, directories) -> tuple[str, ...]:
    if isinstance(directories, str):
        directories = [directories]
    found = []
    for relative in directories:
        path = root / relative
        if not path.exists():
            continue
        selected = contained_path(root, path)
        files = (selected,) if selected.is_file() else sorted(selected.rglob("*.md"))
        found.extend(
            contained_path(root, file).relative_to(root).as_posix()
            for file in files
            if file.suffix == ".md"
        )
    return tuple(dict.fromkeys(found))


def hook_resources(
    root: Path, relative: str = "hooks/hooks.json"
) -> tuple[tuple[str, str], ...]:
    document = json_document(root, relative)
    return hook_identifiers(document)


def hook_identifiers(document: dict) -> tuple[tuple[str, str], ...]:
    hooks = document.get("hooks", {})
    if not isinstance(hooks, dict) or any(
        not isinstance(entries, list) for entries in hooks.values()
    ):
        raise ValueError("invalid plugin hook inventory")
    return tuple(
        ("hook", f"hooks/{event}/{index}")
        for event, entries in hooks.items()
        for index, _ in enumerate(entries)
    )
