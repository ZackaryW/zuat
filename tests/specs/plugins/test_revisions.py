from dataclasses import FrozenInstanceError, replace

import pytest

from zuat.specs import native


def record(*, agent="claude", scope="user", version="release-candidate+build.7"):
    return native.PluginRecord(
        native.PluginRef(agent, "review@team", scope),
        "review", True, native.PluginActivation.INACTIVE,
        installed_version=version,
    )


def test_exact_revision_identity_is_independent_of_installation():
    user = record()
    project = record(scope="project")
    assert user.revision == project.revision
    assert user.ref != project.ref
    assert user.revision.agent_kind == "claude"
    assert user.revision.plugin_id == "review@team"
    assert user.revision.version == "release-candidate+build.7"
    assert user.revision != record(agent="codex").revision
    assert user.revision != record(version="release-candidate+build.8").revision
    assert user.revision != replace(user, ref=native.PluginRef("claude", "review@other")).revision
    with pytest.raises(FrozenInstanceError):
        user.revision.version = "changed"


def test_missing_version_is_not_an_exact_revision():
    observed = record(version=None)
    assert observed.installed
    assert observed.revision is None


@pytest.mark.parametrize("version", ["", "  ", 7, True, {"version": "1"}])
def test_invalid_native_version_is_rejected_without_coercion(version):
    with pytest.raises(native.InvalidAssetError):
        record(version=version)


def test_contribution_binds_revision_not_display_name():
    first = native.PluginContribution(record().revision, "skill", "review")
    second = native.PluginContribution(record(version="next").revision, "skill", "review")
    assert first != second
    assert first.to_dict() == {
        "revision": {"agent_kind": "claude", "plugin_id": "review@team", "version": "release-candidate+build.7"},
        "kind": "skill", "contribution_id": "review",
    }
