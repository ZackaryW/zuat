import json
from pathlib import Path

import pytest
from git import Actor, Repo

from zuat import pub


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    skill = root / "nested" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review carefully\n---\nDistinctive bundle body\n"
    )
    (skill / "data.bin").write_bytes(b"\x00support\xff")
    return root


@pytest.fixture
def service(tmp_path):
    with pub.Zuat(root=tmp_path / "tracking", home=tmp_path / "home") as result:
        yield result


def test_build_and_reopen_public_handles(source, service, tmp_path):
    before = service.registry.history()
    build = service.build_bundle(source, name="review-bundle")
    assert isinstance(build, pub.BundleBuild)
    assert build.agents == ("codex", "claude", "pi")
    assert service.registry.history() == before
    record = service.get_bundle(build.bundle_id)
    assert record.builds == (build,)
    assert record.targets == ()
    assert service.build_bundle(source, name="review-bundle") == build
    for agent, manifest in (
        ("codex", ".codex-plugin/plugin.json"),
        ("claude", ".claude-plugin/plugin.json"),
        ("pi", "package.json"),
    ):
        output = service.resolve_bundle(build.bundle_id, agent=agent)
        assert output.is_relative_to(tmp_path / "home" / ".zuat")
        assert (output / "skills/review/data.bin").read_bytes() == b"\x00support\xff"
        assert (output / "skills/review/SKILL.md").read_bytes() == (
            source / "nested/review/SKILL.md"
        ).read_bytes()
        value = json.loads((output / manifest).read_text())
        assert value["name"] == record.name
        assert value["version"] == build.version
    with pub.Zuat(root=tmp_path / "tracking", home=tmp_path / "home") as reopened:
        assert reopened.get_bundle(build.bundle_id) == record
        assert reopened.resolve_bundle(build.bundle_id, agent="pi") == output
    with pub.Zuat(
        root=tmp_path / "tracking", bundle_root=tmp_path / "other"
    ) as alternate:
        with pytest.raises(pub.BundleNotFoundError):
            alternate.get_bundle(build.bundle_id)


def test_new_build_preserves_old_and_checks_output(source, service):
    first = service.build_bundle(source)
    original = service.resolve_bundle(first.bundle_id, agent="claude")
    (source / "nested/review/data.bin").write_bytes(b"changed")
    second = service.build_bundle(source)
    assert first.bundle_id == second.bundle_id
    assert first.build_revision != second.build_revision
    assert (
        service.resolve_bundle(
            first.bundle_id, build_revision=first.build_revision, agent="claude"
        )
        == original
    )
    assert service.resolve_bundle(first.bundle_id, agent="claude") != original
    (original / "skills/review/data.bin").write_bytes(b"tampered")
    with pytest.raises(pub.BundleOutputError):
        service.resolve_bundle(
            first.bundle_id, build_revision=first.build_revision, agent="claude"
        )
    with pytest.raises(pub.BundleOutputError):
        service.resolve_bundle(first.bundle_id, build_revision="f" * 64, agent="claude")


@pytest.mark.parametrize(
    "problem",
    ["duplicate", "frontmatter", "nested", "empty", "size", "files", "changed"],
)
def test_invalid_source_preserves_registration(source, service, monkeypatch, problem):
    from zuat.utils.bundles import capture

    first = service.build_bundle(source)
    before = service.get_bundle(first.bundle_id)
    skill = source / "nested/review/SKILL.md"
    if problem == "duplicate":
        other = source / "other"
        other.mkdir()
        (other / "SKILL.md").write_bytes(skill.read_bytes())
    elif problem == "frontmatter":
        skill.write_text("not frontmatter")
    elif problem == "nested":
        (source / "SKILL.md").write_text(
            "---\nname: parent\ndescription: Parent\n---\n"
        )
    elif problem == "empty":
        skill.unlink()
    elif problem == "size":
        monkeypatch.setattr(capture, "MAX_BYTES", 4)
    elif problem == "files":
        monkeypatch.setattr(capture, "MAX_FILES", 1)
    else:
        original = capture.read_file

        def racing(path):
            data = original(path)
            if path.name == "SKILL.md":
                path.write_bytes(data + b"changed")
            return data

        monkeypatch.setattr(capture, "read_file", racing)
    with pytest.raises(pub.BundleBuildError):
        service.build_bundle(source)
    assert service.get_bundle(first.bundle_id) == before


def test_link_source_rejected(source, service, tmp_path):
    linked = source / "escape"
    try:
        linked.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(pub.BundleBuildError):
        service.build_bundle(source)


def test_git_exact_revision_no_source_execution(source, service, tmp_path):
    repo = Repo.init(source)
    marker = tmp_path / "executed"
    (source / "build.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()"
    )
    repo.index.add(["nested", "build.py"])
    actor = Actor("test", "test@example.invalid")
    commit = repo.index.commit("first", author=actor, committer=actor)
    (source / "nested/review/data.bin").write_bytes(b"uncommitted")
    ref = "git+" + source.as_uri()
    try:
        build = service.build_bundle(ref, revision=commit.hexsha)
        assert build.source_commit == commit.hexsha
        output = service.resolve_bundle(build.bundle_id, agent="pi")
        assert (output / "skills/review/data.bin").read_bytes() == b"\x00support\xff"
        assert (source / "nested/review/data.bin").read_bytes() == b"uncommitted"
        assert not marker.exists()
    finally:
        repo.close()


@pytest.mark.parametrize("unsafe", ["NUL", "DATA.bin"])
def test_git_paths_cannot_silently_drop_support_files(source, service, unsafe):
    with Repo.init(source) as repo:
        actor = Actor("test", "test@example.invalid")
        repo.git.config("core.protectNTFS", "false")
        repo.index.add(["nested"])
        first = repo.index.commit("source", author=actor, committer=actor)
        blob = first.tree / "nested/review/data.bin"
        repo.git.update_index(
            "--add", "--cacheinfo", f"100644,{blob.hexsha},nested/review/{unsafe}"
        )
        commit = repo.index.commit(
            "unsafe portable path", author=actor, committer=actor
        )
        with pytest.raises(pub.BundleBuildError):
            service.build_bundle("git+" + source.as_uri(), revision=commit.hexsha)
        assert service.list_bundles() == ()


@pytest.mark.parametrize(
    "source",
    [
        "https://user:secret@example.invalid/repo",
        "ext::unsafe",
        "https://example.invalid/repo?token=secret",
    ],
)
def test_credentials_and_unsafe_sources_rejected(service, source):
    with pytest.raises(pub.BundleBuildError):
        service.build_bundle(source)
    assert service.list_bundles() == ()


def test_name_collision_is_not_adoption(source, service, tmp_path):
    service.build_bundle(source, name="same")
    other = tmp_path / "other-source"
    other.mkdir()
    (other / "SKILL.md").write_bytes((source / "nested/review/SKILL.md").read_bytes())
    with pytest.raises(pub.BundleBuildError):
        service.build_bundle(other, name="same")


def test_source_mapping_is_kept_with_the_captured_material(source):
    from zuat.utils.bundles.capture import skills, tree

    captured = skills(tree(source))
    assert captured.sources == {"nested/review": "skills/review"}
    assert captured.files["skills/review/data.bin"] == b"\x00support\xff"


def test_renderer_contract_change_gets_a_new_immutable_build(
    source, service, monkeypatch
):
    from zuat.specs.claude_bundles import ClaudeBundleAdapter

    before = service.build_bundle(source)
    monkeypatch.setattr(ClaudeBundleAdapter, "contract", "test-new-renderer")
    after = service.build_bundle(source)
    assert before.bundle_id == after.bundle_id
    assert before.build_revision != after.build_revision
    old = service.resolve_bundle(
        before.bundle_id, build_revision=before.build_revision, agent="pi"
    )
    (old / "package.json").unlink()
    with pytest.raises(pub.BundleOutputError):
        service.resolve_bundle(
            before.bundle_id, build_revision=before.build_revision, agent="pi"
        )
