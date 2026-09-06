"""Zuat-private ownership records and plugin receipts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from zuat.specs.native import InvalidAssetError, Scope
from zuat.utils.mutation import atomic_write


@dataclass(frozen=True, slots=True)
class OwnershipRecord:
    agent: str
    kind: str
    name: str
    scope: str
    destination: str
    fingerprint: str
    fragment: object | None = None
    native_locator: str | None = None

    def __post_init__(self) -> None:
        Scope(self.scope)
        if not isinstance(self.destination, str) or not self.destination:
            raise ValueError("ownership destination must be a nonempty path")
        if self.native_locator is not None and not isinstance(self.native_locator, str):
            raise ValueError("ownership locator must be text")


class OwnershipStore:
    def __init__(self, root: Path, agent: str) -> None:
        self.root = Path(root).resolve() / agent
        self.agent = agent

    def for_context(self, context: str) -> OwnershipStore:
        return OwnershipStore(self.root.parent / "contexts" / context, self.agent)

    def _path(self, kind: str, name: str, scope: str) -> Path:
        digest = sha256(name.encode("utf-8")).hexdigest()[:16]
        return self.root / kind / scope / f"{digest}.json"

    def save(self, record: OwnershipRecord) -> None:
        if record.agent != self.agent:
            raise InvalidAssetError("ownership record belongs to another agent")
        payload = json.dumps(asdict(record), indent=2, sort_keys=True).encode("utf-8") + b"\n"
        atomic_write(self._path(record.kind, record.name, record.scope), payload)

    def load(self, kind: str, name: str, scope: str = "user") -> OwnershipRecord | None:
        path = self._path(kind, name, scope)
        if not path.is_file() or path.is_symlink():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = OwnershipRecord(**payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise InvalidAssetError(f"invalid Zuat ownership record: {path}") from error
        if record.agent != self.agent or record.kind != kind or record.name != name or record.scope != scope:
            raise InvalidAssetError(f"mismatched Zuat ownership record: {path}")
        return record

    def remove(self, kind: str, name: str, scope: str = "user") -> None:
        self._path(kind, name, scope).unlink(missing_ok=True)

    def records(self, kind: str | None = None) -> tuple[OwnershipRecord, ...]:
        base = self.root / kind if kind else self.root
        if not base.is_dir() or base.is_symlink():
            return ()
        found: list[OwnershipRecord] = []
        for path in sorted(base.rglob("*.json")):
            if path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                record = OwnershipRecord(**payload)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if record.agent == self.agent and (kind is None or record.kind == kind):
                found.append(record)
        return tuple(found)
