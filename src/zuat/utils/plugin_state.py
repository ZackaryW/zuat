"""Validation for durable plugin metadata, never native output or payloads."""

from __future__ import annotations

import re
from pathlib import PureWindowsPath
from urllib.parse import urlsplit


def is_direct_source(value: str) -> bool:
    return (
        value.startswith(
            (
                "./",
                "../",
                "/",
                "\\",
                "~",
                "git:",
                "git+",
                "git@",
                "file:",
                "http:",
                "https:",
                "ssh:",
            )
        )
        or PureWindowsPath(value).is_absolute()
    )


def metadata_identifier(value: object) -> str:
    """Accept bounded identifiers, not commands, URLs, or filesystem locations."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("invalid durable plugin identifier")
    candidate = value.removeprefix("npm:")
    if not re.fullmatch(r"[\w@][\w@./+~-]*", candidate, flags=re.ASCII):
        raise ValueError("invalid durable plugin identifier")
    if any(part in {"", ".", ".."} for part in candidate.split("/")):
        raise ValueError("invalid durable plugin identifier")
    return value


def safe_source(value: object) -> str | None:
    """Omit unsafe routing metadata; trust is checked separately at execution."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(ord(char) < 33 for char in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http"}:
            if parsed.hostname and not (
                parsed.username or parsed.password or parsed.query or parsed.fragment
            ):
                return value
            return None
        if parsed.scheme:
            return None
        # Catalog names only; local relative paths are never durable locators.
        if "/" not in value:
            return metadata_identifier(value)
    except ValueError:
        pass
    return None
