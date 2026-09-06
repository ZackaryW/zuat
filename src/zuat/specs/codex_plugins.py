"""Agent-owned native plugin behavior."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from zuat.specs.interface import PluginCapabilities
from zuat.specs.native import (
    Agent,
    PluginOperationError,
    PluginRecord,
    PluginRef,
    Scope,
)
from zuat.utils.plugin_lifecycle import CommandPluginAdapter, activation
from zuat.utils.runtime_paths import contained_path
from zuat.utils.plugin_state import metadata_identifier, is_direct_source


class CodexPluginAdapter(CommandPluginAdapter):
    agent = Agent.CODEX
    scopes = frozenset({Scope.USER})
    capabilities = PluginCapabilities(scopes, scopes, scopes, scopes, available=True)
    environment_variable = "CODEX_HOME"
    config_directory = Path(".codex")

    def contextual_ref(self, ref):
        ref = super().contextual_ref(ref)
        if is_direct_source(ref.native_ref):
            return ref
        if "@" in ref.native_ref:
            if ref.source and ref.source != ref.native_ref.rsplit("@", 1)[1]:
                raise PluginOperationError(
                    "plugin marketplace conflicts with canonical identity"
                )
            return ref
        if not ref.source:
            raise PluginOperationError("plugin requires an explicit marketplace")
        metadata_identifier(ref.source)
        if "/" in ref.source:
            raise PluginOperationError("plugin requires a catalog marketplace name")
        return replace(ref, native_ref=f"{ref.native_ref}@{ref.source}")

    def _find(self, records, ref):
        return super()._find(records, self.contextual_ref(ref))

    def contributions(self, record):
        from zuat.utils.plugin_resources import (
            json_document,
            skill_resources,
            hook_resources,
        )

        if record.runtime_root is None:
            return ()
        manifest = json_document(record.runtime_root, ".codex-plugin/plugin.json")
        from zuat.utils.plugin_resources import hook_identifiers

        declarations = manifest.get("hooks", "hooks/hooks.json")
        if not isinstance(declarations, list):
            declarations = [declarations]
        hooks = []
        for index, declaration in enumerate(declarations):
            found = (
                hook_identifiers(declaration)
                if isinstance(declaration, dict)
                else hook_resources(record.runtime_root, declaration)
            )
            hooks.extend(
                (
                    kind,
                    identifier
                    if len(declarations) == 1
                    else f"declared-{index}/{identifier}",
                )
                for kind, identifier in found
            )
        return (
            *skill_resources(record.runtime_root, manifest.get("skills", ["skills"])),
            *hooks,
        )

    def _installed_root(self, native_id, version):
        if version is None or "@" not in native_id:
            return None
        name, marketplace = native_id.rsplit("@", 1)
        for value in (name, marketplace, version):
            metadata_identifier(value)
            if "/" in value:
                raise ValueError("invalid native cache component")
        cache = self.home / self.config_directory / "plugins/cache"
        selected = cache / marketplace / name / version
        if not selected.is_dir() or selected.is_symlink():
            return None
        return contained_path(cache, selected)

    def discovery_args(self) -> tuple[str, ...]:
        return ("codex", "plugin", "list", "--json")

    def install_args(self, ref: PluginRef) -> tuple[str, ...]:
        return ("codex", "plugin", "add", self.contextual_ref(ref).native_ref, "--json")

    def remove_args(self, ref: PluginRef) -> tuple[str, ...]:
        return (
            "codex",
            "plugin",
            "remove",
            self.contextual_ref(ref).native_ref,
            "--json",
        )

    def update_args(self, ref: PluginRef) -> tuple[tuple[str, ...], ...]:
        marketplace = ref.source or (
            ref.native_ref.rsplit("@", 1)[1] if "@" in ref.native_ref else None
        )
        if not marketplace:
            raise PluginOperationError("Codex update requires an owning marketplace")
        return (
            ("codex", "plugin", "marketplace", "upgrade", marketplace, "--json"),
            self.install_args(ref),
        )

    def decode(self, output: str) -> tuple[PluginRecord, ...]:
        try:
            document = json.loads(output)
            records = []
            for category in ("installed", "available"):
                entries = (
                    document[category]
                    if category == "installed"
                    else document.get(category, [])
                )
                if not isinstance(entries, list):
                    raise ValueError
                for item in entries:
                    installed = category == "installed"
                    if not isinstance(item["pluginId"], str) or not isinstance(
                        item["name"], str
                    ):
                        raise ValueError
                    if installed and type(item.get("installed")) is not bool:
                        raise ValueError
                    runtime_root = (
                        self._installed_root(item["pluginId"], item.get("version"))
                        if installed
                        else None
                    )
                    if installed and runtime_root is None:
                        self.discovery_diagnostics += (
                            "installed plugin has no verified runtime revision",
                        )
                    records.append(
                        PluginRecord(
                            PluginRef(
                                self.agent,
                                item["pluginId"],
                                Scope.USER,
                                item.get("marketplaceName"),
                            ),
                            item["name"],
                            installed and item["installed"],
                            activation(item.get("enabled")),
                            installed_version=item.get("version")
                            if runtime_root
                            else None,
                            available_version=item.get("version")
                            if not installed
                            else item.get("availableVersion"),
                            native_evidence=dict(item),
                            runtime_root=runtime_root,
                        )
                    )
            return tuple(records)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise PluginOperationError(
                "Codex plugin inventory has an unsupported shape"
            ) from error
