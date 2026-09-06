"""Semantic JSON/TOML hook-fragment reconciliation."""

from __future__ import annotations

import json
import tomllib
from copy import deepcopy
from pathlib import Path

from zuat.specs.native import InvalidAssetError


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InvalidAssetError(f"invalid JSON document: {path}") from error
    if not isinstance(value, dict):
        raise InvalidAssetError(f"JSON document must be an object: {path}")
    return value


def write_json(value: dict[str, object]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_toml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise InvalidAssetError(f"invalid TOML document: {path}") from error


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    raise InvalidAssetError(f"unsupported TOML value: {type(value).__name__}")


def write_toml(value: dict[str, object]) -> bytes:
    lines: list[str] = []
    tables: list[tuple[str, dict[str, object]]] = []
    arrays: list[tuple[str, list[dict[str, object]]]] = []
    for key, item in value.items():
        if isinstance(item, dict):
            tables.append((key, item))
        elif isinstance(item, list) and item and all(isinstance(entry, dict) for entry in item):
            arrays.append((key, item))
        else:
            lines.append(f"{key} = {_toml_scalar(item)}")
    for key, table in tables:
        if lines:
            lines.append("")
        lines.append(f"[{key}]")
        lines.extend(f"{name} = {_toml_scalar(item)}" for name, item in table.items())
    for key, entries in arrays:
        for entry in entries:
            if lines:
                lines.append("")
            lines.append(f"[[{key}]]")
            lines.extend(f"{name} = {_toml_scalar(item)}" for name, item in entry.items())
    return ("\n".join(lines) + "\n").encode("utf-8")


def contains_fragment(document: dict[str, object], fragment: object, *, key: str = "hooks") -> bool:
    current = document.get(key)
    if isinstance(fragment, dict) and isinstance(current, dict):
        return all(name in current and all(item in current[name] for item in values) for name, values in fragment.items() if isinstance(values, list) and isinstance(current.get(name), list))
    if isinstance(fragment, list) and isinstance(current, list):
        return all(item in current for item in fragment)
    return current == fragment


def add_fragment(document: dict[str, object], fragment: object, *, key: str = "hooks") -> dict[str, object]:
    result = deepcopy(document)
    if isinstance(fragment, dict):
        current = result.setdefault(key, {})
        if not isinstance(current, dict):
            raise InvalidAssetError(f"native {key} value conflicts with managed hooks")
        for name, values in fragment.items():
            if not isinstance(values, list):
                raise InvalidAssetError("hook event values must be lists")
            existing = current.setdefault(name, [])
            if not isinstance(existing, list):
                raise InvalidAssetError(f"native hook event conflicts: {name}")
            existing.extend(item for item in values if item not in existing)
    elif isinstance(fragment, list):
        current = result.setdefault(key, [])
        if not isinstance(current, list):
            raise InvalidAssetError(f"native {key} value conflicts with managed hooks")
        current.extend(item for item in fragment if item not in current)
    else:
        raise InvalidAssetError("unsupported hook fragment")
    return result


def remove_fragment(document: dict[str, object], fragment: object, *, key: str = "hooks") -> dict[str, object]:
    result = deepcopy(document)
    current = result.get(key)
    if isinstance(fragment, dict) and isinstance(current, dict):
        for name, values in fragment.items():
            existing = current.get(name)
            if isinstance(existing, list) and isinstance(values, list):
                current[name] = [item for item in existing if item not in values]
                if not current[name]:
                    del current[name]
        if not current:
            result.pop(key, None)
    elif isinstance(fragment, list) and isinstance(current, list):
        result[key] = [item for item in current if item not in fragment]
        if not result[key]:
            result.pop(key, None)
    return result


def remove_fragment_at_locator(
    document: dict[str, object], locator: str, *, key: str = "hooks"
) -> dict[str, object]:
    """Remove one resolver-observed hook entry without touching its neighbors."""
    result = deepcopy(document)
    parts = locator.split("/")
    if not parts or parts[0] != key:
        raise InvalidAssetError(f"invalid hook locator: {locator}")
    current = result.get(key)
    try:
        if isinstance(current, dict) and len(parts) == 3:
            event = parts[1]
            index = int(parts[2])
            entries = current.get(event)
            if not isinstance(entries, list):
                raise InvalidAssetError(f"hook locator does not exist: {locator}")
            entries.pop(index)
            if not entries:
                del current[event]
            if not current:
                result.pop(key, None)
            return result
        if isinstance(current, list) and len(parts) == 2:
            current.pop(int(parts[1]))
            if not current:
                result.pop(key, None)
            return result
    except (IndexError, ValueError) as error:
        raise InvalidAssetError(f"hook locator does not exist: {locator}") from error
    raise InvalidAssetError(f"hook locator does not exist: {locator}")


def replace_fragment_at_locator(
    document: dict[str, object], locator: str, fragment: object, *, key: str = "hooks"
) -> dict[str, object]:
    """Replace one resolver-observed hook entry without changing its position."""
    result = deepcopy(document)
    parts = locator.split("/")
    if not parts or parts[0] != key:
        raise InvalidAssetError(f"invalid hook locator: {locator}")
    current = result.get(key)
    try:
        if isinstance(current, dict) and len(parts) == 3:
            event = parts[1]
            entries = current.get(event)
            values = fragment.get(event) if isinstance(fragment, dict) else None
            if (
                not isinstance(entries, list)
                or not isinstance(values, list)
                or len(values) != 1
            ):
                raise InvalidAssetError(f"hook locator does not exist: {locator}")
            entries[int(parts[2])] = deepcopy(values[0])
            return result
        if isinstance(current, list) and len(parts) == 2:
            if not isinstance(fragment, list) or len(fragment) != 1:
                raise InvalidAssetError(f"hook locator does not exist: {locator}")
            current[int(parts[1])] = deepcopy(fragment[0])
            return result
    except (IndexError, ValueError) as error:
        raise InvalidAssetError(f"hook locator does not exist: {locator}") from error
    raise InvalidAssetError(f"hook locator does not exist: {locator}")
