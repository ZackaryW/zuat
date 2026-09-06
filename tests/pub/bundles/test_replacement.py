import pytest


@pytest.mark.parametrize("agent", ["claude", "pi"])
def test_force_is_bounded_and_explicit_retry(source, native_service, agent):
    service, managers = native_service
    manager = managers[agent]
    first = service.build_bundle(source)
    assert service.bootstrap_bundle(first.bundle_id, agents=[agent], trust=True).ok
    manager.fail.add("update")
    (source / "nested/review/data.bin").write_bytes(b"second build")
    second = service.build_bundle(source)
    blocked = service.bootstrap_bundle(second.bundle_id, agents=[agent], trust=True)
    assert not blocked.ok
    assert manager.installed
    manager.fail.add("install")
    failed = service.bootstrap_bundle(
        second.bundle_id, agents=[agent], trust=True, force=True
    )
    assert not failed.ok
    assert not manager.installed
    assert failed.targets[0].reason == "installation-absent"
    assert service.get_bundle(second.bundle_id).targets
    manager.fail.remove("install")
    retried = service.bootstrap_bundle(
        second.bundle_id, agents=[agent], trust=True, force=True
    )
    assert retried.ok, retried
    assert retried.targets[0].build_revision == second.build_revision


def test_foreign_name_is_never_adopted_or_deleted(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)
    adapter = service._resolver("claude").bundle_adapter()
    ref = adapter.reference(service.get_bundle(build.bundle_id))
    managers["claude"].installed[ref.native_ref] = ("foreign", source)
    result = service.bootstrap_bundle(
        build.bundle_id, agents=["claude"], trust=True, force=True
    )
    assert not result.ok
    assert result.targets[0].reason == "foreign-or-ambiguous-target"
    assert managers["claude"].installed[ref.native_ref] == ("foreign", source)


def test_failed_removal_does_not_attempt_reinstall(source, native_service):
    service, managers = native_service
    first = service.build_bundle(source)
    assert service.bootstrap_bundle(first.bundle_id, agents=["claude"], trust=True).ok
    (source / "nested/review/data.bin").write_bytes(b"new")
    second = service.build_bundle(source)
    manager = managers["claude"]
    manager.fail.update({"update", "uninstall"})
    before = dict(manager.installed)
    result = service.bootstrap_bundle(
        second.bundle_id, agents=["claude"], trust=True, force=True
    )
    assert not result.ok
    assert manager.installed == before
    assert result.targets[0].reason == "removal-unverified"


def test_native_neighbor_damage_is_not_reported_as_bundle_success(
    source, native_service
):
    service, managers = native_service
    manager = managers["claude"]
    manager.installed["unrelated@external"] = ("1", source)
    original = manager.run

    def damaging(args, **context):
        result = original(args, **context)
        if args[2] == "install":
            manager.installed["unrelated@external"] = ("2", source)
        return result

    manager.run = damaging
    build = service.build_bundle(source)
    result = service.bootstrap_bundle(build.bundle_id, agents=["claude"], trust=True)
    assert not result.ok
    assert result.targets[0].status == "indeterminate"
    assert service.get_bundle(build.bundle_id).targets[0].status == "indeterminate"
