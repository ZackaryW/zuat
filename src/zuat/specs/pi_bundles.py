"""Pi package manifest policy, independent of transient install routing."""

import json

from zuat.specs.native import PluginRef


class PiBundleAdapter:
    contract = "pi-bundle-1"

    def initialize(self, native):
        from zuat.utils.bundles.catalog import ensure_native_home

        ensure_native_home(native)

    def reference(self, record):
        return PluginRef("pi", "local/" + record.name)

    def bind(self, native, records, store_root):
        """Restore transient routes from compiler handles, never from Git history.

        This does not turn arbitrary third-party package names into identities.
        A fresh service must explicitly select the same compiler store.
        """
        native.bundle_paths = {
            store_root
            / "builds"
            / record.bundle_id
            / build.build_revision
            / "pi": self.reference(record).native_ref
            for record in records
            for build in record.builds
            if "pi" in build.agents
        }

    def prepare(self, native, record, output, store_root):
        """Only the command receives the output path; manifest identity is durable."""
        return PluginRef("pi", str(output))

    def matches(self, record, observed, outputs):
        # Pi registers a path, so a same-name package elsewhere is never ours.
        return (
            observed.ref == self.reference(record) and observed.runtime_root in outputs
        )

    def render(self, name, version):
        return {
            "package.json": json.dumps(
                {
                    "name": name,
                    "version": version,
                    "description": "Zuat managed skill bundle",
                    "keywords": ["pi-package", "agent-skills"],
                    "files": ["skills"],
                    "pi": {"skills": ["./skills"]},
                },
                sort_keys=True,
            ).encode()
        }
