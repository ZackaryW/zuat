"""Immutable public artifact-extension contracts; resolved paths are transient."""

from dataclasses import dataclass
from pathlib import Path

from zuat.specs.native import PluginRef, PluginRevision


@dataclass(frozen=True, slots=True)
class PluginArtifactContext:
    """Transient installed-revision context passed to a host locator, not journaled."""

    ref: PluginRef
    revision: PluginRevision | None
    runtime_root: Path


@dataclass(frozen=True, slots=True)
class ArtifactStatus:
    """Eligibility evidence; returned paths are runtime values, not durable sources."""

    ref: PluginRef
    identifier: str
    policy: str = "inherit"
    effective: bool = False
    reason: str = "unresolved"
    revision: PluginRevision | None = None
    paths: tuple[Path, ...] = ()

    def to_dict(self):
        return {
            "ref": self.ref.to_dict(),
            "identifier": self.identifier,
            "policy": self.policy,
            "effective": self.effective,
            "reason": self.reason,
            "revision": self.revision.to_dict() if self.revision else None,
            "paths": [str(path) for path in self.paths],
        }
