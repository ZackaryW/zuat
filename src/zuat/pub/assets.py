"""Focused public orchestration for independently managed source assets."""

import tempfile
from dataclasses import asdict
from pathlib import Path

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    OperationKind,
    OperationOutcome,
    RegistryError,
)
from zuat.pub.models import AssetInspection, OperationResult, OperationStatus
from zuat.pub.results import failed
from zuat.specs.interface import AssetKind, ResolutionError
from zuat.specs.native import UnsupportedNativeOperation
from zuat.utils.contexts import project_context, scope_path
from zuat.utils.mutation import atomic_write, mirror_files


class AssetOperations:
    """Source-relative inspection and update, sharing the ordinary recovery path.

    Targeting stays with the resolver; this coordinator owns intent, before-state
    capture, verification, and publication under the registry lock.
    """

    def __init__(self, service):
        self.service = service

    def pending_status(self):
        """Expose interrupted intent before broad observation can imply convergence.

        A matching native projection alone cannot prove that receipt and profile
        publication completed. Leave recovery explicit until those agree.
        """
        registry = self.service.registry
        if not registry.recovery_marker.exists():
            return None
        pending = registry._read_json(registry.recovery_marker)
        if pending.get("metadata", {}).get("state_kind") != "asset-update":
            return None
        return OperationResult(
            "status",
            OperationStatus.PARTIAL,
            operation_id=pending["operation_id"],
            profile=pending.get("profile"),
            completeness="partial",
            diagnostics=(
                "unresolved asset operation; restore its operation ID using the original project context",
            ),
            data={
                "pending_operation_id": pending["operation_id"],
                "recovery_required": True,
            },
        )

    def target(self, asset):
        """Resolve native identity without registering or adopting the candidate.

        An explicit reference must agree with source, scope, and locator. Inspection
        and update share this gate so inspection cannot authorize a different target.
        """
        service = self.service
        service._observations.validate_context_catalog()
        if not asset.source:
            raise ResolutionError("source is required")
        ref = None
        if asset.asset_ref:
            service._observations.validate_refs((asset.asset_ref,))
            ref = service.registry.find_asset_ref(asset.asset_ref)
            if (ref.agent, ref.kind, ref.scope) != (
                asset.agent,
                asset.kind,
                asset.scope,
            ):
                raise ResolutionError(
                    "source and reference identify different installations"
                )
        native = service._resolver(asset.agent).inspect_asset(
            Path(asset.source),
            AssetKind(asset.kind),
            asset.scope,
            name=asset.name,
            locator=asset.locator or (ref.locator if ref else None),
        )
        if ref is not None and ref.locator != native.asset.evidence["native_locator"]:
            raise ResolutionError(
                "source locator and reference identify different installations"
            )
        if ref is None:
            ref = next(
                (
                    item
                    for item in service.registry.projected_state().catalog
                    if (item.agent, item.kind, item.scope, item.locator)
                    == (
                        asset.agent,
                        asset.kind,
                        asset.scope,
                        native.asset.evidence["native_locator"],
                    )
                ),
                None,
            )
        return native, ref

    def inspect(self, asset):
        """Translate targeted native evidence without requiring whole-agent discovery.

        An independently verified receipt can remain inspectable while unrelated
        plugin inventory is offline. Matching source bytes never grant ownership.
        """
        try:
            native, ref = self.target(asset)
            return AssetInspection(
                native.classification,
                asset.agent,
                asset.kind,
                native.asset.name,
                asset.scope,
                asset_ref=ref,
                source_fingerprint=native.source.fingerprint,
                observed_fingerprint=native.observed_fingerprint,
                baseline_fingerprint=native.record.fingerprint
                if native.record
                else None,
                owned=native.record is not None,
                ownership_evidence=("verified independent receipt",)
                if native.record
                else (),
                source_matches=native.observed_fingerprint == native.source.fingerprint
                if native.observed_fingerprint
                else None,
            )
        except (ResolutionError, RegistryError, OSError, ValueError) as error:
            return AssetInspection(
                "unsupported"
                if isinstance(error, UnsupportedNativeOperation)
                else "indeterminate",
                asset.agent,
                asset.kind,
                asset.name,
                asset.scope,
                completeness="partial",
                diagnostics=(str(error),),
            )

    def update(self, asset, *, force=False):
        """Capture, replace, verify, and publish as one recoverable operation.

        The lock serializes Zuat callers, not external editors: capture and recheck
        before intent, then verify after replacement. Keep actual before content
        and the owned baseline separately so force remains reversible without
        silently adopting local or foreign content.
        """
        service = self.service
        registry = service.registry
        operation_id = None
        before = ()
        try:
            with registry.operation(), tempfile.TemporaryDirectory() as temporary:
                native, ref = self.target(asset)
                if native.classification == "current":
                    return OperationResult(
                        "update-asset", OperationStatus.SUCCESS, data={"changed": False}
                    )
                if native.classification == "absent":
                    raise ResolutionError("target is absent; use install")
                if native.classification in {"unowned", "conflict"} and not force:
                    raise ResolutionError(
                        "force is required for unowned or conflicting replacement"
                    )
                resolver = service._resolver(asset.agent)
                ref = ref or registry.ensure_asset_ref(
                    agent=asset.agent,
                    kind=asset.kind,
                    scope=asset.scope,
                    locator=native.asset.evidence["native_locator"],
                )
                plural = "skills" if asset.kind == "skill" else "hooks"
                filename = (
                    native.asset.name
                    if asset.kind == "skill"
                    else native.source.path.name
                )
                intended = Path(temporary) / "intended" / filename
                # Publish these frozen bytes after verification, not the caller's
                # mutable source path, which another process may edit meanwhile.
                if asset.kind == "skill" or native.source.path.is_dir():
                    mirror_files(intended, native.source.files)
                else:
                    atomic_write(intended, native.source.files[0].content)
                normalized = (
                    Path(asset.agent)
                    / scope_path(asset.scope, project_context(service.project_root))
                    / plural
                    / filename
                ).as_posix()
                profile = registry.projected_state().selected_profile
                original = registry.profile_root(profile) / normalized
                baseline = (
                    service._projections.profile_fingerprint(ref, original)
                    if original.exists()
                    else None
                )
                if baseline:
                    registry.archive_asset(ref, normalized, original, baseline)
                # The managed baseline and actual native bytes may differ. Keep
                # both so restoration can recover a conflict without adopting it.
                ownership = asdict(native.record) if native.record else None
                if ownership:
                    ownership.pop("destination")
                metadata = {
                    "normalized_path": normalized,
                    "asset_name": native.asset.name,
                    "native_locator": ref.locator,
                    "ownership": ownership,
                    "owned_profile_fingerprint": baseline,
                }
                observed_fp = f"sha256:{native.observed_fingerprint}"
                authority = (
                    Authority.AUTHORITATIVE
                    if baseline == observed_fp
                    else Authority.CONFLICTING
                    if baseline
                    else Authority.UNAUTHORITATIVE
                )
                previous = AssetEvidence(ref, observed_fp, authority, evidence=metadata)
                before = (previous,)
                captured = Path(temporary) / filename
                resolver.capture_asset(native, captured)
                if (
                    service._projections.profile_fingerprint(ref, captured)
                    != observed_fp
                ):
                    raise ResolutionError("target changed while capturing before state")
                registry.archive_asset(ref, normalized, captured, observed_fp)
                # A registry lock cannot exclude native agent/editor writes.
                # Reject changed evidence before promising a recoverable mutation.
                refreshed, _ = self.target(asset)
                if (
                    refreshed.observed_fingerprint,
                    refreshed.record,
                    refreshed.source.fingerprint,
                ) != (
                    native.observed_fingerprint,
                    native.record,
                    native.source.fingerprint,
                ):
                    raise ResolutionError(
                        "target or source changed during update preflight"
                    )
                operation_id = registry.begin_operation(
                    OperationKind.UPDATE,
                    profile=profile,
                    before=before,
                    metadata={
                        "state_kind": "asset-update",
                        "project_context": project_context(service.project_root)
                        if asset.scope == "project"
                        else None,
                    },
                )
                resolver.replace_asset(native)
                verified, _ = self.target(asset)
                if (
                    verified.classification != "current"
                    or verified.source.fingerprint != native.source.fingerprint
                ):
                    raise ResolutionError("update postcondition verification failed")
                after = AssetEvidence(
                    ref,
                    f"sha256:{native.source.fingerprint}",
                    Authority.AUTHORITATIVE,
                    evidence={
                        "normalized_path": normalized,
                        "asset_name": native.asset.name,
                        "native_locator": ref.locator,
                    },
                )
                registry.store_profile_asset(
                    profile, ref, normalized, intended, after.fingerprint
                )
                event = registry.record_asset_operation(
                    OperationKind.UPDATE,
                    OperationOutcome.SUCCESS,
                    profile=profile,
                    before=before,
                    after=(after,),
                    forced=force,
                    operation_id=operation_id,
                    metadata={"state_kind": "asset-update"},
                )
                registry.finish_operation(operation_id, event.outcome)
                return OperationResult(
                    "update-asset",
                    OperationStatus.SUCCESS,
                    operation_id=event.operation_id,
                    profile=profile,
                    assets=(after,),
                    data={"changed": True},
                )
        except (ResolutionError, RegistryError, OSError, ValueError) as error:
            if operation_id:
                with registry.operation():
                    compensated = self.compensate(before, profile)
                    outcome = (
                        OperationOutcome.FAILED
                        if compensated
                        else OperationOutcome.INDETERMINATE
                    )
                    event = registry.append_event(
                        OperationKind.UPDATE,
                        outcome,
                        profile=profile,
                        before=before,
                        operation_id=operation_id,
                        diagnostics=(str(error),),
                        metadata={
                            "state_kind": "asset-update",
                            "compensated": compensated,
                        },
                    )
                    if compensated:
                        registry.clear_operation(operation_id)
                    return OperationResult(
                        "update-asset",
                        OperationStatus.FAILED
                        if compensated
                        else OperationStatus.PARTIAL,
                        operation_id=event.operation_id,
                        completeness="complete" if compensated else "partial",
                        diagnostics=(str(error),),
                    )
            return failed("update-asset", str(error))

    def compensate(self, before, profile):
        """Reuse inverse projections and native verification after a failed update.

        Do not call a public restore here: compensation belongs to the same update
        intent, not a second user operation. Failure leaves that intent actionable.
        """
        service = self.service
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                service._projections.write_inverse_profile(root, before)
                plans = service._projections.restore_plans(root, before)
                for plan in plans:
                    service._resolver(plan.agent).preflight(plan)
                    if not service._resolver(plan.agent).materialize(plan).verified:
                        return False
                service._projections.project_inverse_profile(profile, before)
                from zuat.pub.models import AssetInput

                for item in before:
                    # The archive object has a storage filename, so inspect the
                    # correctly named inverse projection, not its internal path.
                    actual, _ = self.target(
                        AssetInput(
                            item.ref.agent,
                            item.ref.kind,
                            scope=item.ref.scope,
                            source=str(root / item.evidence["normalized_path"]),
                            name=item.evidence["asset_name"],
                        )
                    )
                    if f"sha256:{actual.observed_fingerprint}" != item.fingerprint:
                        return False
                return True
        except (ResolutionError, RegistryError, OSError, ValueError):
            return False

    def restore_target(self, operation_id):
        """Expose interrupted update evidence to ordinary restoration without replay.

        Validate its original project before journaling recovery evidence. A crash
        may leave intent without an event, so retain the same opaque operation ID.
        """
        registry = self.service.registry
        if registry.recovery_marker.exists():
            pending = registry._read_json(registry.recovery_marker)
            if (
                pending["operation_id"] == operation_id
                and pending.get("metadata", {}).get("state_kind") == "asset-update"
            ):
                before = tuple(
                    registry._evidence_from_dict(item) for item in pending["before"]
                )
                self.service._observations.validate_refs(
                    tuple(item.ref.id for item in before)
                )
                try:
                    return registry.event(operation_id)
                except RegistryError:
                    return registry.append_event(
                        OperationKind.UPDATE,
                        OperationOutcome.INDETERMINATE,
                        profile=pending.get("profile"),
                        before=before,
                        operation_id=operation_id,
                        diagnostics=(
                            "interrupted update; explicit restoration requested",
                        ),
                        metadata=pending["metadata"],
                    )
        return registry.event(operation_id)

    def handoff_pending_restore(self, operation_id):
        """Clear matching intent only at the caller's verified recovery boundary.

        The caller must have verified a no-op or preflighted the replacement restore
        and hold the registry lock. Clearing earlier would lose rejected recovery.
        """
        registry = self.service.registry
        if registry.recovery_marker.exists():
            pending = registry._read_json(registry.recovery_marker)
            if (
                pending["operation_id"] == operation_id
                and pending.get("metadata", {}).get("state_kind") == "asset-update"
            ):
                registry.clear_operation(operation_id)

    def recovery_evidence(self, expected):
        """Measure actual content, receipt, and managed baseline independently.

        Rebuild a named temporary projection because archive filenames are storage
        identities, not native asset names. Never substitute expected ownership for
        the live receipt: that would make incomplete restoration verify itself.
        """
        from zuat.pub.models import AssetInput

        service = self.service
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service._projections.write_inverse_profile(root, (expected,))
            actual, _ = self.target(
                AssetInput(
                    expected.ref.agent,
                    expected.ref.kind,
                    scope=expected.ref.scope,
                    source=str(root / expected.evidence["normalized_path"]),
                    name=expected.evidence["asset_name"],
                )
            )
            value = (
                f"sha256:{actual.observed_fingerprint}"
                if actual.observed_fingerprint
                else None
            )
            profile = service.registry.projected_state().profile(
                service.registry.projected_state().selected_profile
            )
            authority = Authority.UNAUTHORITATIVE
            baseline = None
            if expected.ref.id in profile.assets:
                baseline = service._projections.profile_fingerprint(
                    expected.ref,
                    service.registry.profile_root()
                    / expected.evidence["normalized_path"],
                )
                authority = (
                    Authority.AUTHORITATIVE
                    if baseline == value
                    else Authority.CONFLICTING
                )
            return AssetEvidence(
                expected.ref,
                value,
                authority,
                present=value is not None,
                evidence={
                    **dict(expected.evidence),
                    "owned_profile_fingerprint": baseline,
                    "ownership": {
                        key: value
                        for key, value in asdict(actual.record).items()
                        if key != "destination"
                    }
                    if actual.record
                    else None,
                },
            )
