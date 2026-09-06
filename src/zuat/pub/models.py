"""Stable public request and result values with no adapter dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from zuat.gitcore.models import (
    AssetEvidence,
    AssetRef,
    Authority,
    JournalEvent,
    Profile,
)
from zuat.specs.interface import Materialization
from zuat.specs.native import PluginRecord

SUPPORTED_AGENTS = ("codex", "claude", "kimi", "pi")
SUPPORTED_KINDS = ("skill", "hook", "plugin")


class OperationStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AssetInspection:
    """Source-relative native facts, not permission to adopt or replace a target.

    Keep source equality separate from owned-baseline evidence: identical foreign
    bytes are still unowned, and local edits remain conflicting even when they
    match the supplied source. Missing fingerprints mean unresolved evidence,
    not an invented empty asset. Update must inspect again before mutation.
    """

    classification: str
    agent: str
    kind: str
    name: str | None
    scope: str
    asset_ref: AssetRef | None = None
    source_fingerprint: str | None = None
    observed_fingerprint: str | None = None
    baseline_fingerprint: str | None = None
    owned: bool = False
    ownership_evidence: tuple[str, ...] = ()
    source_matches: bool | None = None
    completeness: str = "complete"
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssetSelector:
    """Small, explicit filter for observed agent assets."""

    agent: str
    kind: str | None = None
    scope: str | None = None
    authority: Authority | None = None
    present: bool | None = True
    provider: str | None = None
    plugin_id: str | None = None
    version: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.agent not in SUPPORTED_AGENTS:
            raise ValueError(f"unsupported agent: {self.agent}")
        if self.kind is not None and self.kind not in SUPPORTED_KINDS:
            raise ValueError(f"unsupported asset kind: {self.kind}")
        if self.authority is not None:
            object.__setattr__(self, "authority", Authority(self.authority))
        if self.provider not in {None, "global", "plugin"}:
            raise ValueError("unsupported provider")

    def matches(self, item: AssetEvidence) -> bool:
        return (
            item.ref.agent == self.agent
            and (self.kind is None or item.ref.kind == self.kind)
            and (self.scope is None or item.ref.scope == self.scope)
            and (self.authority is None or item.authority is self.authority)
            and (self.present is None or item.present is self.present)
            and (
                self.provider is None
                or self.provider
                == item.evidence.get(
                    "provider", "plugin" if item.ref.kind == "plugin" else "global"
                )
            )
            and (
                self.plugin_id is None
                or item.evidence.get("ref", {}).get("native_ref") == self.plugin_id
            )
            and (
                self.version is None
                or (item.evidence.get("revision") or {}).get("version") == self.version
            )
            and (self.name is None or item.evidence.get("asset_name") == self.name)
        )


@dataclass(frozen=True, slots=True)
class AssetInput:
    """A caller's intended source and installation identity.

    The selected agent resolver validates names, scope, and locators. Source-aware
    inspection/update require a supplied reference to agree with that identity;
    it cannot override project context.
    This value carries a runtime source path, not a durable plugin-source record.
    """

    agent: str
    kind: str
    scope: str = "user"
    name: str | None = None
    locator: str | None = None
    source: str | None = None
    asset_ref: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "kind": self.kind,
            "scope": self.scope,
            "name": self.name,
            "locator": self.locator,
            "source": self.source,
            "asset_ref": self.asset_ref,
        }


@dataclass(frozen=True, slots=True)
class ZuatRequest:
    """Explicit operation selection; force never bypasses native safety checks."""

    agents: tuple[str, ...] = SUPPORTED_AGENTS
    assets: tuple[AssetInput, ...] = ()
    asset_refs: tuple[str, ...] = ()
    profile: str | None = None
    operation_id: str | None = None
    force: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "agents": list(self.agents),
            "assets": [asset.to_dict() for asset in self.assets],
            "asset_refs": list(self.asset_refs),
            "profile": self.profile,
            "operation_id": self.operation_id,
            "force": self.force,
        }


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Public outcome with domain evidence and an optional opaque operation ID.

    Partial means convergence was not established. An absent operation ID can
    mean a no-op or rejection before journaling, so callers must inspect status
    rather than infer success from the presence of a history entry.
    """

    operation: str
    status: OperationStatus
    operation_id: str | None = None
    profile: str | None = None
    completeness: str = "complete"
    assets: tuple[AssetEvidence, ...] = ()
    profiles: tuple[Profile, ...] = ()
    materializations: tuple[Materialization, ...] = ()
    history: tuple[JournalEvent, ...] = ()
    diagnostics: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    plugins: tuple[PluginRecord, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status is OperationStatus.SUCCESS

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "status": self.status.value,
            "ok": self.ok,
            "operation_id": self.operation_id,
            "profile": self.profile,
            "completeness": self.completeness,
            "assets": [item.to_dict() for item in self.assets],
            "profiles": [item.to_dict() for item in self.profiles],
            "materializations": [item.to_dict() for item in self.materializations],
            "history": [item.to_dict() for item in self.history],
            "diagnostics": list(self.diagnostics),
            "data": dict(self.data),
            "plugins": [item.to_dict() for item in self.plugins],
        }
