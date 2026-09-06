"""Private Git-backed journal with lazy adapter loading."""

from zuat.gitcore.errors import (
    GitUnavailableError,
    InvalidRegistryPathError,
    RegistryError,
    RegistryLockedError,
)
from zuat.gitcore.models import (
    AssetEvidence,
    AssetRef,
    Authority,
    JournalEvent,
    OperationKind,
    OperationOutcome,
    Profile,
    ProjectedState,
    new_operation_id,
)


def __getattr__(name: str):
    if name in {"GitRegistry", "resolve_app_root"}:
        from zuat.gitcore.repository import GitRegistry, resolve_app_root

        return {"GitRegistry": GitRegistry, "resolve_app_root": resolve_app_root}[name]
    raise AttributeError(name)


__all__ = [
    "AssetEvidence",
    "AssetRef",
    "Authority",
    "GitRegistry",
    "GitUnavailableError",
    "InvalidRegistryPathError",
    "JournalEvent",
    "OperationKind",
    "OperationOutcome",
    "Profile",
    "ProjectedState",
    "RegistryError",
    "RegistryLockedError",
    "new_operation_id",
    "resolve_app_root",
]
