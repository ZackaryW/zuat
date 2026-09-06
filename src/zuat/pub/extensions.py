"""Explicit runtime extension contracts, separate from native plugin identity.

Registration holds host code in memory only. Building and installing remain
ordinary public calls; registering an object never invokes its locator.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from zuat.pub.artifact_models import PluginArtifactContext
from zuat.utils.plugin_state import metadata_identifier


class ZuatExtension:
    """Subclass to supply identity and optional installed-artifact location.

    Hosts explicitly instantiate trusted Python code. This contract is not a
    sandbox or loader, and does not provide implicit lifecycle callbacks.
    """

    identifier: str
    version: str

    def locate_artifacts(self, context: PluginArtifactContext) -> tuple[Path, ...]:
        """Return provider-local paths; the default extension supplies none."""
        return ()


@dataclass(frozen=True, slots=True)
class _Registration:
    """Capture routing metadata so later instance edits cannot rebind policy."""

    instance: ZuatExtension
    identifier: str
    version: str
    locate: Callable[[PluginArtifactContext], tuple[Path, ...]]


_defaults: dict[str, _Registration] = {}


def _register(registrations, extension: ZuatExtension) -> None:
    if not isinstance(extension, ZuatExtension):
        raise TypeError("extension must be a ZuatExtension instance")
    identifier = metadata_identifier(getattr(extension, "identifier", None))
    version = metadata_identifier(getattr(extension, "version", None))
    locator = extension.locate_artifacts
    if not callable(locator):
        raise TypeError("artifact locator must be callable")
    selected = _Registration(extension, identifier, version, locator)
    for prior in registrations.values():
        if prior.identifier == identifier or prior.instance is extension:
            if (
                prior.instance is extension
                and prior.identifier == identifier
                and prior.version == version
                and prior.locate == locator
            ):
                return
            raise ValueError(
                "extension is already registered with different identity or code"
            )
    registrations[identifier] = selected


def register_extension(extension: ZuatExtension) -> None:
    """Supply a process default for future services, without native side effects."""
    _register(_defaults, extension)


def _registrations() -> dict[str, _Registration]:
    """Take a service-local snapshot, not a live alias to process defaults."""
    return dict(_defaults)
