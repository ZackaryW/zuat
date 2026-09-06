import json

import pytest

from zuat import pub


def test_roots_are_separate_and_queries_reopen(tmp_path):
    home = tmp_path / "home"
    tracking = tmp_path / "tracking"
    with pub.Zuat(root=tracking, home=home) as service:
        assert service.list_bundles() == ()
        with pytest.raises(pub.BundleNotFoundError):
            service.get_bundle("missing")
        assert service.registry.root == tracking
    alternate = tmp_path / "alternate"
    with pub.Zuat(root=tracking, home=home, bundle_root=alternate) as service:
        assert service.list_bundles() == ()
    assert pub.list_bundles(root=tracking, home=home, bundle_root=alternate) == ()
    assert not (home / ".zuat" / ".git").exists()


@pytest.mark.parametrize("relative", [".", "inside", ".."])
def test_reject_overlapping_roots(tmp_path, relative):
    tracking = tmp_path / "tracking"
    with pytest.raises(pub.BundleStoreError):
        pub.Zuat(root=tracking, home=tmp_path / "home", bundle_root=tracking / relative)
    assert not tracking.exists(), (
        "invalid compiler overlap must be checked before initializing Git"
    )


@pytest.mark.parametrize(
    "payload", ["broken", "[]", '{"schema":99}', '{"schema":1,"bundles":{"escape":{}}}']
)
def test_malformed_index_fails_closed(tmp_path, payload):
    store = tmp_path / "store"
    store.mkdir()
    index = store / "index.json"
    index.write_text(payload)
    with pub.Zuat(root=tmp_path / "tracking", bundle_root=store) as service:
        with pytest.raises(pub.BundleStoreError):
            service.list_bundles()
    assert index.read_text() == payload


def test_private_lock_and_atomic_failure_preserve_index(tmp_path, monkeypatch):
    from zuat.pub.bundles.store import BundleStore
    from zuat.gitcore.locking import registry_lock

    store = BundleStore(tmp_path / "store", tmp_path / "tracking")
    with store.locked():
        store.write({"schema": 1, "bundles": {}})
    before = store.index.read_bytes()
    with registry_lock(store.root / ".lock"):
        with pytest.raises(pub.BundleStoreError):
            with store.locked():
                pytest.fail("a concurrent writer entered")
    import zuat.utils.mutation as mutation

    monkeypatch.setattr(
        mutation.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(OSError("interrupted")),
    )
    with pytest.raises(pub.BundleStoreError):
        store.write({"schema": 1, "bundles": {}})
    assert store.index.read_bytes() == before


def test_reopening_reports_attempt_without_resuming(tmp_path):
    from zuat.pub.bundles.store import BundleStore

    store = BundleStore(tmp_path / "store", tmp_path / "tracking")
    state = {
        "schema": 1,
        "bundles": {
            "example": {
                "bundle_id": "example",
                "name": "example",
                "source": "local-binding",
                "source_kind": "local",
                "builds": [],
                "targets": [
                    {
                        "agent": "claude",
                        "plugin_id": "example@zuat-example",
                        "build_revision": None,
                        "status": "indeterminate",
                        "attempt": "install",
                    }
                ],
            }
        },
    }
    with store.locked():
        store.write(state)
    with pub.Zuat(root=tmp_path / "tracking", bundle_root=store.root) as service:
        record = service.get_bundle("example")
        assert record.targets[0].status == "indeterminate"
        assert record.targets[0].attempt == "install"
        assert service.list_bundles() == (record,)
    assert json.loads(store.index.read_text()) == state


def test_malformed_build_digest_is_not_an_accepted_registration(tmp_path):
    store = tmp_path / "store"
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("---\nname: review\ndescription: Review\n---\n")
    with pub.Zuat(root=tmp_path / "tracking", bundle_root=store) as service:
        build = service.build_bundle(source)
        index = store / "index.json"
        data = json.loads(index.read_text())
        data["bundles"][build.bundle_id]["builds"][0]["digests"]["pi"] = "invalid"
        index.write_text(json.dumps(data))
        with pytest.raises(pub.BundleStoreError):
            service.get_bundle(build.bundle_id)


def test_index_cannot_publish_more_than_it_can_reopen(tmp_path):
    from zuat.pub.bundles.store import BundleStore

    store = BundleStore(tmp_path / "store", tmp_path / "tracking")
    with store.locked():
        store.write({"schema": 1, "bundles": {}})
        before = store.index.read_bytes()
        with pytest.raises(pub.BundleStoreError):
            store.write(
                {
                    "schema": 1,
                    "bundles": {
                        "large": {
                            "bundle_id": "large",
                            "name": "large",
                            "source_kind": "local",
                            "source": "x" * (8 * 1024 * 1024),
                            "builds": [],
                            "targets": [],
                        }
                    },
                }
            )
        assert store.index.read_bytes() == before
