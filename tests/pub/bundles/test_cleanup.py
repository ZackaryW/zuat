import pytest

from zuat import pub


def test_purge_removes_only_selected_generated_trees(native_service, source):
    service, managers = native_service
    built = service.build_bundle(source)
    neighbor = service.build_bundle(source, name="neighbor")
    assert service.bootstrap_bundle(
        built.bundle_id, agents=("claude", "pi"), trust=True
    ).ok
    assert service.bootstrap_bundle(
        neighbor.bundle_id, agents=("claude",), trust=True
    ).ok
    selected_path = service.resolve_bundle(built.bundle_id, agent="claude")
    neighbor_path = service.resolve_bundle(neighbor.bundle_id, agent="claude")
    history = service.registry.repo.head.commit.hexsha
    result = service.remove_bundle(built.bundle_id, purge=True)
    assert result.ok and result.outputs_removed
    assert not selected_path.parent.parent.exists()
    assert not (service.home / ".zuat/catalogs" / built.bundle_id).exists()
    assert neighbor_path.is_dir()
    assert (source / "nested/review/SKILL.md").is_file()
    assert service.registry.repo.commit(history)
    assert service.get_bundle(neighbor.bundle_id)
    assert not managers["pi"].installed
    assert len(managers["claude"].installed) == 1
    with pytest.raises(pub.BundleNotFoundError):
        service.get_bundle(built.bundle_id)


def test_failed_native_removal_preserves_all_output(native_service, source):
    service, managers = native_service
    result = service.add_bundle(source, agents=("claude", "pi"), trust=True)
    output = service.resolve_bundle(result.bundle_id, agent="claude")
    managers["pi"].fail.add("remove")
    removed = service.remove_bundle(result.bundle_id, purge=True)
    assert not removed.ok and not removed.outputs_removed
    assert output.is_dir()
    assert service.get_bundle(result.bundle_id)


def test_partial_filter_rejected_before_native_calls(native_service, source):
    service, managers = native_service
    result = service.add_bundle(source, agents=("claude",), trust=True)
    before = list(managers["claude"].calls)
    with pytest.raises(pub.BundleError):
        service.remove_bundle(result.bundle_id, agents=("claude",), purge=True)
    assert managers["claude"].calls == before
    assert managers["claude"].installed


def test_cleanup_rejects_link_without_deleting_any_output(
    native_service, source, tmp_path
):
    service, _ = native_service
    built = service.build_bundle(source)
    output = service.resolve_bundle(built.bundle_id, agent="claude")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("preserve")
    link = output / "foreign"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(pub.BundleCleanupError):
        service.remove_bundle(built.bundle_id, purge=True)
    assert (output / ".claude-plugin/plugin.json").is_file()
    assert (outside / "sentinel").read_text() == "preserve"
    assert service.get_bundle(built.bundle_id)


def test_cleanup_io_failure_retains_absent_record_for_retry(
    native_service, source, monkeypatch
):
    import shutil

    service, _ = native_service
    result = service.add_bundle(source, agents=("claude",), trust=True)
    original = shutil.rmtree

    def fail(*args, **kwargs):
        raise OSError("credential-sentinel")

    with monkeypatch.context() as scoped:
        scoped.setattr(shutil, "rmtree", fail)
        with pytest.raises(pub.BundleCleanupError) as error:
            service.remove_bundle(result.bundle_id, purge=True)
        assert "credential-sentinel" not in str(error.value)
    assert service.get_bundle(result.bundle_id).targets[0].status == "absent"
    assert service.remove_bundle(result.bundle_id, purge=True).outputs_removed
    assert shutil.rmtree is original


def test_default_retains_output_and_module_purge_is_explicit(tmp_path, source):
    context = {"root": tmp_path / "tracking", "home": tmp_path / "home"}
    built = pub.build_bundle(source, **context)
    output = pub.resolve_bundle(built.bundle_id, agent="claude", **context)
    result = pub.remove_bundle(built.bundle_id, **context)
    assert result.ok and not result.outputs_removed
    assert output.is_dir()
    second = pub.build_bundle(source, name="second", **context)
    other = pub.resolve_bundle(second.bundle_id, agent="claude", **context)
    assert pub.remove_bundle(second.bundle_id, purge=True, **context).outputs_removed
    assert not other.exists()
    assert output.is_dir()


def test_purge_retry_rechecks_native_absence(native_service, source, monkeypatch):
    import shutil

    service, managers = native_service
    added = service.add_bundle(source, agents=("claude",), trust=True)
    installed = dict(managers["claude"].installed)
    output = service.resolve_bundle(added.bundle_id, agent="claude")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            shutil, "rmtree", lambda *a, **kw: (_ for _ in ()).throw(OSError())
        )
        with pytest.raises(pub.BundleCleanupError):
            service.remove_bundle(added.bundle_id, purge=True)
    managers["claude"].installed.update(installed)
    with pytest.raises(pub.BundleCleanupError):
        service.remove_bundle(added.bundle_id, purge=True)
    assert output.is_dir()
    assert managers["claude"].installed == installed
    assert service.get_bundle(added.bundle_id)
