"""Opaque installation context keys; runtime paths never become journal values."""

import hashlib
import os
from pathlib import Path


def project_context(root: Path | None) -> str | None:
    if root is None:
        return None
    return hashlib.sha256(
        os.path.normcase(str(Path(root).resolve())).encode()
    ).hexdigest()


def locator_context(locator: str) -> str | None:
    parts = locator.split("/")
    if len(parts) > 2 and parts[0] == "contexts":
        return parts[1]
    return None


def contextual_locator(scope: str, locator: str, context: str | None) -> str:
    if scope != "project":
        return locator
    from zuat.specs.interface import ResolutionError

    if not context:
        raise ResolutionError("project assets require an explicit project root")
    existing = locator_context(locator)
    if existing and existing != context:
        raise ResolutionError("asset belongs to another project context")
    return locator if existing else f"contexts/{context}/{locator}"


def native_locator(locator: str) -> str:
    return locator.split("/", 2)[2] if locator_context(locator) else locator


def scope_path(scope: str, context: str | None) -> Path:
    if scope == "project":
        contextual_locator(scope, "assets", context)
        return Path(scope) / "contexts" / context[:16]
    return Path(scope)


def evidence_context(item) -> str | None:
    return locator_context(item.ref.locator) or item.evidence.get("ref", {}).get(
        "context"
    )
