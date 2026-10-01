"""Shared contracts for agent-specific observation and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from zuat.specs.native import PluginLifecycleResult, PluginRecord, PluginRef
    from zuat.utils.inspection import TargetInspection
    from zuat.utils.skill_lookup import SkillSearch


@dataclass(frozen=True, slots=True)
class PluginCapabilities:
    discovery_scopes: frozenset[str]
    install_scopes: frozenset[str] = frozenset()
    update_scopes: frozenset[str] = frozenset()
    remove_scopes: frozenset[str] = frozenset()
    available: bool = False
    exact_versions: bool = False

    def supports(self, operation: str, scope: str) -> bool:
        fields = {"discover": self.discovery_scopes, "install": self.install_scopes,
                  "update": self.update_scopes, "remove": self.remove_scopes}
        return scope in fields.get(operation, frozenset())


class BundleAdapter(Protocol):
    """Agent-owned compilation and supported native bootstrap preparation."""

    contract: str

    def render(self, name: str, version: str) -> dict[str, bytes]: ...

    def initialize(self, native: PluginAdapter) -> None: ...

    def reference(self, record) -> PluginRef: ...

    def prepare(self, native: PluginAdapter, record, output: Path, store_root: Path) -> PluginRef: ...

    def matches(self, record, observed: PluginRecord, outputs: tuple[Path, ...]) -> bool: ...


class PluginAdapter(Protocol):
    capabilities: PluginCapabilities
    discovery_diagnostics: tuple[str, ...]

    def discover(self, *, include_available: bool = False) -> tuple[PluginRecord, ...]: ...
    def contributions(self, record: PluginRecord) -> tuple[tuple[str, str], ...]: ...
    def contextual_ref(self, ref: PluginRef) -> PluginRef: ...
    def validate_install(self, ref: PluginRef, *, trust: bool = False) -> None: ...
    def preflight(self, ref: PluginRef, operation: str, *, desired: PluginRecord | None = None) -> None: ...
    def reconcile(self, desired: PluginRecord) -> PluginLifecycleResult: ...
    def install(self, ref: PluginRef, *, trust: bool = False) -> PluginLifecycleResult: ...
    def update(self, ref: PluginRef) -> PluginLifecycleResult: ...
    def remove(self, ref: PluginRef) -> PluginLifecycleResult: ...


class AssetKind(StrEnum):
    SKILL = "skill"
    HOOK = "hook"
    PLUGIN = "plugin"


class ConflictPolicy(StrEnum):
    ABORT = "abort"
    REPLACE = "replace"


class ResolutionError(RuntimeError):
    """An agent tree cannot be safely resolved."""


@dataclass(frozen=True, slots=True)
class Asset:
    agent: str
    kind: AssetKind
    name: str
    path: Path
    scope: str = "user"
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "kind": self.kind.value,
            "name": self.name,
            "path": self.path.as_posix(),
            "scope": self.scope,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    agent: str
    assets: tuple[Asset, ...] = ()
    rejected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "assets": [asset.to_dict() for asset in self.assets],
            "rejected": list(self.rejected),
        }


@dataclass(frozen=True, slots=True)
class PlannedAction:
    operation: str
    asset: Asset

    def to_dict(self) -> dict[str, object]:
        return {"operation": self.operation, "asset": self.asset.to_dict()}


@dataclass(frozen=True, slots=True)
class ResolutionPlan:
    agent: str
    root: Path
    actions: tuple[PlannedAction, ...]
    conflict_policy: ConflictPolicy = ConflictPolicy.ABORT

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "root": str(self.root),
            "conflict_policy": self.conflict_policy.value,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True, slots=True)
class MaterializationRecord:
    agent: str
    operation: str
    kind: str
    name: str
    status: str
    verified: bool
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "operation": self.operation,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "verified": self.verified,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class Materialization:
    agent: str
    state: str
    records: tuple[MaterializationRecord, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.state == "converged" and all(x.verified for x in self.records)

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "state": self.state,
            "verified": self.verified,
            "records": [record.to_dict() for record in self.records],
            "diagnostics": list(self.diagnostics),
        }


@runtime_checkable
class AgentResolver(Protocol):
    agent: str

    def bundle_adapter(self) -> BundleAdapter | None: ...

    def skill_search(self, cwd: Path) -> SkillSearch:
        """Describe, without any writes, where this agent searches for skills from ``cwd``."""
        ...

    def inspect_asset(self, source: Path, kind: AssetKind, scope: str, *, name: str | None = None, locator: str | None = None) -> TargetInspection: ...

    def resolve_asset_source(self, source: Path, kind: AssetKind, scope: str) -> Asset: ...

    def capture_asset(self, target: TargetInspection, output: Path) -> None: ...

    def replace_asset(self, target: TargetInspection) -> None: ...

    def restore_asset_ownership(self, asset: Asset, ownership: dict[str, object] | None) -> None: ...

    def observe(self, registry_root: Path) -> Observation: ...

    def fingerprint(self, path: Path, kind: AssetKind) -> str: ...

    def plan(
        self,
        desired_root: Path,
        *,
        conflict_policy: ConflictPolicy = ConflictPolicy.ABORT,
    ) -> ResolutionPlan: ...

    def preflight(self, plan: ResolutionPlan) -> None: ...

    def plan_uninstall(
        self,
        assets: tuple[Asset, ...],
        *,
        conflict_policy: ConflictPolicy = ConflictPolicy.ABORT,
    ) -> ResolutionPlan: ...

    def materialize(self, plan: ResolutionPlan) -> Materialization: ...
