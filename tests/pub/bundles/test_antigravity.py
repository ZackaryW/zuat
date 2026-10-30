"""Antigravity has no bundle bootstrap contract; neighbors keep their own outcomes."""


def test_bootstrap_reports_antigravity_unsupported_beside_a_successful_neighbor(source, native_service):
    service, managers = native_service
    build = service.build_bundle(source)

    result = service.bootstrap_bundle(build.bundle_id, agents=["antigravity", "claude"], trust=True)

    assert [t.status for t in result.targets] == ["unsupported", "success"]
    assert managers["claude"].installed
    assert not (service.home / ".gemini").exists()


def test_explicit_diagnostics_report_antigravity_unsupported(source, native_service):
    service, _ = native_service
    built = service.build_bundle(source)

    report = service.doctor_bundle(built.bundle_id, agents=("antigravity",))

    assert not report.ok
    assert {(c.kind, c.agent, c.status) for c in report.checks} == {("manager", "antigravity", "unsupported")}
