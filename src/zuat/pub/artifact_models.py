"""Immutable public artifact-extension contracts; resolved paths are transient."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from zuat.specs.native import PluginRef, PluginRevision
from zuat.utils.plugin_state import metadata_identifier


@dataclass(frozen=True, slots=True)
class PluginArtifactContext:
    """Transient installed-revision context passed to a host locator, not journaled."""

    ref: PluginRef
    revision: PluginRevision | None
    runtime_root: Path


@dataclass(frozen=True, slots=True)
class ArtifactExtension:
    """Host locator code registered at runtime, outside the plugin revision trail."""

    identifier: str
    version: str
    locate: Callable[[PluginArtifactContext], tuple[Path, ...]]

    def __post_init__(self):
        metadata_identifier(self.identifier)
        metadata_identifier(self.version)
        if not callable(self.locate):
            raise ValueError("artifact locator must be callable")


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
