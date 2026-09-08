import json

import pytest
from git import Actor, Repo

from zuat import pub


@pytest.fixture
def git_source(source):
    with Repo.init(source, initial_branch="main") as repo:
        repo.index.add(["nested"])
        actor = Actor("test", "test@example.invalid")
        repo.index.commit("source", author=actor, committer=actor)
        repo.create_tag("v1")
        yield repo


@pytest.mark.parametrize("requested", ["main", "refs/tags/v1", "HEAD", "commit"])
def test_requested_git_revision_survives_reopen(
    git_source, source, tmp_path, requested
):
    commit = git_source.head.commit.hexsha
    revision = commit if requested == "commit" else requested
    options = {"root": tmp_path / "tracking", "home": tmp_path / "home"}
    with pub.Zuat(**options) as service:
        build = service.build_bundle("git+" + source.as_uri(), revision=revision)
    with pub.Zuat(**options) as reopened:
        saved = reopened.get_bundle(build.bundle_id).builds[0]
        assert saved.source_revision == revision
        assert saved.source_commit == commit
        assert saved == build
        assert reopened.list_bundles()[0].builds == (saved,)


def test_equivalent_git_build_keeps_original_provenance(git_source, source, tmp_path):
    with pub.Zuat(root=tmp_path / "tracking", home=tmp_path / "home") as service:
        reference = "git+" + source.as_uri()
        original = service.build_bundle(reference, revision="main")
        actor = Actor("test", "test@example.invalid")
        later = git_source.index.commit("same content", author=actor, committer=actor)
        git_source.create_tag("v2", later)
        reused = service.build_bundle(reference, revision="refs/tags/v2")
        assert reused == original
        assert reused.source_revision == "main"
        assert reused.source_commit != later.hexsha
        assert service.get_bundle(original.bundle_id).builds == (original,)


def test_local_build_does_not_claim_a_git_revision(source, tmp_path):
    with pub.Zuat(root=tmp_path / "tracking", home=tmp_path / "home") as service:
        build = service.build_bundle(source)
        assert build.source_revision is None
        assert build.source_commit is None


@pytest.mark.parametrize(
    "invalid",
    [None, 42, "--all", "main..other", "x" * 257],
    ids=["missing", "non-string", "option", "range", "oversized"],
)
def test_invalid_persisted_git_revision_fails_closed(
    git_source, source, tmp_path, invalid
):
    store = tmp_path / "compiler"
    options = {"root": tmp_path / "tracking", "bundle_root": store}
    with pub.Zuat(**options) as service:
        build = service.build_bundle("git+" + source.as_uri(), revision="main")
    index = store / "index.json"
    data = json.loads(index.read_text())
    data["bundles"][build.bundle_id]["builds"][0]["source_revision"] = invalid
    index.write_text(json.dumps(data))
    before = index.read_bytes()
    with pub.Zuat(**options) as reopened, pytest.raises(pub.BundleStoreError):
        reopened.list_bundles()
    assert index.read_bytes() == before
