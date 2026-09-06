"""Injectable argument-vector subprocess execution."""

from __future__ import annotations

import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def run(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> ProcessResult: ...


class SubprocessRunner:
    def run(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> ProcessResult:
        selected = dict(os.environ)
        selected.update(environment or {})
        completed = subprocess.run(args, cwd=cwd, env=selected, capture_output=True, text=True, check=False, shell=False)
        return ProcessResult(args, completed.returncode, completed.stdout, completed.stderr)
