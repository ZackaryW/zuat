import subprocess
import sys
from dataclasses import fields

import pytest

import zuat.pub as public
from zuat.gitcore.models import (
    AssetEvidence,
    AssetRef,
    Authority,
    JournalEvent,
    OperationKind,
    OperationOutcome,
    Profile,
)
from zuat.pub import AssetInput, OperationResult, OperationStatus, Zuat, ZuatRequest


def test_public_surface_exposes_only_domain_operations() -> None:
    expected = {
        "status",
        "install",
        "uninstall",
        "profiles",
        "create_profile",
        "switch_profile",
        "history",
        "revert",
        "list_assets",
        "adopt_all",
        "uninstall_all",
        "restore_all",
    }
    assert all(callable(getattr(public, name)) for name in expected)
    assert all(hasattr(Zuat, name) for name in expected)
    assert not any(
        hasattr(public, name)
        for name in ("stage", "commit", "checkout", "undo", "recover", "snapshot")
    )


def test_request_carries_only_explicit_domain_inputs() -> None:
    request = ZuatRequest(
        agents=("codex",),
        assets=(
            AssetInput(
                agent="codex",
                kind="skill",
                scope="project",
                name="reviewer",
                locator="skills/reviewer",
                source="C:/assets/reviewer",
            ),
        ),
        asset_refs=("asset_one",),
        profile="work",
        operation_id="op_one",
        force=True,
    )

    assert request.to_dict() == {
        "agents": ["codex"],
        "assets": [
            {
                "agent": "codex",
                "kind": "skill",
                "scope": "project",
                "name": "reviewer",
                "locator": "skills/reviewer",
                "source": "C:/assets/reviewer",
                "asset_ref": None,
            }
        ],
        "asset_refs": ["asset_one"],
        "profile": "work",
        "operation_id": "op_one",
        "force": True,
    }
    assert not {
        "paths",
        "message",
        "revision",
        "branch",
        "staged",
    }.intersection(item.name for item in fields(ZuatRequest))


def test_result_serializes_domain_evidence_profiles_and_history() -> None:
    ref = AssetRef("asset_one", "codex", "skill", "user", "skills/reviewer")
    evidence = AssetEvidence(ref, "sha256:value", Authority.AUTHORITATIVE)
    event = JournalEvent(
        "op_one",
        1,
        OperationKind.INSTALL,
        OperationOutcome.SUCCESS,
        profile="default",
        after=(evidence,),
    )
    result = OperationResult(
        "install",
        OperationStatus.SUCCESS,
        operation_id="op_one",
        profile="default",
        assets=(evidence,),
        profiles=(Profile("default", selected=True, assets=(ref.id,)),),
        history=(event,),
    )

    payload = result.to_dict()

    assert payload["operation_id"] == "op_one"
    assert payload["assets"][0]["asset_ref"] == "asset_one"
    assert payload["profiles"][0]["selected"] is True
    assert payload["history"][0]["kind"] == "install"
    assert not {
        "revision",
        "commit",
        "branch",
        "index",
        "working_tree",
        "snapshot",
    }.intersection(payload)


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("status", ZuatRequest(agents=("codex",))),
        ("install", ZuatRequest(agents=("codex",), asset_refs=("asset_one",))),
        ("uninstall", ZuatRequest(agents=("codex",), asset_refs=("asset_one",))),
        ("profiles", ZuatRequest()),
        ("create_profile", ZuatRequest(profile="work")),
        ("switch_profile", ZuatRequest(profile="work")),
        ("history", ZuatRequest()),
        ("revert", ZuatRequest(operation_id="op_one")),
    ],
)
def test_module_functions_delegate_one_request_to_the_service(
    monkeypatch, method: str, value: ZuatRequest
) -> None:
    calls = []

    def fake_call(selected, value, *, root=None):
        calls.append((selected, value, root))
        return OperationResult(selected, OperationStatus.SUCCESS)

    monkeypatch.setattr(public, "_call", fake_call)

    result = getattr(public, method)(value, root="C:/registry")

    assert result.operation == method
    assert calls == [(method, value, "C:/registry")]


def test_public_models_import_without_click_or_gitpython() -> None:
    script = """
import sys
from zuat.pub import AssetInput, OperationResult, OperationStatus, ZuatRequest
assert AssetInput and OperationResult and OperationStatus and ZuatRequest
assert 'click' not in sys.modules
assert 'git' not in sys.modules
assert 'zuat.gitcore.repository' not in sys.modules
assert 'zuat.specs.codex' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
