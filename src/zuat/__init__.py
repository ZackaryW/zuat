"""Public package entry points for Zuat."""

from __future__ import annotations

from collections.abc import Sequence

_PUBLIC_TYPES = {
    "AssetEvidence",
    "AssetInput",
    "AssetSelector",
    "AssetRef",
    "Authority",
    "JournalEvent",
    "OperationResult",
    "OperationStatus",
    "Profile",
    "ZuatRequest",
}


def __getattr__(name: str):
    if name in _PUBLIC_TYPES:
        from zuat import pub

        return getattr(pub, name)
    raise AttributeError(name)


def main(args: Sequence[str] | None = None) -> None:
    """Run the optional command surface with actionable missing-extra guidance."""
    try:
        from zuat.cli import cli
    except ModuleNotFoundError as error:
        if error.name == "click":
            raise SystemExit(
                "zuat CLI is optional; install 'zuat[cli]' to use it."
            ) from None
        raise
    cli.main(args=list(args) if args is not None else None, prog_name="zuat")


__all__ = ["main", *_PUBLIC_TYPES]
