"""Agent-neutral mechanics for internal payload projections.

These are not native installers. Callers validate and scope the internal paths;
resolvers remain responsible for native destinations, safety, and semantics."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from zuat.specs.interface import (
    Asset,
)


def copy_asset(source: Path, target: Path) -> None:
    """Replace one already-validated internal projection, not a native destination.

    Callers supply a temporary/profile path. Native path safety and mutation
    belong to resolvers; this helper deliberately does not choose destinations.
    """
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def write_asset_metadata(target: Path, ref, *, targeted: bool = False) -> None:
    """Carry native identity beside a projection instead of guessing from filenames.

    Targeted marks semantic recovery input; it does not bypass resolver preflight.
    """
    metadata = target.with_name(f"{target.name}.zuat.json")
    metadata.write_text(
        json.dumps(
            {
                "scope": ref.scope,
                "native_locator": ref.locator,
                **({"targeted": True} if targeted else {}),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def asset_locator(asset: Asset) -> str:
    """Prefer resolver identity over the display/storage path when available."""
    native = asset.evidence.get("native_locator")
    if isinstance(native, str) and native:
        return native
    value = asset.path.as_posix().strip("/")
    prefix = f"{asset.agent}/"
    return value[len(prefix) :] if value.startswith(prefix) else value


def asset_fingerprint(path: Path, asset: Asset) -> str | None:
    """Prefer native semantic evidence; hash the projection only as a fallback."""
    supplied = asset.evidence.get("fingerprint")
    if isinstance(supplied, str) and supplied:
        return supplied if ":" in supplied else f"sha256:{supplied}"
    return fingerprint_path(path) if path.exists() else None


def fingerprint_path(path: Path) -> str:
    """Hash relative names and bytes so renames and removed files change identity."""
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    else:
        for item in sorted(
            candidate for candidate in path.rglob("*") if candidate.is_file()
        ):
            digest.update(item.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(item.read_bytes())
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"
