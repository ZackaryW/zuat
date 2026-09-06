"""Pointer document mechanics, without copying or archiving native contents."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from zuat.specs.native import PluginRecord, InvalidAssetError
from zuat.utils.mutation import atomic_write


POINTER_FIELDS = frozenset(
    {
        "ref",
        "revision",
        "name",
        "installed",
        "activation",
        "installed_version",
        "available_version",
    }
)


def read_pointer(path: Path) -> PluginRecord:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError
        return PluginRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError) as error:
        raise InvalidAssetError(
            "invalid plugin pointer; use a fresh registry"
        ) from error


def evidence_pointer(evidence: dict) -> PluginRecord:
    return PluginRecord.from_dict(
        {key: value for key, value in evidence.items() if key in POINTER_FIELDS}
    )


def write_pointer(path: Path, record: PluginRecord) -> None:
    atomic_write(
        path, (json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n").encode()
    )


def pointer_fingerprint(record: PluginRecord) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(record.to_dict(), sort_keys=True).encode()
        ).hexdigest()
    )


def clean_evidence(evidence: dict) -> dict:
    """Validate the pointer and retain only domain-owned reference annotations."""
    result = evidence_pointer(evidence).to_dict()
    for key in (
        "native_locator",
        "normalized_path",
        "asset_name",
        "contribution_id",
        "project_context",
    ):
        value = evidence.get(key)
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or not re.fullmatch(r"[\w@./:+~-]{1,1024}", value, re.ASCII)
            or PurePosixPath(value).is_absolute()
            or PureWindowsPath(value).drive
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise InvalidAssetError("invalid plugin reference annotation")
        result[key] = value
    if evidence.get("provider") == "plugin":
        result["provider"] = "plugin"
    if "fingerprint" in evidence:
        result["fingerprint"] = pointer_fingerprint(evidence_pointer(evidence))
    return result
