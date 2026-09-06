import pytest

from zuat import pub


def test_partial_removal_and_reopen(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    assert service.bootstrap_bundle(
        build.bundle_id, agents=["claude", "pi"], trust=True
    ).ok
    managers["pi"].fail.add("remove")
    result = service.remove_bundle(build.bundle_id)
    assert not result.ok
    assert [t.status for t in result.targets] == ["absent", "failed"]
    assert not managers["claude"].installed
    assert managers["pi"].installed
    before = service.get_bundle(build.bundle_id)
    with pub.Zuat(
        root=service.registry.root, home=service.home, resolvers=service._resolvers
    ) as reopened:
        assert reopened.get_bundle(build.bundle_id) == before
        managers["pi"].fail.clear()
        removed = reopened.remove_bundle(build.bundle_id, agents=["pi"])
        assert removed.ok, removed
        with pytest.raises(pub.BundleNotFoundError):
            reopened.get_bundle(build.bundle_id)


def test_interruption_is_historical_not_automatic_retry(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    managers["claude"].interrupt = "install"
    with pytest.raises(KeyboardInterrupt):
        service.bootstrap_bundle(build.bundle_id, agents=["claude"], trust=True)
    target = service.get_bundle(build.bundle_id).targets[0]
    assert target.status == "indeterminate"
    assert target.attempt == "install"
    before = list(managers["claude"].calls)
    with pub.Zuat(
        root=service.registry.root, home=service.home, resolvers=service._resolvers
    ) as reopened:
        assert reopened.get_bundle(build.bundle_id).targets == (target,)
        assert managers["claude"].calls == before
        managers["claude"].interrupt = None
        result = reopened.bootstrap_bundle(
            build.bundle_id, agents=["claude"], trust=True
        )
        assert result.ok, result


def test_unsupported_selection_does_not_become_an_owned_installation(
    source, native_service
):
    service, managers = native_service
    build = service.build_bundle(source)
    assert not service.bootstrap_bundle(build.bundle_id, agents=["kimi"], trust=True).ok
    service.remove_bundle(build.bundle_id)
    with pytest.raises(pub.BundleNotFoundError):
        service.get_bundle(build.bundle_id)
