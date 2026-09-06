"""Isolated Python-only lifecycle demonstration; never uses a real agent home."""

from pathlib import Path
from tempfile import TemporaryDirectory

from zuat.pub import AssetInput, AssetSelector, Zuat, ZuatRequest


def main():
    with TemporaryDirectory(prefix="zuat-example-") as temporary:
        base = Path(temporary)
        package = base / "package/reviewer"
        package.mkdir(parents=True)
        document = package / "SKILL.md"
        revision_a = (
            "---\nname: reviewer\ndescription: Review changes\n---\nRevision A.\n"
        )
        document.write_text(revision_a, encoding="utf-8")
        asset = AssetInput("kimi", "skill", scope="project", source=str(package))
        context = {"root": base / "registry", "home": base / "home"}

        # Kimi's local plugin inventory requires no external agent executable.
        # Both projects share this registry and native user home.
        for project in (base / "a", base / "b"):
            with Zuat(**context, project_root=project) as state:
                assert state.install(ZuatRequest(agents=("kimi",), assets=(asset,))).ok

        document.write_text(revision_a + "Revision B.\n", encoding="utf-8")
        with Zuat(**context, project_root=base / "a") as state:
            inspection = state.inspect_asset(asset)
            assert inspection.classification == "outdated" and inspection.owned
            updated = state.update_asset(asset)
            assert updated.ok and updated.data["changed"]

        # Reopen: operation IDs, not Git identifiers, address restoration.
        with Zuat(**context, project_root=base / "a") as state:
            selector = AssetSelector("kimi", kind="skill", scope="project")
            restored = state.restore_all(updated.operation_id, selector, force=True)
            assert restored.ok, restored.diagnostics
            assert state.inspect_asset(asset).classification == "outdated"
            assert state.uninstall_all(selector).ok
            assert state.inspect_asset(asset).classification == "absent"
        with Zuat(**context, project_root=base / "b") as state:
            assert state.inspect_asset(asset).classification == "outdated"
        print(
            "Source-aware update, restart, restore, removal and project isolation verified."
        )


if __name__ == "__main__":
    main()
