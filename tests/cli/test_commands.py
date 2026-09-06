import json
from dataclasses import dataclass

import pytest
from click.testing import CliRunner

from zuat import pub as api
from zuat.cli import cli


@dataclass
class StubResult:
    operation: str
    status: str = "success"
    operation_id: str | None = "op_test"
    profile: str | None = "default"
    diagnostics: tuple[str, ...] = ()

    def to_dict(self):
        return {
            "operation": self.operation,
            "status": self.status,
            "ok": self.status == "success",
            "operation_id": self.operation_id,
            "profile": self.profile,
            "assets": [],
            "profiles": [],
            "materializations": [],
            "history": [],
            "diagnostics": list(self.diagnostics),
        }


@pytest.mark.parametrize(
    ("arguments", "operation"),
    [
        (["status", "--agent", "codex"], "status"),
        (
            [
                "install",
                "--agent",
                "codex",
                "--kind",
                "skill",
                "--source",
                "reviewer",
                "--name",
                "reviewer",
                "--scope",
                "project",
                "--locator",
                "skills/reviewer",
            ],
            "install",
        ),
        (
            ["uninstall", "--agent", "codex", "--asset-ref", "asset_one"],
            "uninstall",
        ),
        (["profile", "list"], "profiles"),
        (["profile", "create", "work", "--agent", "codex"], "create_profile"),
        (["profile", "switch", "work", "--agent", "codex"], "switch_profile"),
        (["history"], "history"),
        (
            ["revert", "--operation-id", "op_one", "--agent", "codex"],
            "revert",
        ),
    ],
)
def test_commands_route_only_through_public_api(
    monkeypatch: pytest.MonkeyPatch, arguments: list[str], operation: str
) -> None:
    called = []

    def invoke(request=None, **kwargs):
        called.append((request, kwargs))
        return StubResult(operation)

    monkeypatch.setattr(api, operation, invoke)
    result = CliRunner().invoke(cli, arguments)

    assert result.exit_code == 0, result.output
    assert len(called) == 1
    assert operation in result.stdout


@pytest.mark.parametrize(
    ("arguments", "operation", "expected"),
    [
        (
            [
                "list-assets",
                "--agent",
                "codex",
                "--kind",
                "skill",
                "--scope",
                "user",
                "--authority",
                "unauthoritative",
            ],
            "list_assets",
            {
                "agent": "codex",
                "kind": "skill",
                "scope": "user",
                "authority": "unauthoritative",
                "present": True,
            },
        ),
        (
            ["adopt-all", "--agent", "claude", "--kind", "hook"],
            "adopt_all",
            {
                "agent": "claude",
                "kind": "hook",
                "scope": None,
                "authority": None,
                "present": True,
                "force": False,
            },
        ),
        (
            ["uninstall-all", "--agent", "kimi", "--kind", "skill", "--force"],
            "uninstall_all",
            {
                "agent": "kimi",
                "kind": "skill",
                "scope": None,
                "authority": None,
                "present": True,
                "force": True,
            },
        ),
        (
            [
                "restore-all",
                "--operation-id",
                "op_source",
                "--agent",
                "pi",
                "--kind",
                "hook",
                "--force",
            ],
            "restore_all",
            {
                "operation_id": "op_source",
                "agent": "pi",
                "kind": "hook",
                "scope": None,
                "authority": None,
                "present": True,
                "force": True,
            },
        ),
    ],
)
def test_helper_commands_route_filters_through_public_api(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    operation: str,
    expected: dict[str, object],
) -> None:
    captured = []

    def invoke(*args, **kwargs):
        captured.append((args, kwargs))
        return StubResult(operation.replace("_", "-"))

    monkeypatch.setattr(api, operation, invoke)

    result = CliRunner().invoke(cli, [*arguments, "--json"])

    assert result.exit_code == 0, result.output
    assert captured[0][0] == ()
    assert {key: value for key, value in captured[0][1].items() if key != "root"} == expected
    assert json.loads(result.stdout)["result"]["status"] == "success"


def test_failed_helper_result_maps_to_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr(
        api,
        "uninstall_all",
        lambda **kwargs: StubResult("uninstall-all", status="failed"),
    )

    result = CliRunner().invoke(
        cli, ["uninstall-all", "--agent", "codex", "--kind", "skill"]
    )

    assert result.exit_code == 1


def test_install_builds_explicit_source_and_force_request(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        api,
        "install",
        lambda request, **kwargs: captured.append(request) or StubResult("install"),
    )

    result = CliRunner().invoke(
        cli,
        [
            "install",
            "--agent",
            "claude",
            "--kind",
            "hook",
            "--source",
            "hook.json",
            "--name",
            "guard",
            "--scope",
            "user",
            "--locator",
            "hooks/Start/0",
            "--force",
        ],
    )

    assert result.exit_code == 0, result.output
    request = captured[0]
    assert request.agents == ("claude",)
    assert request.force is True
    assert request.assets[0].to_dict() == {
        "agent": "claude",
        "kind": "hook",
        "scope": "user",
        "name": "guard",
        "locator": "hooks/Start/0",
        "source": "hook.json",
        "asset_ref": None,
    }


def test_install_can_adopt_multiple_stable_references(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        api,
        "install",
        lambda request, **kwargs: captured.append(request) or StubResult("install"),
    )

    result = CliRunner().invoke(
        cli,
        [
            "install",
            "--agent",
            "codex",
            "--asset-ref",
            "asset_one",
            "--asset-ref",
            "asset_two",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured[0].asset_refs == ("asset_one", "asset_two")


@pytest.mark.parametrize(
    "arguments",
    [
        ["install", "--agent", "codex"],
        ["install", "--agent", "codex", "--source", "reviewer"],
        ["uninstall", "--agent", "codex"],
        ["profile", "create", "work"],
        ["profile", "switch", "work"],
        ["revert", "--operation-id", "op_one"],
        ["revert", "--agent", "codex"],
    ],
)
def test_incomplete_mutation_input_fails_before_public_call(
    monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    calls = []
    for name in (
        "install",
        "uninstall",
        "create_profile",
        "switch_profile",
        "revert",
    ):
        monkeypatch.setattr(api, name, lambda *args, **kwargs: calls.append(name))

    result = CliRunner().invoke(cli, arguments)

    assert result.exit_code != 0
    assert calls == []


@pytest.mark.parametrize(
    "legacy", ("stage", "commit", "checkout", "undo", "recover", "snapshot")
)
def test_discarded_git_shaped_commands_are_absent(legacy: str) -> None:
    result = CliRunner().invoke(cli, [legacy, "--help"])

    assert result.exit_code != 0
    assert f"No such command '{legacy}'" in result.output


def test_json_mode_emits_one_envelope_and_diagnostics_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api,
        "status",
        lambda *args, **kwargs: StubResult("status", diagnostics=("native warning",)),
    )

    result = CliRunner().invoke(cli, ["status", "--agent", "codex", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"]["operation"] == "status"
    assert result.stdout.count("\n") == 1
    assert "native warning" in result.stderr


def test_human_output_is_concise_and_domain_oriented(monkeypatch) -> None:
    monkeypatch.setattr(
        api, "history", lambda *args, **kwargs: StubResult("history")
    )

    result = CliRunner().invoke(cli, ["history"])

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "history: success",
        "operation: op_test",
        "profile: default",
    ]
    assert not any(
        word in result.stdout.lower()
        for word in ("commit", "branch", "index", "working tree", "revision")
    )
