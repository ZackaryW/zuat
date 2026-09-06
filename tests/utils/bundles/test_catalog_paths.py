import pytest

from zuat.utils.bundles.catalog import project


def test_catalog_manifest_parent_cannot_redirect_writes(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "marketplace.json"
    sentinel.write_bytes(b"unrelated catalog")
    root = tmp_path / "catalog"
    root.mkdir()
    try:
        (root / ".claude-plugin").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    output = tmp_path / "revision" / "claude"
    output.mkdir(parents=True)
    (output / "payload").write_bytes(b"plugin data")
    with pytest.raises(ValueError):
        project(root, output, ".claude-plugin/marketplace.json", {"name": "managed"})
    assert sentinel.read_bytes() == b"unrelated catalog"
