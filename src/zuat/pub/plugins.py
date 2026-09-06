"""Public plugin operations coordinated through the existing domain journal."""

from dataclasses import replace

from zuat.gitcore import Authority, OperationKind, OperationOutcome, RegistryError
from zuat.pub.models import OperationResult, OperationStatus
from zuat.pub.results import failed
from zuat.specs.interface import ResolutionError
from zuat.specs.native import (
    InvalidAssetError,
    PluginOperationError,
    PluginRef,
    PluginRevision,
    UnsupportedNativeOperation,
)
from zuat.utils.evidence import absent_evidence
from zuat.utils.plugin_pointers import pointer_fingerprint


class PluginOperations:
    """Coordinate native plugin managers without taking ownership of plugin bodies.

    Resolvers own manager-specific commands. This layer persists only revision
    pointers and checks the selected installation plus its neighbors.
    """

    def __init__(self, service):
        self.service = service

    def discover(
        self, agent: str, *, include_available: bool = False
    ) -> OperationResult:
        """Combine manager records and journal observation under one registry lock.

        Preserve incomplete inventory as uncertainty; an unavailable manager is not
        proof that installed plugins or their contributions disappeared.
        """
        service = self.service
        try:
            with service.registry.operation():
                adapter = service._resolver(agent).plugin_adapter()
                records = adapter.discover(include_available=include_available)
                diagnostics = tuple(getattr(adapter, "discovery_diagnostics", ()))
                observed, event, completeness, observation_diagnostics = (
                    service._observations.observe((agent,))
                )
                diagnostics = tuple(
                    dict.fromkeys((*diagnostics, *observation_diagnostics))
                )
                return OperationResult(
                    "plugin-discover",
                    OperationStatus.PARTIAL if diagnostics else OperationStatus.SUCCESS,
                    plugins=records,
                    assets=tuple(
                        item
                        for item in observed
                        if item.ref.kind == "plugin"
                        or item.evidence.get("provider") == "plugin"
                    ),
                    operation_id=event.operation_id if event else None,
                    completeness="partial" if diagnostics else completeness,
                    diagnostics=diagnostics,
                )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if isinstance(error, UnsupportedNativeOperation):
                reason = "unsupported"
            elif (
                isinstance(error, PluginOperationError)
                and str(error) == "plugin manager unavailable"
            ):
                reason = "manager-unavailable"
            elif isinstance(error, PluginOperationError) and str(error) in {
                "Claude plugin inventory has an unsupported shape",
                "Codex plugin inventory has an unsupported shape",
                "Pi plugin inventory has an unsupported shape",
                "Pi plugin manifest has an unsupported shape",
                "Kimi plugin inventory has an unsupported shape",
            }:
                reason = "malformed-inventory"
            else:
                reason = "discovery-failed"
            return replace(failed("plugin-discover", reason), data={"reason": reason})

    def mutate(
        self,
        operation: str,
        ref: PluginRef,
        *,
        trust: bool = False,
        force: bool = False,
    ) -> OperationResult:
        """Bracket a native manager call with pointer observation and durable intent.

        Preflight and trust checks precede the marker; afterwards even command
        failure may mean native state changed. Publish pointers only after both the
        target revision and unaffected neighbors verify, otherwise retain recovery.
        Raw manager diagnostics and runtime paths must not enter durable history.
        """
        service = self.service
        registry = service.registry
        kind = {
            "install": OperationKind.INSTALL,
            "update": OperationKind.UPDATE,
            "remove": OperationKind.UNINSTALL,
        }[operation]
        marker = None
        before = ()
        profile = registry.projected_state().selected_profile
        try:
            with registry.operation():
                adapter = service._resolver(ref.agent.value).plugin_adapter()
                adapter.preflight(ref, operation)
                if operation == "install":
                    adapter.validate_install(ref, trust=trust)
                selected_ref = adapter.contextual_ref(ref)
                observed, _, completeness, _ = service._observations.observe(
                    (ref.agent.value,)
                )
                before = tuple(
                    item
                    for item in observed
                    if item.ref.kind == "plugin"
                    and item.ref.scope == ref.scope.value
                    and item.evidence.get("ref", {}).get("native_ref")
                    == selected_ref.native_ref
                    and item.evidence.get("ref", {}).get("context")
                    == selected_ref.context
                )

                def neighbors(items):
                    return {
                        item.ref.id: (item.fingerprint, item.present)
                        for item in items
                        if not (
                            item.ref.scope == selected_ref.scope
                            and item.evidence.get("ref", {}).get("native_ref")
                            == selected_ref.native_ref
                            and item.evidence.get("ref", {}).get("context")
                            == selected_ref.context
                        )
                    }

                other_before = neighbors(observed)
                if completeness != "complete":
                    raise PluginOperationError("plugin discovery is incomplete")
                requested_version = (
                    adapter.requested_version(ref) if operation == "install" else None
                )
                replaces_revision = requested_version is not None and any(
                    item.evidence.get("installed_version") != requested_version
                    for item in before
                )
                if (
                    (operation in {"remove", "update"} or replaces_revision)
                    and before
                    and not force
                    and any(
                        item.authority is not Authority.AUTHORITATIVE for item in before
                    )
                ):
                    raise PluginOperationError(
                        "force is required for unauthoritative plugin state"
                    )
                try:
                    durable_ref = selected_ref.to_dict()
                except InvalidAssetError:
                    # A runtime source may be usable without being safe to persist.
                    # Keep context/intent, never fall back to serializing its path.
                    durable_ref = None
                intended = (
                    PluginRevision(
                        ref.agent, selected_ref.native_ref, requested_version
                    ).to_dict()
                    if requested_version
                    else None
                )
                marker = registry.begin_operation(
                    kind,
                    profile=profile,
                    before=before,
                    metadata={
                        "state_kind": "plugin-lifecycle",
                        "plugin_agent": ref.agent.value,
                        "plugin_ref": durable_ref,
                        "plugin_context": selected_ref.context,
                        "intended_revision": intended,
                    },
                )
                result = (
                    adapter.install(ref, trust=trust)
                    if operation == "install"
                    else getattr(adapter, operation)(ref)
                )
                observed, _, completeness, _ = service._observations.observe(
                    (ref.agent.value,)
                )
                after = tuple(
                    item
                    for item in observed
                    if item.ref.kind == "plugin"
                    and item.ref.scope == ref.scope.value
                    and item.evidence.get("ref", {}).get("native_ref")
                    == selected_ref.native_ref
                    and item.evidence.get("ref", {}).get("context")
                    == selected_ref.context
                    and item.present
                )
                verified = (
                    # Manager success alone is insufficient: validate rediscovery
                    # and neighbors before publishing the new desired pointer.
                    result.verified
                    and completeness == "complete"
                    and neighbors(observed) == other_before
                )
                if operation == "remove":
                    verified = verified and not after
                else:
                    verified = (
                        verified
                        and result.after is not None
                        and bool(after)
                        and after[0].fingerprint == pointer_fingerprint(result.after)
                    )
                if verified:
                    if operation == "remove":
                        for item in before:
                            registry.remove_profile_asset(
                                profile, item.ref, item.evidence["normalized_path"]
                            )
                    else:
                        item = after[0]
                        registry.store_profile_pointer(
                            profile,
                            item.ref,
                            item.evidence["normalized_path"],
                            result.after,
                        )
                        after = (replace(item, authority=Authority.AUTHORITATIVE),)
                outcome = (
                    OperationOutcome.SUCCESS
                    if verified
                    else OperationOutcome.INDETERMINATE
                )
                if operation == "remove" and not after:
                    after = tuple(absent_evidence(item) for item in before)
                event = registry.append_event(
                    kind,
                    outcome,
                    profile=profile,
                    forced=force,
                    before=before,
                    after=after,
                    operation_id=marker,
                    metadata={"state_kind": "plugin-lifecycle"},
                )
                if verified:
                    registry.clear_operation(marker)
                return OperationResult(
                    "plugin-" + operation,
                    OperationStatus.SUCCESS if verified else OperationStatus.PARTIAL,
                    operation_id=event.operation_id,
                    profile=profile,
                    assets=after,
                    plugins=(result.after,) if result.after else (),
                    completeness="complete" if verified else "indeterminate",
                )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            # Native stderr and arbitrary exception text must never reach durable state.
            diagnostic = (
                str(error)
                if isinstance(error, PluginOperationError)
                else "plugin operation unavailable or unsupported"
            )
            safe = (
                diagnostic
                if diagnostic
                in {
                    "force is required for unauthoritative plugin state",
                    "plugin discovery is incomplete",
                    "direct URL, Git, and local plugin sources require trust",
                    "project plugin operations require project trust",
                }
                else "plugin operation unavailable or unsupported"
            )
            if marker is not None:
                if not any(
                    event.operation_id == marker for event in registry.history()
                ):
                    registry.append_event(
                        kind,
                        OperationOutcome.INDETERMINATE,
                        profile=profile,
                        before=before,
                        operation_id=marker,
                        diagnostics=(safe,),
                        metadata={"state_kind": "plugin-lifecycle"},
                    )
                return OperationResult(
                    "plugin-" + operation,
                    OperationStatus.PARTIAL,
                    operation_id=marker,
                    profile=profile,
                    assets=before,
                    completeness="indeterminate",
                    diagnostics=(safe,),
                )
            return failed("plugin-" + operation, safe)

    def recover(self):
        """Observe an interrupted manager call rather than replay its side effects.

        Require the original project before discovery. A complete rediscovery can
        release the marker but cannot retroactively certify the interrupted command,
        so the recovery event still reports an indeterminate outcome.
        """
        service = self.service
        registry = service.registry
        with registry.operation():
            if not registry.recovery_marker.exists():
                return OperationResult("plugin-recovery", OperationStatus.SUCCESS)
            pending = registry._read_json(registry.recovery_marker)
            before = tuple(
                registry._evidence_from_dict(item) for item in pending.get("before", [])
            )
            from zuat.utils.contexts import project_context

            expected = pending.get("metadata", {}).get("plugin_ref")
            refs = [
                item.evidence["ref"] for item in before if item.ref.kind == "plugin"
            ] + ([expected] if expected else [])
            if pending.get("metadata", {}).get("plugin_context") not in {
                None,
                project_context(service.project_root),
            } or any(
                ref.get("context") not in {None, project_context(service.project_root)}
                for ref in refs
            ):
                return failed(
                    "plugin-recovery", "recovery requires the original project context"
                )
            agents = tuple(
                sorted(
                    {item.ref.agent for item in before}
                    | (
                        {pending["metadata"]["plugin_agent"]}
                        if pending.get("metadata", {}).get("plugin_agent")
                        else set()
                    )
                )
            )
            if not agents:
                return failed("plugin-recovery", "recovery has no agent context")
            observed, _, completeness, _ = service._observations.observe(agents)
            targets = {item.ref.id for item in before}
            after = tuple(
                item
                for item in observed
                if item.ref.id in targets
                or (
                    not targets
                    and item.ref.kind == "plugin"
                    and (
                        not expected
                        or all(
                            item.evidence.get("ref", {}).get(key) == expected.get(key)
                            for key in ("native_ref", "scope", "context")
                        )
                    )
                )
            )
            event = registry.append_event(
                OperationKind.RECOVERY,
                OperationOutcome.INDETERMINATE,
                profile=pending.get("profile"),
                before=before,
                after=after,
                completeness="indeterminate",
                metadata={
                    "state_kind": "plugin-lifecycle",
                    "interrupted_operation_id": pending["operation_id"],
                    "interrupted_kind": pending["kind"],
                    "intended_revision": pending.get("metadata", {}).get(
                        "intended_revision"
                    ),
                },
            )
            if completeness == "complete":
                registry.clear_operation(pending["operation_id"])
            return OperationResult(
                "plugin-recovery",
                OperationStatus.PARTIAL,
                operation_id=event.operation_id,
                assets=after,
                completeness="indeterminate",
            )
