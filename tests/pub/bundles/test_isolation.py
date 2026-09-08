from zuat.gitcore.plugin_safety import clean_metadata


def test_bundle_reference_envelope_is_allowlisted():
    result = clean_metadata(
        {
            "state_kind": "plugin-lifecycle",
            "bundle_id": "safe-bundle",
            "build_revision": "a" * 64,
            "source": "credential-sentinel",
            "source_revision": "private-source-ref-sentinel",
            "files": ["source-body-sentinel"],
        }
    )
    assert result == {
        "state_kind": "plugin-lifecycle",
        "bundle_id": "safe-bundle",
        "build_revision": "a" * 64,
    }


def test_lifecycle_history_never_stores_bundle_bodies(source, native_service):
    service, managers = native_service
    (source / "nested/review/data.bin").write_bytes(b"source-body-sentinel")
    build = service.build_bundle(source)
    assert service.bootstrap_bundle(
        build.bundle_id, agents=["claude", "pi"], trust=True
    ).ok
    (source / "nested/review/data.bin").write_bytes(b"source-body-sentinel changed")
    updated = service.build_bundle(source)
    managers["claude"].fail.update({"update", "install"})
    assert not service.bootstrap_bundle(
        updated.bundle_id, agents=["claude"], trust=True, force=True
    ).ok
    assert any(
        event.metadata.get("bundle_id") == build.bundle_id
        for event in service.history().history
    )
    # Inspect every reachable blob, including superseded journal/profile files.
    blobs = {
        obj.hexsha
        for commit in service.registry.repo.iter_commits("--all")
        for obj in commit.tree.traverse()
        if obj.type == "blob"
    }
    forbidden = (
        b"source-body-sentinel",
        b"credential-sentinel",
        str(source).encode(),
        str(service.home / ".zuat").encode(),
    )
    for sha in blobs:
        payload = service.registry.repo.odb.stream(bytes.fromhex(sha)).read()
        assert all(secret not in payload for secret in forbidden)
    for path in service.registry.control_root.rglob("*"):
        if path.is_file():
            assert all(secret not in path.read_bytes() for secret in forbidden)
