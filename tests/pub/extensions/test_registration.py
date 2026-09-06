import pytest

from tests.pub.plugins.test_lifecycle import setup
from zuat import pub


def test_registration_is_inert_and_conflicts_preserve_original(setup):
    service, manager, _ = setup
    manager.version = "1"
    calls = []

    class Extension(pub.ZuatExtension):
        identifier = "registration-test"
        version = "1"

        def locate_artifacts(self, context):
            calls.append(context)
            return (context.runtime_root / "skills/review/SKILL.md",)

    extension = Extension()
    before = service.registry.history()
    service.register_extension(extension)
    service.register_extension(extension)
    assert calls == []
    assert manager.calls == []
    assert service.registry.history() == before
    with pytest.raises(ValueError):
        service.register_extension(Extension())
    result = service.artifact_status(
        pub.PluginRef("claude", "review@team"), extension.identifier
    )
    assert result.effective
    assert len(calls) == 1
    extension.version = "2"
    with pytest.raises(ValueError):
        service.register_extension(extension)


def test_optional_locator_and_invalid_identity(setup):
    service, manager, _ = setup
    manager.version = "1"

    class Empty(pub.ZuatExtension):
        identifier = "empty"
        version = "1"

    service.register_extension(Empty())
    result = service.artifact_status(pub.PluginRef("claude", "review@team"), "empty")
    assert not result.effective
    assert result.paths == ()
    assert result.reason == "artifact-unavailable"
    invalid = Empty()
    invalid.identifier = "../escape"
    with pytest.raises(ValueError):
        service.register_extension(invalid)
    with pytest.raises((TypeError, ValueError)):
        service.register_extension(object())


def test_registration_scopes_and_restart(tmp_path):
    class Extension(pub.ZuatExtension):
        identifier = "process-registration-test"
        version = "1"

    class Local(pub.ZuatExtension):
        identifier = "local-registration-test"
        version = "1"

    ref = pub.PluginRef("claude", "review@team")
    with pub.Zuat(root=tmp_path / "old", home=tmp_path / "home") as old:
        pub.register_extension(Extension())
        old.register_extension(Local())
        assert (
            old.artifact_status(ref, Extension.identifier).reason == "unknown-extension"
        )
        with pub.Zuat(root=tmp_path / "new", home=tmp_path / "home") as new:
            # Disabled policy can be set only for known registrations; no native call.
            assert new.set_artifact_policy(ref, Extension.identifier, "disabled").ok
            assert not new.set_artifact_policy(ref, Local.identifier, "disabled").ok
        assert old.set_artifact_policy(ref, Local.identifier, "disabled").ok
    with pub.Zuat(root=tmp_path / "old", home=tmp_path / "home") as reopened:
        assert (
            reopened.artifact_status(ref, Local.identifier).reason
            == "unknown-extension"
        )


def test_locator_failure_is_unresolved_not_persisted(setup):
    service, manager, _ = setup
    manager.version = "1"

    class Broken(pub.ZuatExtension):
        identifier = "broken"
        version = "1"

        def locate_artifacts(self, context):
            raise RuntimeError("secret-extension-payload")

    service.register_extension(Broken())
    before = service.registry.history()
    result = service.artifact_status(pub.PluginRef("claude", "review@team"), "broken")
    assert not result.effective
    assert result.paths == ()
    assert result.reason == "artifact-locator-failed"
    assert service.registry.history() == before


def test_removed_public_surface_has_no_compatibility_alias():
    assert not hasattr(pub, "ArtifactExtension")
    assert not hasattr(pub, "register_artifact")
    assert not hasattr(pub.Zuat, "register_artifact")
