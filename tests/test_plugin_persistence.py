import json
import shutil
from dataclasses import replace
import pytest

from test_plugin_workflows import setup
from zuat.pub import ZuatRequest
from zuat.gitcore import OperationKind, OperationOutcome


def test_plugin_under_global_skills_is_not_copied_as_global_content(setup):
    service, native, _ = setup
    native.version = "1"
    destination = service.home / ".claude/skills/review"
    destination.parent.mkdir(parents=True)
    shutil.copytree(native.root, destination)
    (destination / "SKILL.md").write_text("---\nname: review\ndescription: bundled\n---\nPLUGIN BODY")
    native.root = destination
    result = service.status(ZuatRequest(agents=("claude",)))
    assert result.ok, result.diagnostics
    assert not (service.registry.observation_root / "claude/user/skills/review").exists()
    assert all(item.evidence.get("provider") == "plugin" for item in result.assets if item.ref.kind == "skill")
    native.fail_discovery = True
    result = service.status(ZuatRequest(agents=("claude",)))
    assert result.completeness == "partial"
    assert not (service.registry.observation_root / "claude/user/skills/review").exists()


def test_private_event_and_recovery_metadata_never_persist_native_payload(setup):
    service, native, _ = setup
    native.version = "1"
    observed = service.status(ZuatRequest(agents=("claude",)))
    before = tuple(item for item in observed.assets if item.ref.kind == "plugin")
    metadata = {"state_kind": "plugin-lifecycle", "native_output": "PLUGIN BODY credential", "runtime_root": str(native.root)}
    marker = service.registry.begin_operation(OperationKind.UPDATE, profile="default", before=before, metadata=metadata)
    pending = json.loads(service.registry.recovery_marker.read_text())
    assert pending["metadata"] == {"state_kind": "plugin-lifecycle"}
    event = service.registry.append_event(OperationKind.UPDATE, OperationOutcome.FAILED, before=before,
                                          metadata=metadata, diagnostics=("PLUGIN BODY credential",))
    assert event.metadata == {"state_kind": "plugin-lifecycle"}
    assert event.diagnostics == ("plugin operation failed; native details omitted",)
    service.registry.clear_operation(marker)


def test_failed_discovery_retains_last_pointer_without_claiming_absence(setup):
    service, native, _ = setup
    native.version = "1"
    assert service.status(ZuatRequest(agents=("claude",))).ok
    paths = tuple((service.registry.observation_root / "claude/user/plugins").glob("*.json"))
    saved = {path: path.read_bytes() for path in paths}
    assert saved
    native.fail_discovery = True
    result = service.status(ZuatRequest(agents=("claude",)))
    assert result.completeness == "partial"
    assert {path: path.read_bytes() for path in paths} == saved


def test_plugin_evidence_sink_discards_extra_payload_fields(setup):
    service, native, _ = setup
    native.version = "1"
    observed = service.status(ZuatRequest(agents=("claude",)))
    before = next(item for item in observed.assets if item.ref.kind == "plugin")
    polluted = replace(before, evidence={**before.evidence, "native_output": "credential", "runtime_root": str(native.root), "body": "PLUGIN BODY"})
    event = service.registry.append_event(OperationKind.UPDATE, OperationOutcome.FAILED, before=(polluted,))
    serialized = event.to_dict()["before"][0]["evidence"]
    assert serialized == before.to_dict()["evidence"]


def test_old_plugin_history_rejected_without_rewriting_or_harming_globals(setup):
    service, native, _ = setup
    native.version = "1"
    result = service.status(ZuatRequest(agents=("claude",)))
    event_path = next(path for path in (service.registry.root / "operations").glob("*.json") if json.loads(path.read_text())["operation_id"] == result.operation_id)
    payload = json.loads(event_path.read_text())
    payload["after"][0]["evidence"]["native_evidence"] = {"body": "OLD PLUGIN BODY"}
    event_path.write_text(json.dumps(payload))
    original = event_path.read_bytes()
    with pytest.raises(Exception, match="fresh registry"):
        service.registry.history()
    assert event_path.read_bytes() == original
