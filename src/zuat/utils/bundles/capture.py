"""Capture once, render those bytes: never hash one walk and copy another.

Discovery rules adapted from agent-bundler (MIT, ZackaryW, 2026); see NOTICE.
Unlike its compiler, publication never performs an unrestricted copytree.
"""

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import yaml

MAX_FILES = 10_000
MAX_BYTES = 100 * 1024 * 1024
SKIP = frozenset({".git", ".hg", ".svn", "__pycache__"})


def identity(value):
    if not isinstance(value, str):
        raise TypeError("invalid identity")
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not result or len(result) > 64:
        raise ValueError("invalid identity")
    return result


def regular(path: Path, *, directory=False):
    info = path.lstat()
    if (
        info.st_file_attributes & 0x400
        if hasattr(info, "st_file_attributes")
        else stat.S_ISLNK(info.st_mode)
    ):
        raise ValueError("links and reparse points are unsupported")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("special files are unsupported")
    return info


def read_file(path):
    """Bound reads even if a producer grows a file after its metadata check."""
    with path.open("rb") as stream:
        return stream.read(MAX_BYTES + 1)


def tree(root: Path, *, skip=SKIP):
    """Capture bounded regular files and reject observable concurrent edits."""
    regular(root, directory=True)
    files = {}
    stamps = {}
    total = 0
    entries = 0

    def walk():
        nonlocal entries
        for current, directories, names in os.walk(
            root, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)
        ):
            base = Path(current)
            regular(base, directory=True)
            directories[:] = sorted(d for d in directories if d not in skip)
            for name in directories:
                regular(base / name, directory=True)
            entries += len(directories) + len(names)
            if entries > MAX_FILES * 2:
                raise ValueError("too many source entries")
            for name in sorted(names):
                yield base / name

    for path in walk():
        info = regular(path)
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("source escape")
        if info.st_size + total > MAX_BYTES or len(files) >= MAX_FILES:
            raise ValueError("source exceeds capture bounds")
        data = read_file(path)
        after = regular(path)
        stamp = (info.st_ino, info.st_size, info.st_mtime_ns)
        if (
            stamp != (after.st_ino, after.st_size, after.st_mtime_ns)
            or len(data) != info.st_size
        ):
            raise ValueError("source changed during capture")
        total += len(data)
        relative = path.relative_to(root).as_posix()
        files[relative] = data
        stamps[relative] = stamp
    entries = 0
    seen = set()
    for path in walk():
        relative = path.relative_to(root).as_posix()
        seen.add(relative)
        info = regular(path)
        if stamps.get(relative) != (info.st_ino, info.st_size, info.st_mtime_ns):
            raise ValueError("source changed during capture")
    if seen != files.keys():
        raise ValueError("source changed during capture")
    return files


@dataclass(frozen=True)
class CapturedSkills:
    files: dict[str, bytes]
    sources: dict[str, str]


def skills(files):
    """Normalize unique names while keeping skill bodies/support bytes intact."""
    markers = sorted(Path(name) for name in files if Path(name).name == "SKILL.md")
    if not markers:
        raise ValueError("no skills found")
    roots = [p.parent for p in markers]
    if any(a != b and a.is_relative_to(b) for a in roots for b in roots):
        raise ValueError("nested skill payloads are ambiguous")
    names = set()
    output = {}
    sources = {}
    for marker in markers:
        lines = files[marker.as_posix()].decode("utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("missing frontmatter")
        end = next(
            (i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None
        )
        if end is None or end > 512:
            raise ValueError("invalid frontmatter")
        value = yaml.safe_load("\n".join(lines[1:end]))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("description"), str)
            or not value["description"].strip()
        ):
            raise ValueError("missing description")
        name = identity(value.get("name"))
        if name in names:
            raise ValueError("duplicate skill name")
        names.add(name)
        sources[marker.parent.as_posix()] = f"skills/{name}"
        for relative, data in files.items():
            path = Path(relative)
            if path.is_relative_to(marker.parent):
                output[
                    f"skills/{name}/{path.relative_to(marker.parent).as_posix()}"
                ] = data
    return CapturedSkills(output, sources)


def fingerprint(files):
    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        # Length framing prevents path/content boundaries from colliding.
        key = name.encode("utf-8")
        digest.update(len(key).to_bytes(8, "big"))
        digest.update(key)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()
