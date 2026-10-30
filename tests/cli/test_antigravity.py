"""The CLI accepts Antigravity wherever it accepts an agent."""

import pytest
from click.testing import CliRunner

from tests.cli.test_commands import StubResult
from zuat import pub as api
from zuat.cli import cli


def test_agent_option_accepts_antigravity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []
    monkeypatch.setattr(api, "uninstall_all", lambda *a, **k: captured.append(k) or StubResult("uninstall-all"))

    result = CliRunner().invoke(cli, ["uninstall-all", "--agent", "antigravity", "--kind", "skill", "--json"])

    assert result.exit_code == 0, result.output
    assert captured[0]["agent"] == "antigravity"


def test_unknown_agent_is_still_rejected() -> None:
    result = CliRunner().invoke(cli, ["uninstall-all", "--agent", "gemini", "--kind", "skill"])

    assert result.exit_code == 2
