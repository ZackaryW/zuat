"""Isolated native manager fixtures with actual rendered files and inventories."""

import json
import shutil
from pathlib import Path

from zuat.utils.process import ProcessResult


class CatalogManager:
    def __init__(self, home, agent):
        self.home = home
        self.agent = agent
        self.catalogs = {}
        self.installed = {}
        self.calls = []
        self.fail = set()
        self.interrupt = None
        self.unavailable = False

    def run(self, args, **context):
        self.calls.append(args)
        if self.unavailable:
            raise FileNotFoundError("missing manager")
        command = args[3] if args[2] == "marketplace" else args[2]
        key = "catalog-" + command if args[2] == "marketplace" else command
        if key == self.interrupt:
            raise KeyboardInterrupt()
        if key in self.fail:
            return ProcessResult(
                args, 1, "", "credential-sentinel source-body-sentinel"
            )
        if args[2] == "marketplace":
            if command == "list":
                entries = [
                    {
                        "name": name,
                        "root": str(root),
                        "source": "directory",
                        "installLocation": str(root),
                    }
                    for name, root in self.catalogs.items()
                ]
                payload = (
                    {"marketplaces": entries} if self.agent == "codex" else entries
                )
                return ProcessResult(args, 0, json.dumps(payload), "")
            if command == "add":
                root = Path(args[4])
                path = root / (
                    ".agents/plugins/marketplace.json"
                    if self.agent == "codex"
                    else ".claude-plugin/marketplace.json"
                )
                catalog = json.loads(path.read_text())
                if catalog["name"] in self.catalogs:
                    return ProcessResult(args, 1, "", "already registered")
                self.catalogs[catalog["name"]] = root
            return ProcessResult(args, 0, "", "")
        if command == "list":
            entries = []
            for identifier, (version, root) in self.installed.items():
                entries.append(
                    {
                        "id": identifier,
                        "pluginId": identifier,
                        "name": identifier.split("@")[0],
                        "scope": "user",
                        "enabled": True,
                        "installed": True,
                        "version": version,
                        "installPath": str(root),
                    }
                )
            return ProcessResult(
                args,
                0,
                json.dumps(
                    {"installed": entries} if self.agent == "codex" else entries
                ),
                "",
            )
        identifier = args[3]
        if command in {"uninstall", "remove"}:
            self.installed.pop(identifier, None)
        elif command in {"install", "add", "update"}:
            name, catalog_name = identifier.rsplit("@", 1)
            root = self.catalogs[catalog_name]
            path = root / (
                ".agents/plugins/marketplace.json"
                if self.agent == "codex"
                else ".claude-plugin/marketplace.json"
            )
            entry = next(
                p for p in json.loads(path.read_text())["plugins"] if p["name"] == name
            )
            relative = (
                entry["source"]["path"]
                if isinstance(entry["source"], dict)
                else entry["source"]
            )
            output = root / relative
            manifest = json.loads(
                (output / f".{self.agent}-plugin/plugin.json").read_text()
            )
            installed = (
                self.home
                / f".{self.agent}/plugins/cache"
                / catalog_name
                / name
                / manifest["version"]
            )
            if not installed.exists():
                shutil.copytree(output, installed)
            self.installed[identifier] = (manifest["version"], installed)
        return ProcessResult(args, 0, "", "")


class PiManager:
    def __init__(self):
        self.installed = []
        self.calls = []
        self.fail = set()

    def run(self, args, **context):
        self.calls.append(args)
        command = args[1]
        if command in self.fail:
            return ProcessResult(args, 1, "", "credential-sentinel")
        if command == "list":
            output = (
                "User packages:\n"
                + "".join(f"  {root}\n    {root}\n" for root in self.installed)
                if self.installed
                else "No packages installed."
            )
            return ProcessResult(args, 0, output, "")
        path = Path(args[2]).resolve()
        if command == "install" and path not in self.installed:
            self.installed.append(path)
        elif command == "remove":
            self.installed.remove(path)
        else:
            return ProcessResult(args, 1, "", "local update unsupported")
        return ProcessResult(args, 0, "", "")
