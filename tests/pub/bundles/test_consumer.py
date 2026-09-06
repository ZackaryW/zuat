from zuat import pub


def test_explicit_extension_workflow_uses_only_public_bundle_handles(
    source, native_service, tmp_path
):
    service, managers = native_service

    class Host(pub.ZuatExtension):
        identifier = "consumer"
        version = "1"

        def bootstrap(self, service, source, *, force=False):
            build = service.build_bundle(source, name="consumer-bundle")
            return build, service.bootstrap_bundle(
                build.bundle_id, agents=["claude", "pi"], trust=True, force=force
            )

        def locate_artifacts(self, context):
            return (context.runtime_root / "skills/review/SKILL.md",)

    host = Host()
    service.register_extension(host)
    assert service.list_bundles() == ()
    assert all(not manager.calls for manager in managers.values())
    first, result = host.bootstrap(service, source)
    assert result.ok, result
    with pub.Zuat(root=tmp_path / "tracking", home=tmp_path / "home") as reopened:
        assert reopened.get_bundle(first.bundle_id).builds == (first,)
        assert reopened.resolve_bundle(first.bundle_id, agent="claude").is_dir()
    artifacts = service.resolve_artifacts("claude", host.identifier)
    assert artifacts
    ref = pub.PluginRef(
        "claude", next(t.plugin_id for t in result.targets if t.agent == "claude")
    )
    assert service.artifact_status(ref, host.identifier).effective
    (source / "nested/review/data.bin").write_bytes(b"source-body-sentinel")
    managers["claude"].fail.update({"update", "install"})
    second, failed = host.bootstrap(service, source, force=True)
    assert first.bundle_id == second.bundle_id
    assert first.build_revision != second.build_revision
    assert not failed.ok
    assert [t.status for t in failed.targets] == ["failed", "success"]
    assert not service.artifact_status(ref, host.identifier).effective
    managers["claude"].fail.clear()
    retry = service.bootstrap_bundle(second.bundle_id, agents=["claude"], trust=True)
    assert retry.ok, retry
    removed = service.remove_bundle(second.bundle_id)
    assert removed.ok, removed
    assert not managers["claude"].installed
    assert not managers["pi"].installed
