from dataclasses import replace

import pytest

from zuat.specs.native import InvalidAssetError, PluginActivation, PluginRecord, PluginRef


def observed():
    return PluginRecord(PluginRef("claude", "review@team", source="team"), "review", True, PluginActivation.ACTIVE, "1")


def test_plugin_serialization_excludes_transient_native_data(tmp_path):
    item = replace(observed(), native_evidence={
        "installPath": str(tmp_path / "plugin"), "hooks": {"command": "secret-body"},
        "token": "credential", "stdout": "raw-native-output",
    })
    assert item.to_dict() == {
        "ref": {"agent": "claude", "native_ref": "review@team", "scope": "user", "source": "team", "context": None},
        "revision": {"agent_kind": "claude", "plugin_id": "review@team", "version": "1"},
        "name": "review", "installed": True, "activation": "active",
        "installed_version": "1", "available_version": None,
    }


@pytest.mark.parametrize("field,value", [
    ("name", "C:\\private\\plugin"), ("installed_version", "https://user:password@example.org"),
    ("name", "body\nwith\ncommands"), ("installed", "true"),
])
def test_allowed_field_does_not_make_unsafe_value_persistable(field, value):
    with pytest.raises(InvalidAssetError):
        replace(observed(), **{field: value}).to_dict()


@pytest.mark.parametrize("source", ["https://user:password@example.org/plugin", "https://example.org/plugin?token=secret", "C:/private/plugin", "../plugin"])
def test_source_routing_cannot_persist_credentials_or_local_paths(source):
    item = replace(observed(), ref=PluginRef("claude", "review@team", source=source))
    assert item.to_dict()["ref"]["source"] is None


def test_safe_source_routing_is_retained():
    item = replace(observed(), ref=PluginRef("claude", "review@team", source="https://example.org/catalog.git"))
    assert item.to_dict()["ref"]["source"] == "https://example.org/catalog.git"
