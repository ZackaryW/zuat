"""Claude native manifest policy; skills use the native default directory."""

import json

from zuat.specs.native import PluginRef
from zuat.utils.bundles.catalog import catalog_name, ensure_catalog, project


class ClaudeBundleAdapter:
    contract = "claude-bundle-1"

    def initialize(self, native):
        from zuat.utils.bundles.catalog import ensure_native_home

        ensure_native_home(native)

    def reference(self, record):
        catalog = catalog_name(record.bundle_id)
        return PluginRef("claude", f"{record.name}@{catalog}", source=catalog)

    def prepare(self, native, record, output, store_root):
        ref = self.reference(record)
        root = store_root / "catalogs" / record.bundle_id / "claude"
        project(
            root,
            output,
            ".claude-plugin/marketplace.json",
            {
                "name": ref.source,
                "owner": {"name": "Zuat"},
                "plugins": [
                    {"name": record.name, "source": f"./plugins/{output.parent.name}"}
                ],
            },
        )
        ensure_catalog(
            native,
            root,
            ref.source,
            list_args=("claude", "plugin", "marketplace", "list", "--json"),
            add_args=(
                "claude",
                "plugin",
                "marketplace",
                "add",
                str(root),
                "--scope",
                "user",
            ),
            decode=lambda value: [
                (
                    item["name"],
                    item.get("installLocation")
                    if item.get("source") == "directory"
                    else None,
                )
                for item in json.loads(value)
            ],
        )
        return ref

    def matches(self, record, observed, outputs):
        return (
            observed.ref == self.reference(record) and observed.runtime_root is not None
        )

    def render(self, name, version):
        return {
            ".claude-plugin/plugin.json": json.dumps(
                {
                    "name": name,
                    "version": version,
                    "description": "Zuat managed skill bundle",
                },
                sort_keys=True,
            ).encode()
        }
