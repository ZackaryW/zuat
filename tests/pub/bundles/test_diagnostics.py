import pytest

from zuat import pub


def files(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_diagnostics_checks_without_creating_native_homes(native_service, source):
    service, managers = native_service
    built = service.build_bundle(source)
    before = files(service.home)
    journal = service.registry.repo.head.commit.hexsha
    report = service.doctor_bundle(built.bundle_id)
    assert isinstance(report, pub.BundleDiagnostics)
    assert report.ok
    assert {(c.kind, c.agent) for c in report.checks} == {
        (kind, agent)
        for kind in ("output", "manager")
        for agent in ("codex", "claude", "pi")
    }
    assert files(service.home) == before
    assert service.registry.repo.head.commit.hexsha == journal
    assert all(not manager.installed for manager in managers.values())
    assert service.get_bundle(built.bundle_id).targets == ()


@pytest.mark.parametrize("damage", ["modify", "delete"])
def test_reports_multiple_faults_without_repair(native_service, source, damage):
    service, managers = native_service
    built = service.build_bundle(source)
    output = service.resolve_bundle(built.bundle_id, agent="claude")
    skill = output / "skills/review/SKILL.md"
    if damage == "modify":
        skill.write_text("modified")
    else:
        skill.unlink()
    managers["claude"].unavailable = True
    before = files(service.home)
    report = service.doctor_bundle(built.bundle_id, agents=("claude", "kimi"))
    assert not report.ok
    assert {(c.kind, c.agent, c.status) for c in report.checks} == {
        ("output", "claude", "unavailable"),
        ("manager", "claude", "unavailable"),
        ("manager", "kimi", "unsupported"),
    }
    assert files(service.home) == before
    assert "credential-sentinel" not in repr(report)


def test_incomplete_inventory_and_pending_attempt_are_not_repaired(
    native_service, source
):
    service, managers = native_service
    built = service.build_bundle(source)
    managers["claude"].interrupt = "install"
    with pytest.raises(KeyboardInterrupt):
        service.bootstrap_bundle(built.bundle_id, agents=("claude",), trust=True)
    before = files(service.home)
    journal = service.registry.repo.head.commit.hexsha
    managers["claude"].interrupt = None
    managers["claude"].fail.add("list")
    report = service.doctor_bundle(built.bundle_id, agents=("claude",))
    assert not report.ok
    assert files(service.home) == before
    assert service.registry.repo.head.commit.hexsha == journal
    assert service.get_bundle(built.bundle_id).targets[0].attempt == "install"


def test_module_diagnostics_and_invalid_registration(tmp_path, source):
    context = {"root": tmp_path / "tracking", "home": tmp_path / "home"}
    built = pub.build_bundle(source, **context)
    assert not pub.doctor_bundle(built.bundle_id, agents=("kimi",), **context).ok
    with pytest.raises(pub.BundleNotFoundError):
        pub.doctor_bundle("missing", **context)
    index = context["home"] / ".zuat/index.json"
    index.write_text("broken")
    with pytest.raises(pub.BundleStoreError):
        pub.doctor_bundle(built.bundle_id, **context)
    assert index.read_text() == "broken"
