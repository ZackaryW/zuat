import pytest

from zuat import pub


def test_add_retains_partial_success(native_service, source):
    service, managers = native_service
    result = service.add_bundle(source, agents=("claude", "kimi"), trust=True)
    assert not result.ok
    assert [t.status for t in result.targets] == ["success", "unsupported"]
    assert managers["claude"].installed
    record = service.get_bundle(result.bundle_id)
    assert record.builds[0].build_revision == result.targets[0].build_revision


def test_add_pins_its_build(native_service, source, monkeypatch):
    service, managers = native_service
    original = service.build_bundle
    builds = []

    def interleaved(*args, **kwargs):
        first = original(*args, **kwargs)
        (source / "extra/SKILL.md").parent.mkdir()
        (source / "extra/SKILL.md").write_text(
            "---\nname: extra\ndescription: Another skill\n---\nNew body"
        )
        builds.extend((first, original(*args, **kwargs)))
        return first

    monkeypatch.setattr(service, "build_bundle", interleaved)
    result = service.add_bundle(source, agents=("claude",), trust=True)
    assert result.ok
    assert result.targets[0].build_revision == builds[0].build_revision
    assert service.get_bundle(result.bundle_id).builds[-1] == builds[1]
    assert next(iter(managers["claude"].installed.values()))[0] == builds[0].version


def test_module_add_does_not_grant_trust(tmp_path, source):
    context = {"root": tmp_path / "tracking", "home": tmp_path / "home"}
    result = pub.add_bundle(source, agents=("claude",), force=True, **context)
    assert not result.ok
    assert result.targets[0].reason == "source-trust-required"
    assert pub.get_bundle(result.bundle_id, **context).builds
    assert not (context["home"] / ".claude").exists()


def test_invalid_source_never_bootstraps(native_service, tmp_path):
    service, managers = native_service
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(pub.BundleBuildError):
        service.add_bundle(empty, agents=("claude",), trust=True)
    assert not managers["claude"].calls
    assert service.list_bundles() == ()
