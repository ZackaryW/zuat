"""Immutable public values; historical attempts are not native status queries."""

from dataclasses import dataclass


class BundleError(RuntimeError):
    """A bundle request cannot be completed safely."""


class BundleStoreError(BundleError):
    """The private compiler store is unsafe, invalid, or busy."""


class BundleNotFoundError(BundleError):
    """The selected store has no registered bundle with this handle."""


class BundleBuildError(BundleError):
    """Source validation or compilation failed before publication."""


class BundleOutputError(BundleError):
    """A selected immutable build is missing or no longer matches its digest."""


class BundleCleanupError(BundleError):
    """Removal reached cleanup, but retained its registration for explicit retry."""


@dataclass(frozen=True, slots=True)
class BundleBuild:
    """A successful compilation, not evidence of native installation.

    Source revision and commit describe the original Git build, not the last
    equivalent build request. Both are absent for local working-tree inputs.
    """

    bundle_id: str
    build_revision: str
    version: str
    agents: tuple[str, ...]
    source_commit: str | None = None
    source_revision: str | None = None


@dataclass(frozen=True, slots=True)
class BundleTarget:
    """Last recorded attempt only; interrupted attempts remain indeterminate."""

    agent: str
    plugin_id: str
    build_revision: str | None
    status: str
    attempt: str | None = None
    reason: str | None = None
    installed_version: str | None = None
    activation: str | None = None


@dataclass(frozen=True, slots=True)
class BundleRecord:
    """Read-only registration without exposing private source or output paths."""

    bundle_id: str
    name: str
    builds: tuple[BundleBuild, ...]
    targets: tuple[BundleTarget, ...]


@dataclass(frozen=True, slots=True)
class BundleOperationResult:
    """Independent target outcomes; no cross-agent transaction is implied."""

    bundle_id: str
    operation: str
    targets: tuple[BundleTarget, ...]
    outputs_removed: bool = False

    @property
    def ok(self) -> bool:
        return (bool(self.targets) or self.operation == "remove") and all(
            t.status in {"success", "current", "absent"} for t in self.targets
        )


@dataclass(frozen=True, slots=True)
class BundleCheck:
    """One current health check, never a persisted installation assertion."""

    kind: str
    agent: str
    status: str
    build_revision: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BundleDiagnostics:
    """Build integrity and manager availability, not installation convergence."""

    bundle_id: str
    checks: tuple[BundleCheck, ...]

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.status == "ok" for check in self.checks)
