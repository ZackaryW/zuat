"""Agent-owned native plugin behavior."""

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
from zuat.utils.ownership import OwnershipStore
from zuat.utils.process import ProcessRunner
from zuat.utils.plugin_lifecycle import activation
from zuat.utils.plugin_resources import json_document, skill_resources
from zuat.utils.runtime_paths import installed_root


class KimiPluginAdapter:
    agent = Agent.KIMI
    capabilities = PluginCapabilities(frozenset({Scope.USER}))

    def contributions(self, record):
        if record.runtime_root is None:
            return ()
        manifest = self._manifest(record.runtime_root)
        skills = skill_resources(
            record.runtime_root, manifest.get("skills", ["SKILL.md"])
        )
        hooks = manifest.get("hooks", [])
        if not isinstance(hooks, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("event"), str)
            for item in hooks
        ):
            raise ValueError("invalid Kimi plugin hook inventory")
        return (
            *skills,
            *(
                ("hook", f"hooks/{item['event']}/{index}")
                for index, item in enumerate(hooks)
            ),
        )

    @staticmethod
    def _manifest(root):
        selected = (
            "kimi.plugin.json"
            if (root / "kimi.plugin.json").exists()
            else ".kimi-plugin/plugin.json"
        )
        return json_document(root, selected)

    def __init__(
        self, *, home: Path, store: OwnershipStore, runner: ProcessRunner | None = None
    ) -> None:
        del runner
        self.home = home
        self.store = store
        self.discovery_diagnostics = ()

    def discover(self, *, include_available: bool = False) -> tuple[PluginRecord, ...]:
        self.discovery_diagnostics = ()
        if include_available:
            raise UnsupportedNativeOperation(
                "available plugin discovery is unsupported"
            )
        path = self.home / ".kimi-code" / "plugins" / "installed.json"
        if not path.exists():
            return ()
        if path.is_symlink() or not path.is_file():
            raise PluginOperationError("Kimi plugin inventory is not a regular file")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("version") != 1 or not isinstance(
                document.get("plugins"), list
            ):
                raise ValueError
            if any(
                not isinstance(item, dict) or not isinstance(item.get("id"), str)
                for item in document["plugins"]
            ):
                raise ValueError
            records = []
            for item in document["plugins"]:
                root = installed_root(item.get("root"))
                manifest = self._manifest(root) if root else {}
                if manifest and manifest.get("name") != item["id"]:
                    raise ValueError
                if root is None or not manifest:
                    self.discovery_diagnostics += (
                        "installed plugin has no verified runtime revision",
                    )
                    root = None
                record = PluginRecord(
                    PluginRef(
                        self.agent,
                        item["id"],
                        Scope.USER,
                        item.get("originalSource") or item.get("source"),
                    ),
                    item["id"],
                    True,
                    activation(item.get("enabled")),
                    installed_version=manifest.get("version"),
                    native_evidence=dict(item),
                    runtime_root=root,
                )
                record.to_dict()
                records.append(record)
            return tuple(records)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            InvalidAssetError,
        ) as error:
            raise PluginOperationError(
                "Kimi plugin inventory has an unsupported shape"
            ) from error

    def install(self, ref: PluginRef, *, trust: bool = False) -> PluginLifecycleResult:
        del trust
        raise UnsupportedNativeOperation(
            "Kimi plugin lifecycle has no supported noninteractive manager"
        )

    def remove(self, ref: PluginRef) -> PluginLifecycleResult:
        raise UnsupportedNativeOperation(
            "Kimi plugin lifecycle has no supported noninteractive manager"
        )

    def update(self, ref: PluginRef) -> PluginLifecycleResult:
        raise UnsupportedNativeOperation(
            "Kimi plugin lifecycle has no supported noninteractive manager"
        )

    def preflight(self, ref, operation, *, desired=None):
        raise UnsupportedNativeOperation(
            "Kimi plugin lifecycle has no supported noninteractive manager"
        )

    def reconcile(self, desired):
        self.preflight(desired.ref, "install", desired=desired)

    def contextual_ref(self, ref):
        if (
            ref.agent != self.agent
            or ref.scope != Scope.USER
            or ref.context is not None
        ):
            raise UnsupportedNativeOperation("Kimi supports only user plugin discovery")
        return ref

    def validate_install(self, ref, *, trust=False):
        self.preflight(ref, "install")
