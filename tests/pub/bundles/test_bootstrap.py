import pytest

from zuat import pub


@pytest.mark.parametrize("agent", ["codex", "claude", "pi"])
def test_bootstrap_and_current_use_native_evidence(source, native_service, agent):
    service, managers = native_service
    build = service.build_bundle(source)
    result = service.bootstrap_bundle(build.bundle_id, agents=[agent], trust=True)
    assert result.ok, result
    target = result.targets[0]
    assert target.status == "success"
    assert target.build_revision == build.build_revision
    assert target.installed_version == build.version
    assert target.activation in {"active", "partial"}
    inventory = service.discover_plugins(agent)
    assert inventory.ok, inventory.diagnostics
    assert inventory.plugins[0].ref.native_ref == target.plugin_id
    assert inventory.plugins[0].revision.version == build.version
    before = (
        dict(managers[agent].installed)
        if agent != "pi"
        else list(managers[agent].installed)
    )
    repeated = service.bootstrap_bundle(build.bundle_id, agents=[agent], trust=True)
    assert repeated.targets[0].status == "current"
    assert managers[agent].installed == before
    assert service.get_bundle(build.bundle_id).targets[0].attempt is None


def test_independent_targets_and_trust(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    untrusted = service.bootstrap_bundle(build.bundle_id, agents=["claude"], force=True)
    assert not untrusted.ok
    assert untrusted.targets[0].reason == "source-trust-required"
    assert managers["claude"].installed == {}
    assert managers["claude"].catalogs == {}
    managers["codex"].unavailable = True
    result = service.bootstrap_bundle(
        build.bundle_id, agents=["codex", "kimi", "claude"], trust=True
    )
    assert [t.status for t in result.targets] == [
        "unavailable",
        "unsupported",
        "success",
    ]
    assert managers["claude"].installed


def test_build_only_removal_needs_no_native_calls(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    result = service.remove_bundle(build.bundle_id)
    assert result.operation == "remove"
    assert all(not manager.calls for manager in managers.values())
    with pytest.raises(pub.BundleNotFoundError):
        service.get_bundle(build.bundle_id)


def test_omitted_selection_uses_only_available_supported_agents(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    managers["codex"].unavailable = True

    class Missing:
        def run(self, *args, **kwargs):
            raise FileNotFoundError()

    service._resolver("pi").plugin_adapter().runner = Missing()
    result = service.bootstrap_bundle(build.bundle_id, trust=True)
    assert result.ok, result
    assert [target.agent for target in result.targets] == ["claude"]
    managers["claude"].unavailable = True
    unavailable = service.bootstrap_bundle(build.bundle_id, trust=True)
    assert not unavailable.ok
    assert all(t.status == "unavailable" for t in unavailable.targets)


def test_missing_output_is_unavailable_before_native_changes(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    output = service.resolve_bundle(build.bundle_id, agent="claude")
    (output / ".claude-plugin/plugin.json").unlink()
    result = service.bootstrap_bundle(
        build.bundle_id, agents=["claude"], trust=True, force=True
    )
    assert result.targets[0].status == "unavailable"
    assert result.targets[0].reason == "build-output-unavailable"
    assert not managers["claude"].calls


def test_pi_durable_identity_is_not_an_untrusted_install_route(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    record = service.get_bundle(build.bundle_id)
    result = service.install_plugin(pub.PluginRef("pi", "local/" + record.name))
    assert not result.ok
    assert not managers["pi"].installed
    assert not managers["pi"].calls
