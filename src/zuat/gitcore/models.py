"""Pure Zuat domain values persisted by the private journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class Authority(StrEnum):
    AUTHORITATIVE = "authoritative"
    UNAUTHORITATIVE = "unauthoritative"
    CONFLICTING = "conflicting"
    PARTIAL = "partial"
    INDETERMINATE = "indeterminate"


class OperationKind(StrEnum):
    OBSERVE = "observe"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    UPDATE = "update"
    ARTIFACT_POLICY = "artifact-policy"
    PROFILE_CREATE = "profile-create"
    PROFILE_SWITCH = "profile-switch"
    REVERT = "revert"
    RESTORE = "restore"
    RECOVERY = "recovery"


class OperationOutcome(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    PARTIAL = "partial"
    INDETERMINATE = "indeterminate"
    FAILED = "failed"


def new_operation_id() -> str:
    """Return an opaque domain identifier unrelated to Git object identity."""
    return f"op_{uuid4().hex}"


@dataclass(frozen=True, slots=True)
class AssetRef:
    id: str
    agent: str
    kind: str
    scope: str
    locator: str

    def __post_init__(self) -> None:
        for field_name in ("id", "agent", "kind", "scope", "locator"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"asset {field_name} must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "agent": self.agent,
            "kind": self.kind,
            "scope": self.scope,
            "locator": self.locator,
        }


@dataclass(frozen=True, slots=True)
class AssetEvidence:
    ref: AssetRef
    fingerprint: str | None
    authority: Authority
    present: bool = True
    complete: bool = True
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        evidence = dict(self.evidence)
        if self.ref.kind == "plugin" or evidence.get("provider") == "plugin":
            from zuat.utils.plugin_pointers import clean_evidence
            evidence = clean_evidence(evidence)
        return {
            "asset_ref": self.ref.id,
            "agent": self.ref.agent,
            "kind": self.ref.kind,
            "scope": self.ref.scope,
            "locator": self.ref.locator,
            "fingerprint": self.fingerprint,
            "authority": self.authority.value,
            "present": self.present,
            "complete": self.complete,
            "evidence": evidence,
        }


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    selected: bool = False
    assets: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "selected": self.selected,
            "assets": list(self.assets),
        }


@dataclass(frozen=True, slots=True)
class ProjectedState:
    selected_profile: str
    profiles: tuple[Profile, ...]
    catalog: tuple[AssetRef, ...] = ()
    latest_observation: str | None = None

    def profile(self, name: str) -> Profile:
        try:
            return next(profile for profile in self.profiles if profile.name == name)
        except StopIteration as error:
            raise KeyError(name) from error

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "selected_profile": self.selected_profile,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }
        if self.catalog:
            payload["catalog"] = [item.to_dict() for item in self.catalog]
        if self.latest_observation is not None:
            payload["latest_observation"] = self.latest_observation
        return payload


@dataclass(frozen=True, slots=True)
class JournalEvent:
    operation_id: str
    sequence: int
    kind: OperationKind
    outcome: OperationOutcome
    profile: str | None = None
    forced: bool = False
    before: tuple[AssetEvidence, ...] = ()
    after: tuple[AssetEvidence, ...] = ()
    reverts: str | None = None
    completeness: str = "complete"
    diagnostics: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "outcome": self.outcome.value,
            "profile": self.profile,
            "forced": self.forced,
            "before": [item.to_dict() for item in self.before],
            "after": [item.to_dict() for item in self.after],
            "reverts": self.reverts,
            "completeness": self.completeness,
            "diagnostics": list(self.diagnostics),
            "metadata": dict(self.metadata),
        }
