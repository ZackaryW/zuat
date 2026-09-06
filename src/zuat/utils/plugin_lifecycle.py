"""Agent-neutral subprocess lifecycle and verification mechanics."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from zuat.specs.native import (
    Agent,
    InvalidAssetError,
    PluginActivation,
    PluginLifecycleResult,
    PluginOperationError,
    PluginRecord,
    PluginRef,
    Scope,
    UnsupportedNativeOperation,
)
from zuat.utils.ownership import OwnershipRecord, OwnershipStore
from zuat.utils.process import ProcessRunner, SubprocessRunner
from zuat.utils.plugin_state import is_direct_source, metadata_identifier
from zuat.utils.contexts import project_context


def activation(enabled: object) -> PluginActivation:
    if enabled is True:
        return PluginActivation.ACTIVE
    if enabled is False:
        return PluginActivation.INACTIVE
    return PluginActivation.UNKNOWN


class CommandPluginAdapter:
    agent: Agent
    scopes: frozenset[Scope]
    environment_variable: str

    config_directory: Path
    direct_sources = False

    def requested_version(self, ref: PluginRef) -> str | None:
        return None

    def __init__(
        self,
        *,
        home: Path,
        store: OwnershipStore,
        runner: ProcessRunner | None = None,
        project_root: Path | None = None,
        trust_project: bool = False,
    ) -> None:
        self.home = Path(home).resolve()
        self.project_root = (
            Path(project_root).resolve() if project_root is not None else None
        )
        self.trust_project = trust_project
        self.discovery_diagnostics: tuple[str, ...] = ()
        self.unresolved_roots: tuple[Path, ...] = ()
        self.store = store
        self.runner = runner or SubprocessRunner()

    def discovery_args(self) -> tuple[str, ...]:
        raise NotImplementedError

    def install_args(self, ref: PluginRef) -> tuple[str, ...]:
        raise NotImplementedError

    def remove_args(self, ref: PluginRef) -> tuple[str, ...]:
        raise NotImplementedError

    def update_args(self, ref: PluginRef) -> tuple[tuple[str, ...], ...]:
        raise NotImplementedError

    def decode(self, output: str) -> tuple[PluginRecord, ...]:
        raise NotImplementedError

    def discover(self, *, include_available: bool = False) -> tuple[PluginRecord, ...]:
        if include_available and not self.capabilities.available:
            raise UnsupportedNativeOperation(
                "available plugin discovery is unsupported"
            )
        self.discovery_diagnostics = ()
        self.unresolved_roots = ()
        args = self.discovery_args()
        result = self._run((*args, "--available") if include_available else args)
        if result.returncode != 0:
            raise PluginOperationError("plugin discovery failed")
        records = []
        for item in self.decode(result.stdout):
            if not item.installed and not include_available:
                continue
            item = replace(item, ref=self.contextual_ref(item.ref))
            try:
                item.to_dict()
            except InvalidAssetError:
                self.discovery_diagnostics += (
                    "plugin identity is unresolved; native source details omitted",
                )
                if item.runtime_root is not None:
                    self.unresolved_roots += (item.runtime_root,)
                continue
            records.append(item)
        return tuple(records)

    def contextual_ref(self, ref):
        if ref.scope in {Scope.PROJECT, Scope.LOCAL}:
            context = project_context(self.project_root)
            if context is None:
                raise PluginOperationError(
                    "project plugin operations require a project root"
                )
            if ref.context is not None and ref.context != context:
                raise PluginOperationError("plugin belongs to another project context")
            return replace(ref, context=context)
        return ref

    def _find(
        self, records: tuple[PluginRecord, ...], ref: PluginRef
    ) -> PluginRecord | None:
        return next(
            (
                item
                for item in records
                if item.ref.native_ref == ref.native_ref and item.ref.scope is ref.scope
            ),
            None,
        )

    def _validate(self, ref: PluginRef, operation: str) -> None:
        if ref.agent is not self.agent:
            raise PluginOperationError("plugin reference belongs to another agent")
        if not self.capabilities.supports(operation, ref.scope):
            raise UnsupportedNativeOperation(
                f"{self.agent.value} does not support plugin scope {ref.scope.value}"
            )
        self.contextual_ref(ref)

    def validate_install(self, ref: PluginRef, *, trust: bool = False) -> None:
        self._validate(ref, "install")
        direct = is_direct_source(ref.native_ref)
        if direct and not trust:
            raise PluginOperationError(
                "direct URL, Git, and local plugin sources require trust"
            )
        if direct and not self.direct_sources:
            raise UnsupportedNativeOperation(
                "native manager requires a configured catalog reference"
            )
        if not direct:
            try:
                metadata_identifier(ref.native_ref)
            except ValueError as error:
                raise PluginOperationError("unsupported plugin reference") from error

    def install(self, ref: PluginRef, *, trust: bool = False) -> PluginLifecycleResult:
        self.validate_install(ref, trust=trust)
        before = self._find(self.discover(), ref)
        if before is not None:
            self._save_provenance(ref, before)
            return PluginLifecycleResult("install", ref, "current", before, before)
        result = self._run(self.install_args(ref))
        if result.returncode != 0:
            raise PluginOperationError("plugin install failed")
        try:
            after = self._find(self.discover(), ref)
        except PluginOperationError:
            return PluginLifecycleResult("install", ref, "indeterminate", before, None)
        if after is None:
            return PluginLifecycleResult("install", ref, "indeterminate", before, None)
        status = "installed"
        if status == "installed":
            self._save_provenance(ref, after)
        return PluginLifecycleResult("install", ref, status, before, after)

    def remove(self, ref: PluginRef) -> PluginLifecycleResult:
        self._validate(ref, "remove")
        before = self._find(self.discover(), ref)
        if before is None:
            return PluginLifecycleResult("remove", ref, "removed", None, None)
        result = self._run(self.remove_args(ref))
        if result.returncode != 0:
            raise PluginOperationError("plugin removal failed")
        try:
            after = self._find(self.discover(), ref)
        except PluginOperationError:
            return PluginLifecycleResult("remove", ref, "partial", before, None)
        if after is not None:
            return PluginLifecycleResult("remove", ref, "indeterminate", before, after)
        self._provenance_store(ref).remove("plugin", ref.native_ref, ref.scope.value)
        return PluginLifecycleResult("remove", ref, "removed", before, None)

    def update(self, ref: PluginRef) -> PluginLifecycleResult:
        self._validate(ref, "update")
        before = self._find(self.discover(), ref)
        if before is None:
            raise PluginOperationError("plugin is absent from authoritative state")
        for args in self.update_args(ref):
            result = self._run(args)
            if result.returncode != 0:
                raise PluginOperationError("plugin update failed")
        try:
            after = self._find(self.discover(), ref)
        except PluginOperationError:
            return PluginLifecycleResult("update", ref, "partial", before, None)
        if after is None:
            return PluginLifecycleResult("update", ref, "partial", before, None)
        status = (
            "current"
            if before.installed_version == after.installed_version
            else "updated"
        )
        if before.revision is None or after.revision is None:
            status = "partial"
        elif status in {"current", "updated"}:
            self._save_provenance(ref, after)
        return PluginLifecycleResult("update", ref, status, before, after)

    def _save_provenance(self, ref: PluginRef, record: PluginRecord) -> None:
        ref = record.ref
        fingerprint = record.installed_version or "plugin"
        self._provenance_store(ref).save(
            OwnershipRecord(
                self.agent.value,
                "plugin",
                ref.native_ref,
                ref.scope.value,
                ref.native_ref,
                fingerprint,
                record.to_dict(),
            )
        )

    def _provenance_store(self, ref):
        selected = self.contextual_ref(ref)
        if selected.context is None:
            return self.store
        return self.store.for_context(selected.context)

    def preflight(
        self, ref: PluginRef, operation: str, *, desired: PluginRecord | None = None
    ) -> None:
        self._validate(ref, operation)
        if desired is not None:
            current = self._find(self.discover(), ref)
            if current is not None and current.to_dict() == desired.to_dict():
                return
            if desired.revision is None:
                raise UnsupportedNativeOperation("plugin revision is unresolved")
            raise UnsupportedNativeOperation(
                "exact plugin revision or activation restoration is unsupported"
            )

    def reconcile(self, desired: PluginRecord) -> PluginLifecycleResult:
        self.preflight(desired.ref, "install", desired=desired)
        return self.install(desired.ref)

    def _run(self, args: tuple[str, ...]):
        try:
            return self.runner.run(
                args,
                cwd=self.project_root or self.home,
                environment={
                    self.environment_variable: str(self.home / self.config_directory)
                },
            )
        except OSError as error:
            raise PluginOperationError("plugin manager unavailable") from error
