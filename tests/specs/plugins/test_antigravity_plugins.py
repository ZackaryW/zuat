"""Antigravity plugins are discovered from files only; lifecycle stays with agy."""

import json
from pathlib import Path

import pytest

from zuat.specs.antigravity_plugins import AntigravityPluginAdapter
from zuat.specs.native import (
    Agent,
    PluginActivation,
    PluginOperationError,
    PluginRef,
    Scope,
    UnsupportedNativeOperation,
)
from zuat.utils.ownership import OwnershipStore


def adapter(tmp_path: Path) -> AntigravityPluginAdapter:
    return AntigravityPluginAdapter(
        home=tmp_path / "home", store=OwnershipStore(tmp_path / "state", "antigravity")
    )


def plugin(tmp_path: Path, directory: str, manifest, *, location="plugin.json") -> Path:
    root = tmp_path / "home/.gemini/config/plugins" / directory
    path = root / location
    path.parent.mkdir(parents=True)
    path.write_text(manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8")
    return root


def config(tmp_path: Path, document) -> None:
    path = tmp_path / "home/.gemini/config/config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")


def by_id(records):
    return {record.ref.native_ref: record for record in records}


def test_no_plugin_directory_discovers_nothing(tmp_path):
    native = adapter(tmp_path)

    assert native.discover() == ()
    assert native.discovery_diagnostics == ()


def test_installed_plugin_reports_identity_version_source_and_root(tmp_path):
    root = plugin(tmp_path, "chrome-devtools-plugin", {"name": "chrome-devtools-plugin", "version": "1.10.1"})
    config(tmp_path, {"plugins": {"chrome-devtools-plugin": {"installedFrom": {
        "id": "antigravity-plugins-official/plugin/chrome-devtools-plugin",
        "marketplace": "antigravity-plugins-official", "version": "1.10.1"}}},
        "userSettings": {"unrelated": True}})

    record = adapter(tmp_path).discover()[0]

    assert record.ref == PluginRef(
        Agent.ANTIGRAVITY, "chrome-devtools-plugin", Scope.USER,
        "antigravity-plugins-official/plugin/chrome-devtools-plugin",
    )
    assert record.installed and record.installed_version == "1.10.1"
    assert record.activation is PluginActivation.ACTIVE
    assert record.runtime_root == root


def test_enablement_prefers_config_over_manifest(tmp_path):
    plugin(tmp_path, "off-by-manifest", {"disabled": True})
    plugin(tmp_path, "forced-on", {"disabled": True})
    plugin(tmp_path, "forced-off", {"name": "x"})
    config(tmp_path, {"plugins": {"forced-on": {"enabled": True}, "forced-off": {"enabled": False}}})

    records = by_id(adapter(tmp_path).discover())

    assert records["off-by-manifest"].activation is PluginActivation.INACTIVE
    assert records["forced-on"].activation is PluginActivation.ACTIVE
    assert records["forced-off"].activation is PluginActivation.INACTIVE


def test_missing_version_is_unresolved_without_blocking_discovery(tmp_path):
    plugin(tmp_path, "unversioned", {"name": "unversioned"})
    native = adapter(tmp_path)

    record = native.discover()[0]

    assert record.installed_version is None and record.revision is None
    assert native.discovery_diagnostics == ()


def test_alternate_manifest_locations_and_non_plugins(tmp_path):
    plugin(tmp_path, "nested", {"name": "nested"}, location=".antigravity-plugin/plugin.json")
    (tmp_path / "home/.gemini/config/plugins/not-a-plugin").mkdir(parents=True)

    assert set(by_id(adapter(tmp_path).discover())) == {"nested"}


@pytest.mark.parametrize("broken", ["config", "manifest", "plugins-map"])
def test_malformed_inventory_fails_discovery(tmp_path, broken):
    plugin(tmp_path, "p", "{nope" if broken == "manifest" else {"name": "p"})
    if broken == "config":
        config(tmp_path, "{nope")
    if broken == "plugins-map":
        config(tmp_path, {"plugins": ["p"]})

    with pytest.raises(PluginOperationError):
        adapter(tmp_path).discover()


def test_available_discovery_is_unsupported(tmp_path):
    with pytest.raises(UnsupportedNativeOperation):
        adapter(tmp_path).discover(include_available=True)


def test_contributions_list_skills_and_named_hooks(tmp_path):
    root = plugin(tmp_path, "kit", {"name": "kit"})
    for name in ("a11y", "perf"):
        (root / "skills" / name).mkdir(parents=True)
        (root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    (root / "hooks.json").write_text(json.dumps({"lint": {"PostToolUse": []}, "gate": {"PreToolUse": []}}),
                                     encoding="utf-8")
    native = adapter(tmp_path)

    contributions = native.contributions(native.discover()[0])

    assert set(contributions) == {
        ("skill", "skills/a11y"), ("skill", "skills/perf"), ("hook", "hooks/lint"), ("hook", "hooks/gate"),
    }


def test_lifecycle_is_unsupported_and_changes_nothing(tmp_path):
    root = plugin(tmp_path, "kit", {"name": "kit"})
    before = (root / "plugin.json").read_bytes()
    native = adapter(tmp_path)
    ref = PluginRef(Agent.ANTIGRAVITY, "kit", Scope.USER)

    for operation in (lambda: native.install(ref), lambda: native.update(ref), lambda: native.remove(ref),
                      lambda: native.preflight(ref, "install")):
        with pytest.raises(UnsupportedNativeOperation):
            operation()
    with pytest.raises(UnsupportedNativeOperation):
        native.contextual_ref(PluginRef(Agent.ANTIGRAVITY, "kit", Scope.PROJECT))
    assert (root / "plugin.json").read_bytes() == before
