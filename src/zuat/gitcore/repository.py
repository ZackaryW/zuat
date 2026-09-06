"""Private append-only Git journal with a concrete checked-out projection."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from git import Actor, Git, Repo
from git.exc import BadName, GitCommandError, GitCommandNotFound, InvalidGitRepositoryError

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

AGENTS = ("codex", "claude", "kimi", "pi")
_AUTHOR = Actor("Zuat", "zuat@local.invalid")
_INITIAL_PROFILE = "default"


def resolve_app_root(root: str | Path | None = None) -> Path:
    """Resolve the isolated registry root without consulting a project tree."""
    if root is not None:
        return Path(root).expanduser().resolve()
    configured = os.environ.get("ZUAT_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    local_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_data) if local_data else Path.home() / ".local" / "share"
    return (base / "zuat" / "registry").resolve()


class GitRegistry:
    """Persist Zuat domain events while keeping every Git detail private."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = resolve_app_root(root)
        self._lock_path = self.root.parent / f".{self.root.name}.zuat.lock"
        self._mutex = threading.RLock()
        self._depth = 0
        self._check_git()
        self.repo = self._open_or_initialize()
        self._ensure_layout()
        self._recover_interrupted_operation()

    @staticmethod
    def _check_git() -> None:
        try:
            Git().version()
        except (GitCommandNotFound, OSError) as error:
            raise GitUnavailableError(
                "Git is required for Zuat and was not found on PATH"
            ) from error

    def _open_or_initialize(self) -> Repo:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            repo = Repo(self.root)
        except InvalidGitRepositoryError:
            try:
                repo = Repo.init(self.root, initial_branch="zuat-journal")
            except (GitCommandError, GitCommandNotFound, OSError) as error:
                raise RegistryError(f"failed to initialize registry: {error}") from error
        if repo.bare:
            raise RegistryError("Zuat registry requires private projected files")
        return repo

    def _ensure_layout(self) -> None:
        catalog_path = self.root / "catalog.json"
        selected_path = self.root / "selected-profile"
        if catalog_path.exists() and selected_path.exists():
            self._read_catalog()
            self._selected_profile()
            return
        try:
            self.repo.head.commit
        except (ValueError, BadName):
            pass
        else:
            raise RegistryError(
                "registry does not contain Zuat journal state; select a fresh root"
            )
        (self.root / "operations").mkdir(parents=True, exist_ok=True)
        for agent in AGENTS:
            self._initialize_agent_root(self.root / agent, agent)
        self._initialize_profile(_INITIAL_PROFILE)
        self._atomic_json(catalog_path, {})
        self._atomic_text(selected_path, f"{_INITIAL_PROFILE}\n")
        self._commit("zuat:initialize")

    @property
    def control_root(self) -> Path:
        root = Path(self.repo.git_dir).resolve() / "zuat"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @property
    def observation_root(self) -> Path:
        return self.root

    @property
    def recovery_marker(self) -> Path:
        return self.control_root / "pending-operation.json"

    @contextmanager
    def operation(self) -> Iterator[None]:
        """Serialize journal and native orchestration across processes."""
        with self._mutex:
            owns_file = self._depth == 0
            if owns_file:
                try:
                    descriptor = os.open(
                        self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                    )
                except FileExistsError as error:
                    raise RegistryLockedError(
                        f"registry is locked: {self._lock_path}"
                    ) from error
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(str(os.getpid()))
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if owns_file:
                    self._lock_path.unlink(missing_ok=True)

    def projected_state(self) -> ProjectedState:
        selected = self._selected_profile()
        profiles = tuple(
            Profile(
                name,
                selected=name == selected,
                assets=self._profile_asset_ids(name),
            )
            for name in self._profile_names()
        )
        catalog = tuple(
            self._asset_ref_from_dict(value)
            for _, value in sorted(self._read_catalog().items())
        )
        latest_event = next(
            (
                event
                for event in reversed(self.history())
                if event.kind is OperationKind.OBSERVE
            ),
            None,
        )
        latest = (
            latest_event.metadata.get("observation_identity")
            if latest_event is not None
            else None
        )
        return ProjectedState(
            selected_profile=selected,
            profiles=profiles,
            catalog=catalog,
            latest_observation=str(latest) if latest is not None else None,
        )

    def profiles(self) -> tuple[Profile, ...]:
        return self.projected_state().profiles

    def set_profile_assets(self, name: str, asset_ids: Sequence[str]) -> None:
        """Update a profile projection as part of an enclosing domain operation."""
        self.profile_root(name)
        known = {item.id for item in self.projected_state().catalog}
        unknown = sorted(set(asset_ids).difference(known))
        if unknown:
            raise RegistryError(f"unknown asset reference: {', '.join(unknown)}")
        requested = set(asset_ids)
        current = set(self._profile_asset_ids(name))
        for asset_id in sorted(current.difference(requested)):
            metadata_path, metadata = self._profile_metadata(name, asset_id)
            normalized = str(metadata["normalized_path"])
            self.remove_profile_asset(name, self.find_asset_ref(asset_id), normalized)
            metadata_path.unlink(missing_ok=True)
        catalog = self._read_catalog()
        by_id = {str(value["id"]): value for value in catalog.values()}
        for asset_id in sorted(requested.difference(current)):
            entry = by_id[asset_id]
            normalized = entry.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(
                    f"asset has no concrete repository path: {asset_id}"
                )
            target = self.profile_root(name).joinpath(*normalized.split("/"))
            if not target.exists():
                raise RegistryError(
                    f"profile asset payload is missing: {asset_id}"
                )
            self._write_profile_metadata(
                target,
                self._asset_ref_from_dict(entry),
                normalized,
                fingerprint=None,
            )

    def create_profile(
        self, name: str, *, from_profile: str | None = None
    ) -> JournalEvent:
        self._validate_profile(name)
        profiles = set(self._profile_names())
        if name in profiles:
            raise RegistryError(f"profile already exists: {name}")
        source = from_profile or self._selected_profile()
        if source not in profiles:
            raise RegistryError(f"unknown profile: {source}")
        source_root = self.profile_root(source)
        target_root = self._profile_root(name)
        if target_root.exists():
            raise RegistryError(f"profile storage already exists: {name}")
        shutil.copytree(source_root, target_root)
        self._atomic_json(target_root / ".profile.json", {"name": name})
        return self.append_event(
            OperationKind.PROFILE_CREATE,
            OperationOutcome.SUCCESS,
            profile=name,
            metadata={"from_profile": source},
        )

    def record_profile_switch(
        self,
        name: str,
        outcome: OperationOutcome | str,
        *,
        forced: bool = False,
        before: Sequence[AssetEvidence] = (),
        after: Sequence[AssetEvidence] = (),
        diagnostics: Sequence[str] = (),
        operation_id: str | None = None,
    ) -> JournalEvent:
        if name not in self._profile_names():
            raise RegistryError(f"unknown profile: {name}")
        selected_outcome = OperationOutcome(outcome)
        previous = self._selected_profile()
        if selected_outcome is OperationOutcome.SUCCESS:
            self._atomic_text(self.root / "selected-profile", f"{name}\n")
        return self.append_event(
            OperationKind.PROFILE_SWITCH,
            selected_outcome,
            profile=name,
            forced=forced,
            before=before,
            after=after,
            diagnostics=diagnostics,
            operation_id=operation_id,
            metadata={"from_profile": previous},
        )

    def record_asset_operation(
        self,
        kind: OperationKind | str,
        outcome: OperationOutcome | str,
        *,
        profile: str,
        before: Sequence[AssetEvidence],
        after: Sequence[AssetEvidence],
        forced: bool = False,
        diagnostics: Sequence[str] = (),
        operation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> JournalEvent:
        selected_kind = OperationKind(kind)
        if selected_kind not in {OperationKind.INSTALL, OperationKind.UNINSTALL}:
            raise RegistryError(f"not an asset lifecycle operation: {selected_kind}")
        selected_outcome = OperationOutcome(outcome)
        self.profile_root(profile)
        if selected_outcome is OperationOutcome.SUCCESS:
            self._apply_profile_evidence(profile, after)
        return self.append_event(
            selected_kind,
            selected_outcome,
            profile=profile,
            forced=forced,
            before=before,
            after=after,
            diagnostics=diagnostics,
            operation_id=operation_id,
            metadata=metadata,
        )

    def record_revert(
        self,
        operation_id: str,
        *,
        current: Sequence[AssetEvidence] = (),
        forced: bool = False,
        diagnostics: Sequence[str] = (),
        event_operation_id: str | None = None,
    ) -> JournalEvent:
        target = self.event(operation_id)
        if target.outcome is not OperationOutcome.SUCCESS:
            raise RegistryError("only a successful operation can be reverted")
        current_profile = self._selected_profile()
        is_profile_transition = target.kind is OperationKind.PROFILE_SWITCH or (
            target.kind is OperationKind.REVERT
            and target.metadata.get("state_kind") == "profile-switch"
        )
        if is_profile_transition:
            expected_profile = (
                str(target.profile)
                if target.kind is OperationKind.PROFILE_SWITCH
                else str(target.metadata.get("to_profile"))
            )
            if current_profile != expected_profile and not forced:
                message = (
                    f"profile changed after {target.operation_id}; force is required"
                )
                return self.append_event(
                    OperationKind.REVERT,
                    OperationOutcome.REJECTED,
                    profile=current_profile,
                    reverts=target.operation_id,
                    diagnostics=tuple((*diagnostics, message)),
                    metadata={
                        "reverted_kind": target.kind.value,
                        "state_kind": "profile-switch",
                    },
                    operation_id=event_operation_id,
                )
            if target.kind is OperationKind.PROFILE_SWITCH:
                destination = str(target.metadata["from_profile"])
            else:
                destination = str(target.metadata["from_profile"])
            if destination not in self._profile_names():
                raise RegistryError(f"unknown profile: {destination}")
            self._atomic_text(
                self.root / "selected-profile", f"{destination}\n"
            )
            return self.append_event(
                OperationKind.REVERT,
                OperationOutcome.SUCCESS,
                profile=destination,
                forced=forced,
                reverts=target.operation_id,
                diagnostics=diagnostics,
                metadata={
                    "reverted_kind": target.kind.value,
                    "state_kind": "profile-switch",
                    "from_profile": current_profile,
                    "to_profile": destination,
                },
                operation_id=event_operation_id,
            )

        if target.kind not in {
            OperationKind.INSTALL,
            OperationKind.UPDATE,
            OperationKind.UNINSTALL,
            OperationKind.REVERT,
        }:
            raise RegistryError(f"operation cannot be reverted: {target.kind.value}")
        profile = target.profile or current_profile
        inverse_before = tuple(current) if current else target.after
        inverse_after = target.before
        if current and self._evidence_conflicts(target.after, current) and not forced:
            message = (
                f"native state changed after {target.operation_id}; force is required"
            )
            return self.append_event(
                OperationKind.REVERT,
                OperationOutcome.REJECTED,
                profile=profile,
                before=current,
                reverts=target.operation_id,
                diagnostics=tuple((*diagnostics, message)),
                metadata={"reverted_kind": target.kind.value, "state_kind": "asset"},
                operation_id=event_operation_id,
            )
        self._apply_profile_evidence(profile, inverse_after)
        return self.append_event(
            OperationKind.REVERT,
            OperationOutcome.SUCCESS,
            profile=profile,
            forced=forced,
            before=inverse_before,
            after=inverse_after,
            reverts=target.operation_id,
            diagnostics=diagnostics,
            metadata={"reverted_kind": target.kind.value, "state_kind": "asset"},
            operation_id=event_operation_id,
        )

    def revert_conflicts(
        self, operation_id: str, current: Sequence[AssetEvidence] = ()
    ) -> bool:
        target = self.event(operation_id)
        selected = self._selected_profile()
        if target.kind is OperationKind.PROFILE_SWITCH:
            return selected != str(target.profile)
        if (
            target.kind is OperationKind.REVERT
            and target.metadata.get("state_kind") == "profile-switch"
        ):
            return selected != str(target.metadata.get("to_profile"))
        return bool(current) and self._evidence_conflicts(target.after, current)

    @staticmethod
    def _evidence_conflicts(
        expected: Sequence[AssetEvidence], current: Sequence[AssetEvidence]
    ) -> bool:
        actual = {item.ref.id: item for item in current}
        for item in expected:
            observed = actual.get(item.ref.id)
            if observed is None:
                if item.present:
                    return True
                continue
            if observed.present != item.present:
                return True
            if item.present and observed.fingerprint != item.fingerprint:
                return True
        return False

    def _apply_profile_evidence(
        self, profile: str, evidence: Sequence[AssetEvidence]
    ) -> None:
        current = set(self._profile_asset_ids(profile))
        for item in evidence:
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                catalog = self._read_catalog()
                entry = next(
                    (
                        value
                        for value in catalog.values()
                        if value.get("id") == item.ref.id
                    ),
                    None,
                )
                normalized = (
                    str(entry["normalized_path"])
                    if entry is not None
                    and isinstance(entry.get("normalized_path"), str)
                    else None
                )
            if item.present and item.authority is Authority.AUTHORITATIVE:
                if item.ref.id in current:
                    continue
                if normalized is None:
                    raise RegistryError(
                        f"asset has no concrete repository path: {item.ref.id}"
                    )
                if item.ref.kind == "plugin":
                    from zuat.utils.plugin_pointers import evidence_pointer
                    self.store_profile_pointer(profile, item.ref, normalized, evidence_pointer(item.evidence))
                    current.add(item.ref.id)
                    continue
                payload = self.asset_payload(item.ref, item.fingerprint)
                if not payload.exists():
                    raise RegistryError(
                        f"asset has no restorable payload: {item.ref.id}"
                    )
                assert item.fingerprint is not None
                self.store_profile_asset(
                    profile,
                    item.ref,
                    normalized,
                    payload,
                    item.fingerprint,
                )
                current.add(item.ref.id)
            elif item.ref.id in current:
                if normalized is None:
                    _, metadata = self._profile_metadata(profile, item.ref.id)
                    normalized = str(metadata["normalized_path"])
                self.remove_profile_asset(profile, item.ref, normalized)
                current.discard(item.ref.id)

    def append_event(
        self,
        kind: OperationKind | str,
        outcome: OperationOutcome | str,
        *,
        profile: str | None = None,
        forced: bool = False,
        before: Sequence[AssetEvidence] = (),
        after: Sequence[AssetEvidence] = (),
        reverts: str | None = None,
        completeness: str = "complete",
        diagnostics: Sequence[str] = (),
        metadata: dict[str, object] | None = None,
        operation_id: str | None = None,
    ) -> JournalEvent:
        from zuat.gitcore.plugin_safety import plugin_event, clean_metadata
        if plugin_event(before, after, metadata or {}):
            metadata = clean_metadata(metadata or {})
            if diagnostics:
                diagnostics = ("plugin operation failed; native details omitted",)
        events = self.history()
        selected_id = operation_id or new_operation_id()
        if any(event.operation_id == selected_id for event in events):
            raise RegistryError(f"operation identifier already exists: {selected_id}")
        event = JournalEvent(
            operation_id=selected_id,
            sequence=(events[-1].sequence + 1) if events else 1,
            kind=OperationKind(kind),
            outcome=OperationOutcome(outcome),
            profile=profile,
            forced=forced,
            before=tuple(before),
            after=tuple(after),
            reverts=reverts,
            completeness=completeness,
            diagnostics=tuple(diagnostics),
            metadata=dict(metadata or {}),
        )
        filename = f"{event.sequence:012d}-{event.operation_id}.json"
        self._atomic_json(self.root / "operations" / filename, event.to_dict())
        self._commit(f"zuat:{event.kind.value}:{event.operation_id}")
        return event

    def record_observation(
        self,
        assets: Sequence[AssetEvidence],
        *,
        agents: Sequence[str] | None = None,
        completeness: str = "complete",
        diagnostics: Sequence[str] = (),
        context: str | None = None,
    ) -> JournalEvent | None:
        """Append changed observation evidence without accepting profile intent."""
        if completeness not in {"complete", "partial", "indeterminate"}:
            raise RegistryError(f"unsupported observation completeness: {completeness}")
        ordered = tuple(sorted(assets, key=lambda item: item.ref.id))
        selected_agents = tuple(
            sorted(set(agents or (item.ref.agent for item in ordered)))
        )
        if any(agent not in AGENTS for agent in selected_agents):
            raise RegistryError("observation includes an unsupported agent")
        identity_payload = {
            "agents": list(selected_agents),
            "completeness": completeness,
            "assets": [item.to_dict() for item in ordered],
            "diagnostics": list(diagnostics),
            "context": context,
        }
        identity = hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        previous_event = next(
            (
                event
                for event in reversed(self.history())
                if event.kind is OperationKind.OBSERVE
            ),
            None,
        )
        if (
            previous_event is not None
            and previous_event.metadata.get("observation_identity") == identity
        ):
            return None

        before = self.latest_observation()
        self._record_catalog_paths(ordered)
        outcome = {
            "complete": OperationOutcome.SUCCESS,
            "partial": OperationOutcome.PARTIAL,
            "indeterminate": OperationOutcome.INDETERMINATE,
        }[completeness]
        return self.append_event(
            OperationKind.OBSERVE,
            outcome,
            profile=self._selected_profile(),
            before=before,
            after=ordered,
            completeness=completeness,
            diagnostics=diagnostics,
            metadata={
                "observation_agents": list(selected_agents),
                "observation_identity": identity,
                "observation_context": context,
            },
        )

    def latest_observation(self) -> tuple[AssetEvidence, ...]:
        retained: dict[str, AssetEvidence] = {}
        for event in self.history():
            if event.kind is not OperationKind.OBSERVE:
                continue
            if event.completeness == "complete":
                selected_agents = {
                    str(agent)
                    for agent in event.metadata.get("observation_agents", [])
                }
                if not selected_agents:
                    selected_agents = {item.ref.agent for item in event.after}
                retained = {
                    asset_id: item
                    for asset_id, item in retained.items()
                    if item.ref.agent not in selected_agents or item.evidence.get("ref", {}).get("context") not in {None, event.metadata.get("observation_context")}
                }
            retained.update({item.ref.id: item for item in event.after})
        return tuple(retained[key] for key in sorted(retained))

    def begin_operation(
        self,
        kind: OperationKind | str,
        *,
        profile: str | None,
        before: Sequence[AssetEvidence] = (),
        metadata: dict[str, object] | None = None,
        operation_id: str | None = None,
    ) -> str:
        """Persist crash-recovery evidence outside the journal projection."""
        from zuat.gitcore.plugin_safety import plugin_event, clean_metadata
        if plugin_event(before, (), metadata or {}):
            metadata = clean_metadata(metadata or {})
        if self.recovery_marker.exists():
            raise RegistryError("another native operation requires recovery")
        selected_id = operation_id or new_operation_id()
        self._atomic_json(
            self.recovery_marker,
            {
                "operation_id": selected_id,
                "kind": OperationKind(kind).value,
                "profile": profile,
                "before": [item.to_dict() for item in before],
                "metadata": dict(metadata or {}),
            },
        )
        return selected_id

    def finish_operation(self, operation_id: str, outcome: OperationOutcome) -> None:
        """Keep uncertain plugin mutations pending for native rediscovery."""
        if self.recovery_marker.exists() and outcome is not OperationOutcome.SUCCESS:
            marker = self._read_json(self.recovery_marker)
            if marker.get("metadata", {}).get("state_kind") == "plugin-lifecycle" or any(
                item.get("kind") == "plugin" or item.get("evidence", {}).get("provider") == "plugin"
                for item in marker.get("before", [])
            ):
                return
        self.clear_operation(operation_id)

    def clear_operation(self, operation_id: str) -> None:
        if not self.recovery_marker.exists():
            return
        marker = self._read_json(self.recovery_marker)
        if marker.get("operation_id") != operation_id:
            raise RegistryError("recovery marker belongs to a different operation")
        self.recovery_marker.unlink()

    def _recover_interrupted_operation(self) -> None:
        if not self.recovery_marker.exists():
            return
        marker = self._read_json(self.recovery_marker)
        if marker.get("metadata", {}).get("state_kind") == "plugin-lifecycle" or any(item.get("kind") == "plugin" for item in marker.get("before", [])):
            # Native plugin evidence can only be refreshed by orchestration.
            return
        try:
            interrupted_id = str(marker["operation_id"])
            interrupted_kind = str(marker["kind"])
            before = tuple(
                self._evidence_from_dict(item) for item in marker.get("before", [])
            )
            metadata = dict(marker.get("metadata", {}))
        except (KeyError, TypeError, ValueError) as error:
            raise RegistryError("operation recovery marker is invalid") from error
        metadata.update(
            {
                "interrupted_operation_id": interrupted_id,
                "interrupted_kind": interrupted_kind,
            }
        )
        self.append_event(
            OperationKind.RECOVERY,
            OperationOutcome.INDETERMINATE,
            profile=(str(marker["profile"]) if marker.get("profile") else None),
            before=before,
            diagnostics=("interrupted native operation requires fresh observation",),
            metadata=metadata,
        )
        self.recovery_marker.unlink()

    def history(self) -> tuple[JournalEvent, ...]:
        event_root = self.root / "operations"
        if not event_root.exists():
            return ()
        events = tuple(
            self._event_from_dict(self._read_json(path))
            for path in sorted(event_root.glob("*.json"))
        )
        expected = tuple(range(1, len(events) + 1))
        if tuple(item.sequence for item in events) != expected:
            raise RegistryError("journal event sequence is not contiguous")
        return events

    def event(self, operation_id: str) -> JournalEvent:
        try:
            return next(
                event for event in self.history() if event.operation_id == operation_id
            )
        except StopIteration as error:
            raise RegistryError(f"unknown operation: {operation_id}") from error

    def ensure_asset_ref(
        self, *, agent: str, kind: str, scope: str, locator: str
    ) -> AssetRef:
        if agent not in AGENTS:
            raise RegistryError(f"unsupported agent: {agent}")
        locator = self._safe_locator(locator)
        key = "\0".join((agent, kind, scope, locator))
        catalog = self._read_catalog()
        existing = catalog.get(key)
        if existing is not None:
            return self._asset_ref_from_dict(existing)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        ref = AssetRef(f"asset_{digest}", agent, kind, scope, locator)
        catalog[key] = ref.to_dict()
        self._write_catalog(catalog)
        return ref

    def find_asset_ref(self, asset_id: str) -> AssetRef:
        try:
            return next(
                item
                for item in self.projected_state().catalog
                if item.id == asset_id
            )
        except StopIteration as error:
            raise RegistryError(f"unknown asset reference: {asset_id}") from error

    def _profile_root(self, name: str) -> Path:
        self._validate_profile(name)
        return self.root / "profiles" / name

    def profile_root(self, name: str | None = None) -> Path:
        selected = name or self.projected_state().selected_profile
        root = self._profile_root(selected)
        if not root.exists():
            raise RegistryError(f"unknown profile: {selected}")
        return root

    def store_profile_asset(
        self,
        profile: str,
        ref: AssetRef,
        normalized_path: str,
        source: str | Path,
        fingerprint: str,
    ) -> Path:
        """Materialize verified desired payload into a profile and object archive."""
        source_path = Path(source).resolve()
        relative = self._safe_profile_asset_path(ref, normalized_path)
        target = self.profile_root(profile).joinpath(*relative.split("/"))
        if ref.kind == "plugin":
            from zuat.utils.plugin_pointers import read_pointer, write_pointer
            write_pointer(target, read_pointer(source_path))
        else:
            self._copy_asset(source_path, target)
        self._set_catalog_path(ref, relative)
        self._write_profile_metadata(
            target,
            ref,
            relative,
            fingerprint=fingerprint,
        )
        if ref.kind != "plugin":
            self.archive_asset(ref, relative, source_path, fingerprint)
        return target

    def store_profile_pointer(self, profile, ref, normalized_path, record):
        from zuat.utils.plugin_pointers import write_pointer, pointer_fingerprint
        relative = self._safe_profile_asset_path(ref, normalized_path)
        target = self.profile_root(profile).joinpath(*relative.split("/"))
        write_pointer(target, record)
        self._set_catalog_path(ref, relative)
        self._write_profile_metadata(target, ref, relative, fingerprint=pointer_fingerprint(record))
        return target

    def archive_asset(
        self,
        ref: AssetRef,
        normalized_path: str,
        source: str | Path,
        fingerprint: str,
    ) -> Path:
        relative = self._safe_profile_asset_path(ref, normalized_path)
        source_path = Path(source).resolve()
        if ref.kind == "plugin":
            from zuat.utils.plugin_pointers import read_pointer
            read_pointer(source_path)
            return source_path
        archive = self.asset_payload(ref, fingerprint)
        if not archive.exists():
            self._copy_asset(source_path, archive)
        self._atomic_json(
            archive.parent / "evidence.json",
            {
                "asset_ref": ref.id,
                "fingerprint": fingerprint,
                "normalized_path": relative,
            },
        )
        return archive

    def remove_profile_asset(
        self, profile: str, ref: AssetRef, normalized_path: str
    ) -> None:
        relative = self._safe_profile_asset_path(ref, normalized_path)
        target = self.profile_root(profile).joinpath(*relative.split("/"))
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        target.with_name(f"{target.name}.zuat.json").unlink(missing_ok=True)

    def asset_payload(self, ref: AssetRef, fingerprint: str | None) -> Path:
        if not fingerprint:
            raise RegistryError(f"asset has no restorable fingerprint: {ref.id}")
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        # Git already retains committed concrete payloads. This local cache is
        # private adapter machinery and must not add an opaque duplicate tree
        # to the human-browsable checked-out projection.
        return self.control_root / "payloads" / ref.id / digest / "payload"

    @classmethod
    def _safe_profile_asset_path(cls, ref: AssetRef, path: str) -> str:
        normalized = cls._safe_locator(path)
        expected = f"{ref.agent}/{ref.scope}/"
        if not normalized.startswith(expected):
            raise InvalidRegistryPathError(
                f"profile asset path does not match its reference: {path}"
            )
        return normalized

    @staticmethod
    def _copy_asset(source: Path, target: Path) -> None:
        if not source.exists() or source.is_symlink():
            raise InvalidRegistryPathError(f"unsafe asset source: {source}")
        if source.is_dir() and any(item.is_symlink() for item in source.rglob("*")):
            raise InvalidRegistryPathError(f"asset source contains a symbolic link: {source}")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        elif source.is_file():
            shutil.copy2(source, target)
        else:
            raise InvalidRegistryPathError(f"asset source is not a regular path: {source}")

    def _initialize_agent_root(self, root: Path, agent: str) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._atomic_json(root / ".agent.json", {"agent": agent})

    def _initialize_profile(self, name: str) -> None:
        root = self._profile_root(name)
        root.mkdir(parents=True, exist_ok=True)
        self._atomic_json(root / ".profile.json", {"name": name})
        for agent in AGENTS:
            self._initialize_agent_root(root / agent, agent)

    def _selected_profile(self) -> str:
        path = self.root / "selected-profile"
        try:
            selected = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise RegistryError(f"invalid selected profile marker: {path}") from error
        self._validate_profile(selected)
        if not self._profile_root(selected).is_dir():
            raise RegistryError(f"unknown selected profile: {selected}")
        return selected

    def _profile_names(self) -> tuple[str, ...]:
        root = self.root / "profiles"
        if not root.is_dir():
            raise RegistryError("registry profile storage is missing")
        names: list[str] = []
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or path.is_symlink():
                continue
            self._validate_profile(path.name)
            marker = self._read_json(path / ".profile.json")
            if marker.get("name") != path.name:
                raise RegistryError(f"profile marker is invalid: {path}")
            names.append(path.name)
        return tuple(names)

    def _profile_asset_ids(self, name: str) -> tuple[str, ...]:
        root = self.profile_root(name)
        assets: list[str] = []
        for metadata_path in sorted(root.rglob("*.zuat.json")):
            metadata = self._read_json(metadata_path)
            asset_id = metadata.get("asset_ref")
            normalized = metadata.get("normalized_path")
            if not isinstance(asset_id, str) or not isinstance(normalized, str):
                raise RegistryError(
                    f"profile asset metadata is invalid: {metadata_path}"
                )
            target_name = metadata_path.name[: -len(".zuat.json")]
            target = metadata_path.with_name(target_name)
            expected = root.joinpath(*self._safe_locator(normalized).split("/"))
            if target != expected or not target.exists():
                raise RegistryError(
                    f"profile asset metadata has no concrete payload: {metadata_path}"
                )
            assets.append(asset_id)
        if len(assets) != len(set(assets)):
            raise RegistryError(f"profile contains duplicate asset references: {name}")
        return tuple(sorted(assets))

    def _profile_metadata(
        self, name: str, asset_id: str
    ) -> tuple[Path, dict[str, object]]:
        root = self.profile_root(name)
        for path in root.rglob("*.zuat.json"):
            metadata = self._read_json(path)
            if metadata.get("asset_ref") == asset_id:
                return path, metadata
        raise RegistryError(f"profile does not contain asset: {asset_id}")

    def _write_profile_metadata(
        self,
        target: Path,
        ref: AssetRef,
        normalized_path: str,
        *,
        fingerprint: str | None,
    ) -> None:
        self._atomic_json(
            target.with_name(f"{target.name}.zuat.json"),
            {
                "asset_ref": ref.id,
                "agent": ref.agent,
                "kind": ref.kind,
                "scope": ref.scope,
                "native_locator": ref.locator,
                "normalized_path": self._safe_profile_asset_path(
                    ref, normalized_path
                ),
                "fingerprint": fingerprint,
            },
        )

    def _read_catalog(self) -> dict[str, dict[str, object]]:
        payload = self._read_json(self.root / "catalog.json")
        if not all(isinstance(key, str) and isinstance(value, dict) for key, value in payload.items()):
            raise RegistryError("registry asset catalog is invalid")
        return {str(key): dict(value) for key, value in payload.items()}

    def _write_catalog(self, catalog: dict[str, dict[str, object]]) -> None:
        self._atomic_json(self.root / "catalog.json", catalog)

    def _record_catalog_paths(self, evidence: Sequence[AssetEvidence]) -> None:
        catalog = self._read_catalog()
        changed = False
        by_id = {str(value.get("id")): value for value in catalog.values()}
        for item in evidence:
            normalized = item.evidence.get("normalized_path")
            entry = by_id.get(item.ref.id)
            if not isinstance(normalized, str) or entry is None:
                continue
            safe = self._safe_profile_asset_path(item.ref, normalized)
            if entry.get("normalized_path") != safe:
                entry["normalized_path"] = safe
                changed = True
        if changed:
            self._write_catalog(catalog)

    def _set_catalog_path(self, ref: AssetRef, normalized_path: str) -> None:
        catalog = self._read_catalog()
        selected = next(
            (value for value in catalog.values() if value.get("id") == ref.id),
            None,
        )
        if selected is None:
            raise RegistryError(f"unknown asset reference: {ref.id}")
        safe = self._safe_profile_asset_path(ref, normalized_path)
        if selected.get("normalized_path") != safe:
            selected["normalized_path"] = safe
            self._write_catalog(catalog)

    def _commit(self, message: str) -> None:
        try:
            self.repo.git.add("-A", "--", ".")
            self.repo.index.commit(message, author=_AUTHOR, committer=_AUTHOR)
        except (GitCommandError, OSError) as error:
            raise RegistryError(f"failed to advance private journal: {error}") from error

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RegistryError(f"invalid registry document: {path}") from error
        if not isinstance(value, dict):
            raise RegistryError(f"invalid registry document: {path}")
        return value

    @staticmethod
    def _atomic_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)

    @staticmethod
    def _atomic_text(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _validate_profile(name: str) -> None:
        if (
            not name
            or name in {".", ".."}
            or name.startswith("-")
            or "/" in name
            or "\\" in name
        ):
            raise RegistryError(f"profile name is invalid: {name}")

    @staticmethod
    def _safe_locator(locator: str) -> str:
        raw = locator.replace("\\", "/")
        if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":") or "\0" in raw:
            raise InvalidRegistryPathError(f"unsafe native locator: {locator}")
        normalized = raw.strip("/")
        parts = normalized.split("/") if normalized else []
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise InvalidRegistryPathError(f"unsafe native locator: {locator}")
        return "/".join(parts)

    @staticmethod
    def _asset_ref_from_dict(value: object) -> AssetRef:
        if not isinstance(value, dict):
            raise RegistryError("registry asset reference is invalid")
        try:
            return AssetRef(
                id=str(value["id"]),
                agent=str(value["agent"]),
                kind=str(value["kind"]),
                scope=str(value["scope"]),
                locator=str(value["locator"]),
            )
        except KeyError as error:
            raise RegistryError("registry asset reference is incomplete") from error

    @classmethod
    def _evidence_from_dict(cls, value: object) -> AssetEvidence:
        if not isinstance(value, dict):
            raise RegistryError("journal asset evidence is invalid")
        ref = AssetRef(
            id=str(value["asset_ref"]),
            agent=str(value["agent"]),
            kind=str(value["kind"]),
            scope=str(value["scope"]),
            locator=str(value["locator"]),
        )
        evidence = dict(value.get("evidence", {}))
        if ref.kind == "plugin" or evidence.get("provider") == "plugin":
            from zuat.utils.plugin_pointers import clean_evidence
            from zuat.specs.interface import ResolutionError
            try:
                if clean_evidence(evidence) != evidence:
                    raise ValueError
            except (ResolutionError, ValueError) as error:
                raise RegistryError("incompatible plugin history; use a fresh registry") from error
        return AssetEvidence(
            ref=ref,
            fingerprint=(
                str(value["fingerprint"])
                if value.get("fingerprint") is not None
                else None
            ),
            authority=Authority(str(value["authority"])),
            present=bool(value.get("present", True)),
            complete=bool(value.get("complete", True)),
            evidence=evidence,
        )

    @classmethod
    def _event_from_dict(cls, value: dict[str, object]) -> JournalEvent:
        try:
            return JournalEvent(
                operation_id=str(value["operation_id"]),
                sequence=int(value["sequence"]),
                kind=OperationKind(str(value["kind"])),
                outcome=OperationOutcome(str(value["outcome"])),
                profile=(str(value["profile"]) if value.get("profile") else None),
                forced=bool(value.get("forced", False)),
                before=tuple(
                    cls._evidence_from_dict(item)
                    for item in value.get("before", [])
                ),
                after=tuple(
                    cls._evidence_from_dict(item)
                    for item in value.get("after", [])
                ),
                reverts=(str(value["reverts"]) if value.get("reverts") else None),
                completeness=str(value.get("completeness", "complete")),
                diagnostics=tuple(str(item) for item in value.get("diagnostics", [])),
                metadata=dict(value.get("metadata", {})),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RegistryError("journal event is invalid") from error

    def close(self) -> None:
        self.repo.close()

    def __enter__(self) -> GitRegistry:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["AGENTS", "GitRegistry", "resolve_app_root"]
