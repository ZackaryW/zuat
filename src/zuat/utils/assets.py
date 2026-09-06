"""Bounded, symlink-safe native asset parsing."""

from __future__ import annotations

import json
import re
import tomllib
from hashlib import sha256
from pathlib import Path

import yaml

from zuat.specs.native import Agent, AssetFile, HookSource, InvalidAssetError, SkillSource

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_FILES = 512
_MAX_BYTES = 16 * 1024 * 1024


def collect_files(path: Path) -> tuple[AssetFile, ...]:
    path = path.resolve(strict=True)
    if path.is_symlink():
        raise InvalidAssetError(f"asset is a symbolic link: {path}")
    candidates = (path,) if path.is_file() else tuple(sorted(path.rglob("*")))
    files: list[AssetFile] = []
    total = 0
    for candidate in candidates:
        if candidate.is_symlink():
            raise InvalidAssetError(f"asset contains a symbolic link: {candidate}")
        if not candidate.is_file():
            continue
        relative = candidate.name if path.is_file() else candidate.relative_to(path).as_posix()
        content = candidate.read_bytes()
        total += len(content)
        files.append(AssetFile(relative, content))
        if len(files) > _MAX_FILES or total > _MAX_BYTES:
            raise InvalidAssetError("asset exceeds the bounded file or byte limit")
    if not files:
        raise InvalidAssetError(f"asset contains no files: {path}")
    return tuple(files)


def fingerprint(files: tuple[AssetFile, ...]) -> str:
    digest = sha256()
    for item in files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.content)
        digest.update(b"\0")
    return digest.hexdigest()


def _frontmatter(content: bytes) -> dict[str, object]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InvalidAssetError("SKILL.md must be UTF-8") from error
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise InvalidAssetError("SKILL.md must begin with YAML frontmatter")
    marker = text.find("\n---", 4)
    if marker < 0:
        raise InvalidAssetError("SKILL.md frontmatter is not terminated")
    try:
        value = yaml.safe_load(text[4:marker])
    except yaml.YAMLError as error:
        raise InvalidAssetError(f"invalid YAML frontmatter: {error}") from error
    if not isinstance(value, dict):
        raise InvalidAssetError("SKILL.md frontmatter must be a mapping")
    return value


def _agents(value: object) -> frozenset[Agent]:
    if value is None:
        return frozenset(Agent)
    if not isinstance(value, list) or not value:
        raise InvalidAssetError("compatible_agents must be a non-empty YAML list")
    try:
        return frozenset(Agent(str(item)) for item in value)
    except ValueError as error:
        raise InvalidAssetError(f"unknown compatible agent: {error}") from error


def load_skill(path: Path) -> SkillSource:
    if path.is_symlink():
        raise InvalidAssetError(f"asset is a symbolic link: {path}")
    document = path / "SKILL.md" if path.is_dir() else path
    if document.name != "SKILL.md" or not document.is_file():
        raise InvalidAssetError(f"skill requires SKILL.md: {path}")
    files = collect_files(path)
    metadata = _frontmatter(document.read_bytes())
    name = metadata.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise InvalidAssetError("skill frontmatter requires a valid name")
    return SkillSource(path.resolve(), name, files, fingerprint(files), _agents(metadata.get("compatible_agents")))


def _hook_source(
    path: Path,
    *,
    agent: Agent,
    format_name: str,
    fragment: object,
    semantic: bool = False,
) -> HookSource:
    files = collect_files(path)
    name = path.stem if path.is_file() else path.name
    if not _NAME.fullmatch(name):
        raise InvalidAssetError("hook requires a valid name")
    return HookSource(
        path.resolve(),
        name,
        format_name,
        fragment,
        files,
        (
            sha256(
                json.dumps(
                    fragment, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            if semantic
            else fingerprint(files)
        ),
        frozenset({agent}),
    )


def load_json_hook(path: Path, *, agent: Agent) -> HookSource:
    if path.is_symlink():
        raise InvalidAssetError(f"hook is a symbolic link: {path}")
    if not path.is_file() or path.suffix != ".json":
        raise InvalidAssetError("JSON hooks must be JSON files")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        fragment = document.get("hooks") if isinstance(document, dict) else None
        if not isinstance(fragment, dict) or not all(
            isinstance(name, str)
            and isinstance(entries, list)
            and all(isinstance(entry, dict) for entry in entries)
            for name, entries in fragment.items()
        ):
            raise InvalidAssetError("hook JSON requires a hooks mapping")
    except (json.JSONDecodeError, UnicodeError) as error:
        raise InvalidAssetError(f"invalid JSON hook: {error}") from error
    return _hook_source(
        path,
        agent=agent,
        format_name="json",
        fragment=fragment,
        semantic=True,
    )


def load_toml_hook(path: Path) -> HookSource:
    if path.is_symlink():
        raise InvalidAssetError(f"hook is a symbolic link: {path}")
    if not path.is_file() or path.suffix != ".toml":
        raise InvalidAssetError("Kimi hooks must be TOML files")
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        fragment = document.get("hooks")
        if not isinstance(fragment, list) or not all(
            isinstance(item, dict) for item in fragment
        ):
            raise InvalidAssetError("Kimi hook TOML requires [[hooks]] entries")
    except (tomllib.TOMLDecodeError, UnicodeError) as error:
        raise InvalidAssetError(f"invalid TOML hook: {error}") from error
    return _hook_source(
        path,
        agent=Agent.KIMI,
        format_name="toml",
        fragment=fragment,
        semantic=True,
    )


def load_pi_extension(path: Path) -> HookSource:
    if path.is_symlink():
        raise InvalidAssetError(f"extension is a symbolic link: {path}")
    if path.is_dir() and not (
        (path / "index.ts").is_file() or (path / "index.js").is_file()
    ):
        raise InvalidAssetError("Pi extension directory requires index.ts or index.js")
    if path.is_file() and path.suffix not in {".js", ".ts"}:
        raise InvalidAssetError("Pi extensions must be JavaScript or TypeScript")
    return _hook_source(
        path, agent=Agent.PI, format_name="extension", fragment=None
    )
