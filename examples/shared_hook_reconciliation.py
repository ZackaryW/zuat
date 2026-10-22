"""Run with uv run python examples/shared_hook_reconciliation.py; all state is temporary."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from zuat.pub import AssetInput, AssetSelector, Zuat, ZuatRequest


def reconcile(state, asset, *, authorize_receipt_repair=False):
    """A consumer decision table using only supported public APIs."""
    inspected = state.inspect_asset(asset)
    kind = inspected.classification
    if inspected.completeness != "complete" or kind in {"indeterminate", "unsupported"}:
        raise ValueError("; ".join(inspected.diagnostics) or kind)
    if kind == "current":
        return None
    if kind == "outdated":
        result = state.update_asset(asset)
    elif kind == "absent" or (kind == "unowned" and inspected.source_matches):
        result = state.install(ZuatRequest(agents=(asset.agent,), assets=(asset,)))
    elif kind == "conflict" and inspected.owned and inspected.source_matches and authorize_receipt_repair:
        result = state.update_asset(asset, force=True)
    else:
        raise ValueError("Explicit reconciliation is required")
    if not result.ok:
        raise ValueError("; ".join(result.diagnostics))
    assert state.inspect_asset(asset).classification == "current"
    return result


def hooks(command, event="Start"):
    return f'[[hooks]]\nevent = "{event}"\ncommand = "{command}"\n'


def main():
    with TemporaryDirectory(prefix="zuat-hooks-") as temporary:
        base = Path(temporary)
        context = dict(root=base / "registry", home=base / "home",
                       project_root=base / "project", bundle_root=base / "bundles")
        source = base / "reviewer.toml"
        source.write_text(hooks("one"), encoding="utf-8")
        asset = AssetInput("kimi", "hook", source=str(source))
        native = base / "home/.kimi-code/config.toml"
        with Zuat(**context) as state:
            assert reconcile(state, asset).ok  # Verified absence.
            assert reconcile(state, asset) is None  # Current reuse.
            source.write_text(hooks("two"), encoding="utf-8")
            assert reconcile(state, asset).data["native_changed"]  # Outdated update.
            source.write_text(hooks("three"), encoding="utf-8")
            native.write_bytes(source.read_bytes())  # Simulate an external update.
            try:
                reconcile(state, asset)
            except ValueError:
                pass
            else:
                raise AssertionError("Receipt repair needs explicit authorization")
            before = native.read_bytes(), native.stat().st_mtime_ns
            repaired = reconcile(state, asset, authorize_receipt_repair=True)
            assert repaired.data["ownership_changed"] and not repaired.data["native_changed"]
            assert (native.read_bytes(), native.stat().st_mtime_ns) == before
        with Zuat(**context) as state:
            assert reconcile(state, asset) is None
            restored = state.restore_all(repaired.operation_id, AssetSelector("kimi", kind="hook"), force=True)
            assert restored.ok, restored.diagnostics
            assert state.inspect_asset(asset).classification == "conflict"
            assert (native.read_bytes(), native.stat().st_mtime_ns) == before
            adoption_source = base / "stop.toml"
            adoption_source.write_text(hooks("stop", "Stop"), encoding="utf-8")
            native.write_bytes(native.read_bytes() + adoption_source.read_bytes())
            adoption = AssetInput("kimi", "hook", source=str(adoption_source))
            before = native.read_bytes(), native.stat().st_mtime_ns
            assert reconcile(state, adoption).ok  # Exact unowned adoption.
            assert (native.read_bytes(), native.stat().st_mtime_ns) == before
            native.write_bytes(native.read_bytes() + adoption_source.read_bytes())
            for rejected in (adoption, replace(adoption, scope="project")):
                try:
                    reconcile(state, rejected)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unknown or unsupported targets must stop")
        print("Install, reuse, update, explicit receipt repair, reopen, restore, adoption, and rejection verified.")


if __name__ == "__main__":
    main()
