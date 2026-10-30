"""Antigravity plugin discovery from its config files; lifecycle stays with agy."""

from __future__ import annotations

import json
from pathlib import Path

from zuat.specs.interface import PluginCapabilities
from zuat.specs.native import (
    Agent,
    InvalidAssetError,
    PluginLifecycleResult,
    PluginOperationError,
    PluginRecord,
    PluginRef,
    Scope,
    UnsupportedNativeOperation,
)
from zuat.utils.documents import read_keyed_json
from zuat.utils.ownership import OwnershipStore
from zuat.utils.plugin_lifecycle import activation
from zuat.utils.plugin_resources import skill_resources
from zuat.utils.process import ProcessRunner

# The plugin directory is the marker; agy also accepts these nested manifests.
MANIFESTS = ("plugin.json", ".antigravity-plugin/plugin.json", ".gemini-plugin/plugin.json")
UNSUPPORTED = "Antigravity plugin lifecycle is not managed by Zuat; use agy plugin"


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PluginOperationError(f"Antigravity plugin inventory is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise PluginOperationError(f"Antigravity plugin inventory has an unsupported shape: {path}")
    return value


class AntigravityPluginAdapter:
    agent = Agent.ANTIGRAVITY
    capabilities = PluginCapabilities(frozenset({Scope.USER}))

    def __init__(
        self, *, home: Path, store: OwnershipStore, runner: ProcessRunner | None = None
    ) -> None:
        del runner
        self.home = home
        self.store = store
        self.root = home / ".gemini" / "config"
        self.discovery_diagnostics = ()

    def _settings(self) -> dict:
        path = self.root / "config.json"
        if not path.exists():
            return {}
        plugins = _object(path).get("plugins", {})
        if not isinstance(plugins, dict) or any(not isinstance(item, dict) for item in plugins.values()):
            raise PluginOperationError("Antigravity config.json plugins must map names to objects")
        return plugins

    def discover(self, *, include_available: bool = False) -> tuple[PluginRecord, ...]:
        """Installed user plugins; ``config.json`` enablement overrides the manifest's."""
        self.discovery_diagnostics = ()
        if include_available:
            raise UnsupportedNativeOperation("available plugin discovery is unsupported")
        directory = self.root / "plugins"
        settings = self._settings()
        if not directory.is_dir():
            return ()
        records = []
        for root in sorted(directory.iterdir(), key=lambda value: value.name):
            if root.name.startswith(".") or not root.is_dir() or root.is_symlink():
                continue
            manifest_path = next((root / name for name in MANIFESTS if (root / name).is_file()), None)
            if manifest_path is None:
                continue
            manifest = _object(manifest_path)
            setting = settings.get(root.name, {})
            enabled = setting.get("enabled")
            if not isinstance(enabled, bool):
                enabled = not manifest.get("disabled", False)
            installed_from = setting.get("installedFrom")
            source = installed_from.get("id") if isinstance(installed_from, dict) else None
            version = manifest.get("version")
            try:
                record = PluginRecord(
                    PluginRef(self.agent, root.name, Scope.USER, source if isinstance(source, str) else None),
                    root.name,
                    True,
                    activation(enabled),
                    installed_version=version if isinstance(version, str) else None,
                    native_evidence={"manifest": manifest_path.relative_to(root).as_posix(), **setting},
                    runtime_root=root,
                )
                record.to_dict()
            except (InvalidAssetError, TypeError, ValueError) as error:
                raise PluginOperationError(f"Antigravity plugin has invalid identity: {root.name}") from error
            records.append(record)
        return tuple(records)

    def contributions(self, record):
        if record.runtime_root is None:
            return ()
        hooks = read_keyed_json(record.runtime_root / "hooks.json")
        return (
            *skill_resources(record.runtime_root, ["skills"]),
            *(("hook", f"hooks/{name}") for name in hooks),
        )

    def install(self, ref: PluginRef, *, trust: bool = False) -> PluginLifecycleResult:
        raise UnsupportedNativeOperation(UNSUPPORTED)

    def update(self, ref: PluginRef) -> PluginLifecycleResult:
        raise UnsupportedNativeOperation(UNSUPPORTED)

    def remove(self, ref: PluginRef) -> PluginLifecycleResult:
        raise UnsupportedNativeOperation(UNSUPPORTED)

    def preflight(self, ref, operation, *, desired=None):
        raise UnsupportedNativeOperation(UNSUPPORTED)

    def reconcile(self, desired):
        self.preflight(desired.ref, "install", desired=desired)

    def contextual_ref(self, ref):
        if ref.agent != self.agent or ref.scope != Scope.USER or ref.context is not None:
            raise UnsupportedNativeOperation("Antigravity supports only user plugin discovery")
        return ref

    def validate_install(self, ref, *, trust=False):
        self.preflight(ref, "install")
