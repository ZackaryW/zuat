from pathlib import Path

import pytest

from zuat.specs.claude import ClaudeResolver
from zuat.specs.codex import CodexResolver


@pytest.fixture(autouse=True)
def isolated_system_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect machine-wide skill locations so lookup tests never read the real machine."""
    system = tmp_path / "system"
    monkeypatch.setattr(ClaudeResolver, "MANAGED_ROOT", system / "claude-managed")
    monkeypatch.setattr(CodexResolver, "ADMIN_ROOT", system / "codex-admin")
    return system
