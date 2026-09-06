import pytest

from tests.pub.bundles.conftest import native_service, source


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_catalog_setup_preserves_unrelated_registration(
    source, native_service, tmp_path, agent
):
    service, managers = native_service
    unrelated = tmp_path / "unrelated-catalog"
    managers[agent].catalogs["unrelated"] = unrelated
    build = service.build_bundle(source)
    first = service.bootstrap_bundle(build.bundle_id, agents=[agent], trust=True)
    assert first.ok, first
    assert managers[agent].catalogs["unrelated"] == unrelated
    (source / "nested/review/data.bin").write_bytes(b"second")
    second = service.build_bundle(source)
    result = service.bootstrap_bundle(
        second.bundle_id, agents=[agent], trust=True, force=True
    )
    assert result.ok, result
    assert managers[agent].catalogs["unrelated"] == unrelated


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_foreign_catalog_source_is_not_replaced(
    source, native_service, tmp_path, agent
):
    service, managers = native_service
    build = service.build_bundle(source)
    record = service.get_bundle(build.bundle_id)
    ref = service._resolver(agent).bundle_adapter().reference(record)
    foreign = tmp_path / "foreign"
    managers[agent].catalogs[ref.source] = foreign
    result = service.bootstrap_bundle(
        build.bundle_id, agents=[agent], trust=True, force=True
    )
    assert not result.ok
    assert managers[agent].catalogs[ref.source] == foreign
    assert not managers[agent].installed


def test_different_bundle_names_share_no_catalog_registration(source, native_service):
    service, managers = native_service
    first = service.build_bundle(source, name="first")
    second = service.build_bundle(source, name="second")
    assert service.bootstrap_bundle(first.bundle_id, agents=["claude"], trust=True).ok
    result = service.bootstrap_bundle(second.bundle_id, agents=["claude"], trust=True)
    assert result.ok, result
    assert service.remove_bundle(first.bundle_id).ok
    assert (
        service.bootstrap_bundle(second.bundle_id, agents=["claude"], trust=True)
        .targets[0]
        .status
        == "current"
    )
