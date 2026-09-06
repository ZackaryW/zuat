"""Small atomic index, not a second journal or native-operation replay engine."""

import json
import re
from contextlib import contextmanager
from pathlib import Path

from zuat.gitcore.errors import RegistryLockedError
from zuat.gitcore.locking import registry_lock
from zuat.pub.bundles.models import (
    BundleBuild,
    BundleNotFoundError,
    BundleRecord,
    BundleStoreError,
    BundleTarget,
)
from zuat.utils.bundles.paths import reject_links
from zuat.utils.mutation import atomic_write
from zuat.utils.plugin_state import metadata_identifier

MAX_INDEX_BYTES = 8 * 1024 * 1024


def _token(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{0,127}", value
    ):
        raise ValueError("invalid bundle identifier")
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("invalid build digest")
    return value


def _plain_path(path):
    """Reject linked control paths before writes, including Windows junctions."""
    try:
        reject_links(path)
    except ValueError as error:
        raise BundleStoreError("linked compiler store path") from error


def _record(data):
    """Validate on every read; persisted JSON is not trusted executable input."""
    identifier = _token(data["bundle_id"])
    name = _token(data["name"])
    if data["source_kind"] not in {"local", "git"} or not isinstance(
        data["source"], str
    ):
        raise ValueError("invalid source binding")
    builds = []
    for item in data["builds"]:
        revision = _digest(item["build_revision"])
        version = metadata_identifier(item["version"])
        agents = tuple(item["agents"])
        if (
            not agents
            or len(set(agents)) != len(agents)
            or set(agents) - {"codex", "claude", "pi"}
        ):
            raise ValueError("invalid build agents")
        if set(item["digests"]) != set(agents):
            raise ValueError("missing build evidence")
        for digest in item["digests"].values():
            _digest(digest)
        commit = item.get("source_commit")
        if commit is not None and not re.fullmatch(r"[a-f0-9]{40,64}", commit):
            raise ValueError("invalid commit")
        builds.append(BundleBuild(identifier, revision, version, agents, commit))
    if len({b.build_revision for b in builds}) != len(builds):
        raise ValueError("duplicate build")
    targets = []
    for item in data["targets"]:
        agent = item["agent"]
        if agent not in {"codex", "claude", "pi", "kimi"}:
            raise ValueError("invalid target")
        plugin_id = metadata_identifier(item["plugin_id"])
        revision = item["build_revision"]
        if revision is not None:
            _digest(revision)
        status = item["status"]
        if status not in {
            "success",
            "current",
            "unsupported",
            "unavailable",
            "failed",
            "indeterminate",
            "absent",
        }:
            raise ValueError("invalid outcome")
        attempt = item.get("attempt")
        if attempt not in {None, "install", "update", "remove", "prepare"}:
            raise ValueError("invalid attempt")
        reason = item.get("reason")
        if reason is not None:
            _token(reason)
        if type(item.get("managed", False)) is not bool:
            raise ValueError("invalid managed installation flag")
        installed_version = item.get("installed_version")
        if installed_version is not None:
            metadata_identifier(installed_version)
        activation = item.get("activation")
        if activation not in {None, "active", "inactive", "partial", "unknown"}:
            raise ValueError("invalid activation")
        targets.append(
            BundleTarget(
                agent,
                plugin_id,
                revision,
                "indeterminate" if attempt else status,
                attempt,
                reason,
                installed_version,
                activation,
            )
        )
    if len({t.agent for t in targets}) != len(targets):
        raise ValueError("duplicate target")
    return BundleRecord(identifier, name, tuple(builds), tuple(targets))


class BundleStore:
    """Own compiler metadata only; merely opening it never invokes an agent."""

    def __init__(self, root: Path, tracking: Path):
        selected = root.expanduser().absolute()
        _plain_path(selected)
        self.root = selected.resolve()
        self.tracking = tracking.resolve()
        if self.root.is_relative_to(self.tracking) or self.tracking.is_relative_to(
            self.root
        ):
            raise BundleStoreError("compiler store and Git registry must be disjoint")
        self.index = self.root / "index.json"

    def _check(self):
        _plain_path(self.root)
        _plain_path(self.index)

    @contextmanager
    def locked(self):
        """One nonblocking writer; native interruption leaves its marker intact."""
        try:
            self._check()
            self.root.mkdir(parents=True, exist_ok=True)
            _plain_path(self.root / ".lock")
            with registry_lock(self.root / ".lock"):
                yield
        except (OSError, RegistryLockedError) as error:
            raise BundleStoreError("compiler store unavailable or locked") from error

    def read(self):
        self._check()
        if not self.index.exists():
            return {"schema": 1, "bundles": {}}
        try:
            if self.index.stat().st_size > MAX_INDEX_BYTES:
                raise ValueError("oversized index")
            data = json.loads(self.index.read_text(encoding="utf-8"))
            self._validate(data)
            return data
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise BundleStoreError("invalid compiler registration index") from error

    @staticmethod
    def _validate(data):
        if data["schema"] != 1 or not isinstance(data["bundles"], dict):
            raise ValueError("unsupported index")
        for identifier, record in data["bundles"].items():
            if _record(record).bundle_id != identifier:
                raise ValueError("mismatched bundle ID")

    def write(self, data):
        """Publish the whole small index only after validation, under caller lock."""
        try:
            self._check()
            self._validate(data)
            payload = json.dumps(data, sort_keys=True).encode("utf-8")
            if len(payload) > MAX_INDEX_BYTES:
                raise ValueError("oversized index")
            atomic_write(self.index, payload)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise BundleStoreError(
                "compiler registration could not be published"
            ) from error

    def get(self, identifier):
        try:
            _token(identifier)
            return _record(self.read()["bundles"][identifier])
        except (KeyError, ValueError) as error:
            raise BundleNotFoundError(
                "bundle is not registered in this store"
            ) from error

    def list(self):
        return tuple(
            _record(item) for _, item in sorted(self.read()["bundles"].items())
        )
