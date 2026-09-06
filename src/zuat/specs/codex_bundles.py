"""Codex plugin manifest policy (not a shared agent-mode switch)."""

import json

from zuat.specs.native import PluginRef
from zuat.utils.bundles.catalog import catalog_name, ensure_catalog, project


class CodexBundleAdapter:
    contract = "codex-bundle-1"

    def initialize(self, native):
        from zuat.utils.bundles.catalog import ensure_native_home

        ensure_native_home(native)

    def reference(self, record):
        catalog = catalog_name(record.bundle_id)
        return PluginRef("codex", f"{record.name}@{catalog}", source=catalog)

    def prepare(self, native, record, output, store_root):
        ref = self.reference(record)
        root = store_root / "catalogs" / record.bundle_id / "codex"
        name = ref.source
        project(
            root,
            output,
            ".agents/plugins/marketplace.json",
            {
                "name": name,
                "interface": {"displayName": "Zuat managed skills"},
                "plugins": [
                    {
                        "name": record.name,
                        "source": {
                            "source": "local",
                            "path": f"./plugins/{output.parent.name}",
                        },
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Developer Tools",
                    }
                ],
            },
        )
        ensure_catalog(
            native,
            root,
            name,
            list_args=("codex", "plugin", "marketplace", "list", "--json"),
            add_args=("codex", "plugin", "marketplace", "add", str(root), "--json"),
            decode=lambda value: [
                (item["name"], item.get("root"))
                for item in json.loads(value)["marketplaces"]
            ],
        )
        return ref

    def matches(self, record, observed, outputs):
        """Catalog identity is stable; native version establishes the build revision."""
        ref = self.reference(record)
        return (
            observed.ref.native_ref == ref.native_ref
            and observed.ref.scope == ref.scope
            and observed.runtime_root is not None
        )

    def render(self, name, version):
        return {
            ".codex-plugin/plugin.json": json.dumps(
                {
                    "name": name,
                    "version": version,
                    "description": "Zuat managed skill bundle",
                    "skills": "./skills/",
                    "author": {"name": "Zuat"},
                    "interface": {
                        "displayName": name,
                        "shortDescription": "Zuat managed skills",
                        "developerName": "Zuat",
                        "category": "Developer Tools",
                    },
                },
                sort_keys=True,
            ).encode()
        }
