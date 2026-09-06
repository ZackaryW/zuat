"""Agent-owned native plugin behavior."""

from __future__ import annotations

import json
from pathlib import Path

from zuat.specs.interface import PluginCapabilities
from zuat.specs.native import (
    Agent,
    PluginActivation,
    PluginOperationError,
    PluginRecord,
    PluginRef,
    Scope,
)
from zuat.utils.plugin_lifecycle import CommandPluginAdapter, activation
from zuat.utils.runtime_paths import installed_root


class ClaudePluginAdapter(CommandPluginAdapter):
    agent = Agent.CLAUDE
    scopes = frozenset({Scope.USER, Scope.PROJECT, Scope.LOCAL, Scope.MANAGED})
    mutable_scopes = scopes - {Scope.MANAGED}
    capabilities = PluginCapabilities(
        scopes, mutable_scopes, scopes, mutable_scopes, available=True
    )
    environment_variable = "CLAUDE_CONFIG_DIR"
    config_directory = Path(".claude")

    def contributions(self, record):
        from zuat.utils.plugin_resources import (
            json_document,
            skill_resources,
            hook_resources,
        )

        if record.runtime_root is None:
            return ()
        manifest = json_document(record.runtime_root, ".claude-plugin/plugin.json")
        skills = (
            *skill_resources(record.runtime_root, ["skills"]),
            *skill_resources(record.runtime_root, manifest.get("skills", [])),
        )
        from zuat.utils.plugin_resources import markdown_resources

        skills += tuple(
            ("skill", identifier)
            for identifier in markdown_resources(
                record.runtime_root, manifest.get("commands", ["commands"])
            )
        )
        hooks = list(hook_resources(record.runtime_root))
        declared = manifest.get("hooks", [])
        if isinstance(declared, (str, dict)):
            declared = [declared]
        for index, item in enumerate(declared):
            if isinstance(item, str):
                hooks.extend(
                    (kind, f"declared-{index}/{identifier}")
                    for kind, identifier in hook_resources(record.runtime_root, item)
                )
            elif isinstance(item, dict):
                from zuat.utils.plugin_resources import hook_identifiers

                hooks.extend(
                    (kind, f"declared-{index}/{identifier}")
                    for kind, identifier in hook_identifiers(item)
                )
            else:
                raise ValueError("invalid plugin hook declaration")
        return tuple(dict.fromkeys((*skills, *hooks)))

    def discovery_args(self) -> tuple[str, ...]:
        return ("claude", "plugin", "list", "--json")

    def install_args(self, ref: PluginRef) -> tuple[str, ...]:
        return (
            "claude",
            "plugin",
            "install",
            ref.native_ref,
            "--scope",
            ref.scope.value,
        )

    def remove_args(self, ref: PluginRef) -> tuple[str, ...]:
        return (
            "claude",
            "plugin",
            "uninstall",
            ref.native_ref,
            "--scope",
            ref.scope.value,
            "--yes",
        )

    def update_args(self, ref: PluginRef) -> tuple[tuple[str, ...], ...]:
        return (
            ("claude", "plugin", "update", ref.native_ref, "--scope", ref.scope.value),
        )

    def decode(self, output: str) -> tuple[PluginRecord, ...]:
        try:
            document = json.loads(output)
            entries = document if isinstance(document, list) else document["installed"]
            records = []
            for item in entries:
                native_ref = item["id"]
                if not isinstance(native_ref, str):
                    raise ValueError
                source = native_ref.rsplit("@", 1)[1] if "@" in native_ref else None
                records.append(
                    PluginRecord(
                        PluginRef(
                            self.agent, native_ref, Scope(str(item["scope"])), source
                        ),
                        native_ref.rsplit("@", 1)[0],
                        True,
                        activation(item.get("enabled")),
                        installed_version=item.get("version"),
                        available_version=item.get("availableVersion"),
                        native_evidence=dict(item),
                        runtime_root=installed_root(item.get("installPath")),
                    )
                )
            if isinstance(document, dict):
                for item in document.get("available", []):
                    native_ref = item["id"]
                    if not isinstance(native_ref, str):
                        raise ValueError
                    records.append(
                        PluginRecord(
                            PluginRef(self.agent, native_ref),
                            item.get("name", native_ref.split("@")[0]),
                            False,
                            PluginActivation.UNKNOWN,
                            available_version=item.get("version"),
                        )
                    )
            return tuple(records)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise PluginOperationError(
                "Claude plugin inventory has an unsupported shape"
            ) from error
