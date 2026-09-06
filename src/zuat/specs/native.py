"""Zuat-owned values for native agent assets and plugin lifecycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from zuat.specs.interface import ResolutionError
from zuat.utils.plugin_state import metadata_identifier, safe_source


class Agent(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"
    KIMI = "kimi"
    PI = "pi"


class Scope(StrEnum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"
    MANAGED = "managed"


class NativeError(ResolutionError):
    """A native asset could not be validated or reconciled safely."""


class InvalidAssetError(NativeError):
    """An asset source is malformed, unsafe, or incompatible."""


class NativeConflictError(NativeError):
    """Native state cannot be changed without explicit replacement."""


class UnsupportedNativeOperation(NativeError):
    """An agent does not support the requested native operation."""


class PluginOperationError(NativeError):
    """A plugin command failed or returned ambiguous evidence."""


@dataclass(frozen=True, slots=True)
class AssetFile:
    relative_path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class SkillSource:
    path: Path
    name: str
    files: tuple[AssetFile, ...]
    fingerprint: str
    compatible_agents: frozenset[Agent] = frozenset(Agent)

    @classmethod
    def from_path(cls, path: str | Path) -> SkillSource:
        from zuat.utils.assets import load_skill

        return load_skill(Path(path))


@dataclass(frozen=True, slots=True)
class HookSource:
    path: Path
    name: str
    format: str
    fragment: object
    files: tuple[AssetFile, ...]
    fingerprint: str
    compatible_agents: frozenset[Agent]

class InspectionStatus(StrEnum):
    ABSENT = "absent"
    ADOPTABLE = "adoptable"
    CURRENT = "current"
    OUTDATED = "outdated"
    UNMANAGED = "unmanaged"
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Inspection:
    status: InspectionStatus
    destination: Path
    expected_fingerprint: str | None = None
    actual_fingerprint: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    operation: str
    status: str
    destination: Path | None = None
    before: Inspection | None = None
    after: Inspection | None = None
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.status in {
            "installed",
            "updated",
            "removed",
            "current",
            "adopted",
            "absent",
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "status": self.status,
            "verified": self.verified,
            "destination": str(self.destination) if self.destination else None,
            "evidence": self.evidence,
        }


class PluginActivation(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidAssetError(f"plugin {field_name} must be a nonempty string")
    return value


@dataclass(frozen=True, slots=True)
class PluginRevision:
    agent_kind: Agent
    plugin_id: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_kind", Agent(self.agent_kind))
        _identifier(self.plugin_id, "id")
        _identifier(self.version, "version")

    def to_dict(self) -> dict[str, str]:
        try:
            metadata_identifier(self.plugin_id)
            metadata_identifier(self.version)
        except ValueError as error:
            raise InvalidAssetError(str(error)) from error
        return {"agent_kind": self.agent_kind.value, "plugin_id": self.plugin_id, "version": self.version}


@dataclass(frozen=True, slots=True)
class PluginContribution:
    revision: PluginRevision
    kind: str
    contribution_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.revision, PluginRevision):
            raise InvalidAssetError("contribution requires an exact plugin revision")
        _identifier(self.kind, "contribution kind")
        _identifier(self.contribution_id, "contribution id")

    def to_dict(self) -> dict[str, object]:
        try:
            metadata_identifier(self.kind)
            metadata_identifier(self.contribution_id)
        except ValueError as error:
            raise InvalidAssetError(str(error)) from error
        return {"revision": self.revision.to_dict(), "kind": self.kind, "contribution_id": self.contribution_id}


@dataclass(frozen=True, slots=True)
class PluginRef:
    agent: Agent
    native_ref: str
    scope: Scope | str = Scope.USER
    source: str | None = None
    context: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent", Agent(self.agent))
        object.__setattr__(self, "scope", Scope(self.scope))
        _identifier(self.native_ref, "native reference")
        if self.context is not None and (len(self.context) != 64 or any(char not in "0123456789abcdef" for char in self.context)):
            raise InvalidAssetError("invalid plugin installation context")

    def to_dict(self) -> dict[str, object]:
        try:
            metadata_identifier(self.native_ref)
        except ValueError as error:
            raise InvalidAssetError(str(error)) from error
        return {
            "agent": self.agent.value,
            "native_ref": self.native_ref,
            "scope": self.scope.value,
            "source": safe_source(self.source),
            "context": self.context,
        }


@dataclass(frozen=True, slots=True)
class PluginRecord:
    ref: PluginRef
    name: str
    installed: bool
    activation: PluginActivation
    installed_version: str | None = None
    available_version: str | None = None
    native_evidence: dict[str, object] = field(default_factory=dict)
    runtime_root: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        for version in (self.installed_version, self.available_version):
            if version is not None:
                _identifier(version, "version")
        object.__setattr__(self, "activation", PluginActivation(self.activation))

    @property
    def revision(self) -> PluginRevision | None:
        if not self.installed or self.installed_version is None:
            return None
        return PluginRevision(self.ref.agent, self.ref.native_ref, self.installed_version)

    def to_dict(self) -> dict[str, object]:
        try:
            metadata_identifier(self.name)
            if self.available_version is not None:
                metadata_identifier(self.available_version)
        except ValueError as error:
            raise InvalidAssetError(str(error)) from error
        if type(self.installed) is not bool:
            raise InvalidAssetError("plugin installed state must be boolean")
        return {
            "ref": self.ref.to_dict(),
            "revision": self.revision.to_dict() if self.revision else None,
            "name": self.name,
            "installed": self.installed,
            "activation": self.activation.value,
            "installed_version": self.installed_version,
            "available_version": self.available_version,
        }

    @classmethod
    def from_dict(cls, value: object) -> PluginRecord:
        try:
            required = {"ref", "revision", "name", "installed", "activation", "installed_version", "available_version"}
            if not isinstance(value, dict) or set(value) != required:
                raise ValueError
            ref = value["ref"]
            if not isinstance(ref, dict) or set(ref) != {"agent", "native_ref", "scope", "source", "context"}:
                raise ValueError
            record = cls(PluginRef(**ref), value["name"], value["installed"], value["activation"], value["installed_version"], value["available_version"])
            if record.to_dict() != value:
                raise ValueError
            return record
        except (KeyError, TypeError, ValueError, InvalidAssetError) as error:
            raise InvalidAssetError("incompatible plugin pointer; use a fresh registry") from error


@dataclass(frozen=True, slots=True)
class PluginLifecycleResult:
    operation: str
    ref: PluginRef
    status: str
    before: PluginRecord | None = None
    after: PluginRecord | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        if self.status not in {"installed", "updated", "removed", "current"}:
            return False
        if self.operation == "remove":
            return self.after is None or not self.after.installed
        return bool(self.after and self.after.installed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "verified": self.verified,
            "ref": self.ref.to_dict(),
            "before": self.before.to_dict() if self.before else None,
            "after": self.after.to_dict() if self.after else None,
            "diagnostics": list(self.diagnostics),
        }
