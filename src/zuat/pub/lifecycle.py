"""Install, adopt, and remove independently selected assets.

Selection and native mutation share the service's registry lock. Temporary
profiles are planning inputs, not published desired state: only verified native
results may update the selected profile. Source-aware updates live in assets.py."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    OperationKind,
    OperationOutcome,
    RegistryError,
)
from zuat.pub.models import (
    AssetSelector,
    OperationResult,
    OperationStatus,
    ZuatRequest,
)
from zuat.pub.results import (
    empty_bulk_result,
    failed,
    materialization_outcome,
)
from zuat.pub.selection import select_present, validate_agents
from zuat.specs.interface import (
    Asset,
    AssetKind,
    ConflictPolicy,
    ResolutionError,
    ResolutionPlan,
)
from zuat.utils.contexts import (
    contextual_locator,
    project_context,
    scope_path,
)
from zuat.utils.evidence import (
    absent_evidence,
)
from zuat.utils.payloads import (
    copy_asset,
    write_asset_metadata,
)

if TYPE_CHECKING:
    from zuat.pub.service import Zuat


class LifecycleOperations:
    """Focused orchestration using the facade's shared registry and resolver context."""

    def __init__(self, service: Zuat) -> None:
        self.service = service

    def adopt_all(
        self, selector: AssetSelector, *, force: bool = False
    ) -> OperationResult:
        """Select and install under one reentrant registry lock.

        Reusing install keeps one mutation event and its recovery boundary; the
        outer lock prevents another Zuat caller changing the selection in between.
        """
        service = self.service
        try:
            with service.registry.operation():
                assets, _, _, _ = service._observations.observe((selector.agent,))
                selected = select_present(assets, selector)
                if not selected:
                    return empty_bulk_result(
                        service.registry.projected_state().selected_profile, "adopt-all"
                    )
                result = service.install(
                    ZuatRequest(
                        agents=(selector.agent,),
                        asset_refs=tuple(item.ref.id for item in selected),
                        force=force,
                    )
                )
                return replace(result, operation="adopt-all")
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return failed("adopt-all", str(error))

    def uninstall_all(
        self, selector: AssetSelector, *, force: bool = False
    ) -> OperationResult:
        """Select and remove under the same lock used by single-operation removal.

        The bulk helper changes selection, not transaction or authority semantics.
        """
        service = self.service
        try:
            with service.registry.operation():
                assets, _, _, _ = service._observations.observe((selector.agent,))
                selected = select_present(assets, selector)
                if not selected:
                    return empty_bulk_result(
                        service.registry.projected_state().selected_profile,
                        "uninstall-all",
                    )
                result = service.uninstall(
                    ZuatRequest(
                        agents=(selector.agent,),
                        asset_refs=tuple(item.ref.id for item in selected),
                        force=force,
                    )
                )
                return replace(result, operation="uninstall-all")
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return failed("uninstall-all", str(error))

    def install(self, request: ZuatRequest) -> OperationResult:
        """Plan selected installs from a frozen profile, then publish verified state.

        All resolver preflights run before mutation intent. Archive actual observed
        content before native writes so a forced install can recover foreign or
        modified content, not just the previously managed package.
        """
        service = self.service
        if not request.assets and not request.asset_refs:
            return failed("install", "at least one asset is required")
        profile = request.profile or service.registry.projected_state().selected_profile
        if profile != service.registry.projected_state().selected_profile:
            return failed("install", "install requires the selected profile")
        operation_id: str | None = None
        try:
            with (
                service.registry.operation(),
                tempfile.TemporaryDirectory() as temporary,
            ):
                service._observations.validate_refs(request.asset_refs)
                observed, _, _, _ = service._observations.observe(request.agents)
                observed_by_id = {item.ref.id: item for item in observed}
                selected = self.install_sources(request, observed_by_id)
                before = tuple(item[3] for item in selected)
                temporary_profile = Path(temporary) / "profile"
                shutil.copytree(
                    service.registry.profile_root(profile), temporary_profile
                )
                for ref, source, normalized, _ in selected:
                    target = temporary_profile / Path(normalized)
                    if ref.kind == "skill" and source.is_file():
                        from zuat.utils.assets import collect_files
                        from zuat.utils.mutation import mirror_files

                        mirror_files(target, collect_files(source))
                    else:
                        copy_asset(source, target)
                    write_asset_metadata(target, ref)
                after = tuple(
                    AssetEvidence(
                        ref,
                        service._projections.profile_fingerprint(
                            ref, temporary_profile / Path(normalized)
                        ),
                        Authority.AUTHORITATIVE,
                        evidence={
                            **dict(previous.evidence),
                            "normalized_path": normalized,
                            "native_locator": ref.locator,
                            "asset_name": (
                                previous.evidence.get("asset_name")
                                or (
                                    (temporary_profile / Path(normalized)).stem
                                    if source.is_file()
                                    else (temporary_profile / Path(normalized)).name
                                )
                            ),
                        },
                    )
                    for ref, source, normalized, previous in selected
                )
                policy = (
                    ConflictPolicy.REPLACE if request.force else ConflictPolicy.ABORT
                )
                target_agents = tuple(dict.fromkeys(item[0].agent for item in selected))
                selected_keys: dict[str, set[tuple[str, str, str]]] = {}
                for ref, _, _, _ in selected:
                    selected_keys.setdefault(ref.agent, set()).add(
                        (ref.kind, ref.scope, ref.locator)
                    )
                complete_plans = tuple(
                    service._resolver(agent).plan(
                        temporary_profile, conflict_policy=policy
                    )
                    for agent in target_agents
                )
                plans = tuple(
                    ResolutionPlan(
                        plan.agent,
                        plan.root,
                        tuple(
                            action
                            for action in plan.actions
                            if action.operation == "install"
                            and (
                                action.asset.kind.value,
                                action.asset.scope,
                                str(action.asset.evidence.get("native_locator")),
                            )
                            in selected_keys[plan.agent]
                        ),
                        plan.conflict_policy,
                    )
                    for plan in complete_plans
                )
                try:
                    for plan in plans:
                        service._resolver(plan.agent).preflight(plan)
                except (ResolutionError, ValueError, OSError) as error:
                    event = service.registry.record_asset_operation(
                        OperationKind.INSTALL,
                        OperationOutcome.REJECTED,
                        profile=profile,
                        before=before,
                        after=after,
                        forced=request.force,
                        diagnostics=(str(error),),
                    )
                    return OperationResult(
                        operation="install",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=before,
                        diagnostics=(str(error),),
                    )

                operation_id = service.registry.begin_operation(
                    OperationKind.INSTALL,
                    profile=profile,
                    before=before,
                )
                for ref, source, normalized, previous in selected:
                    if previous.present and previous.fingerprint is not None:
                        observed_source = service.registry.observation_root / Path(
                            str(previous.evidence["normalized_path"])
                        )
                        service.registry.archive_asset(
                            ref,
                            normalized,
                            observed_source,
                            previous.fingerprint,
                        )
                materializations = tuple(
                    service._resolver(plan.agent).materialize(plan) for plan in plans
                )
                public_status, outcome = materialization_outcome(materializations)
                diagnostics = tuple(
                    message for item in materializations for message in item.diagnostics
                )
                if outcome is OperationOutcome.SUCCESS:
                    for (ref, source, normalized, _), item in zip(selected, after):
                        assert item.fingerprint is not None
                        service.registry.store_profile_asset(
                            profile,
                            ref,
                            normalized,
                            temporary_profile / Path(normalized),
                            item.fingerprint,
                        )
                    # Refresh the concrete top-level agent projection after the
                    # verified native mutation and before journaling its outcome.
                    service._observations.observe(target_agents)
                event = service.registry.record_asset_operation(
                    OperationKind.INSTALL,
                    outcome,
                    profile=profile,
                    before=before,
                    after=after,
                    forced=request.force,
                    diagnostics=diagnostics,
                    operation_id=operation_id,
                )
                service.registry.finish_operation(operation_id, event.outcome)
                return OperationResult(
                    operation="install",
                    status=public_status,
                    operation_id=event.operation_id,
                    profile=profile,
                    assets=after if outcome is OperationOutcome.SUCCESS else before,
                    materializations=materializations,
                    diagnostics=diagnostics,
                )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if operation_id is not None:
                try:
                    event = service.registry.record_asset_operation(
                        OperationKind.INSTALL,
                        OperationOutcome.FAILED,
                        profile=profile,
                        before=(),
                        after=(),
                        forced=request.force,
                        diagnostics=(str(error),),
                        operation_id=operation_id,
                    )
                    service.registry.finish_operation(operation_id, event.outcome)
                    return OperationResult(
                        "install",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return failed("install", str(error))

    def uninstall(self, request: ZuatRequest) -> OperationResult:
        """Remove selected native assets before dropping their managed projections.

        Archive observed content and record intent before deletion. Keeping the
        profile until native verification prevents a failed removal from appearing
        successful merely because its desired-state entry disappeared.
        """
        service = self.service
        if not request.asset_refs:
            return failed("uninstall", "at least one asset reference is required")
        profile = request.profile or service.registry.projected_state().selected_profile
        if profile != service.registry.projected_state().selected_profile:
            return failed("uninstall", "uninstall requires the selected profile")
        operation_id: str | None = None
        before: tuple[AssetEvidence, ...] = ()
        try:
            with service.registry.operation():
                service._observations.validate_refs(request.asset_refs)
                observed, _, _, _ = service._observations.observe(request.agents)
                observed_by_id = {item.ref.id: item for item in observed}
                before = tuple(
                    observed_by_id.get(asset_id)
                    or self.missing_observed_asset(asset_id)
                    for asset_id in request.asset_refs
                )
                missing = [item.ref.id for item in before if not item.present]
                if missing:
                    raise ResolutionError(
                        f"observed asset is not present: {', '.join(missing)}"
                    )
                conflicts = tuple(
                    item
                    for item in before
                    if item.authority is not Authority.AUTHORITATIVE
                )
                if conflicts and not request.force:
                    diagnostic = (
                        "force is required to remove unauthoritative or conflicting assets: "
                        + ", ".join(item.ref.id for item in conflicts)
                    )
                    after = tuple(absent_evidence(item) for item in before)
                    event = service.registry.record_asset_operation(
                        OperationKind.UNINSTALL,
                        OperationOutcome.REJECTED,
                        profile=profile,
                        before=before,
                        after=after,
                        diagnostics=(diagnostic,),
                    )
                    return OperationResult(
                        "uninstall",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=before,
                        diagnostics=(diagnostic,),
                    )
                native_assets: dict[str, list[Asset]] = {}
                for item in before:
                    normalized = item.evidence.get("normalized_path")
                    if not isinstance(normalized, str):
                        raise ResolutionError(
                            f"asset has no normalized payload: {item.ref.id}"
                        )
                    source = service.registry.observation_root / Path(normalized)
                    name = item.evidence.get("asset_name")
                    if not isinstance(name, str):
                        name = source.stem if source.is_file() else source.name
                    native_assets.setdefault(item.ref.agent, []).append(
                        Asset(
                            item.ref.agent,
                            AssetKind(item.ref.kind),
                            name,
                            source,
                            item.ref.scope,
                            dict(item.evidence),
                        )
                    )
                policy = (
                    ConflictPolicy.REPLACE if request.force else ConflictPolicy.ABORT
                )
                plans = tuple(
                    service._resolver(agent).plan_uninstall(
                        tuple(assets), conflict_policy=policy
                    )
                    for agent, assets in native_assets.items()
                )
                try:
                    for plan in plans:
                        service._resolver(plan.agent).preflight(plan)
                except (ResolutionError, ValueError, OSError) as error:
                    after = tuple(absent_evidence(item) for item in before)
                    event = service.registry.record_asset_operation(
                        OperationKind.UNINSTALL,
                        OperationOutcome.REJECTED,
                        profile=profile,
                        before=before,
                        after=after,
                        forced=request.force,
                        diagnostics=(str(error),),
                    )
                    return OperationResult(
                        "uninstall",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=before,
                        diagnostics=(str(error),),
                    )
                operation_id = service.registry.begin_operation(
                    OperationKind.UNINSTALL,
                    profile=profile,
                    before=before,
                )
                for item in before:
                    normalized = str(item.evidence["normalized_path"])
                    source = service.registry.observation_root / Path(normalized)
                    if item.fingerprint is not None:
                        service.registry.archive_asset(
                            item.ref,
                            normalized,
                            source,
                            item.fingerprint,
                        )
                materializations = tuple(
                    service._resolver(plan.agent).materialize(plan) for plan in plans
                )
                public_status, outcome = materialization_outcome(materializations)
                diagnostics = tuple(
                    message for item in materializations for message in item.diagnostics
                )
                after = tuple(absent_evidence(item) for item in before)
                if outcome is OperationOutcome.SUCCESS:
                    profile_ids = set(
                        service.registry.projected_state().profile(profile).assets
                    )
                    for item in before:
                        if item.ref.id in profile_ids:
                            service.registry.remove_profile_asset(
                                profile,
                                item.ref,
                                str(item.evidence["normalized_path"]),
                            )
                    # Native removal and desired-state removal have both been
                    # verified; project that new observation into the Git tree.
                    service._observations.observe(tuple(native_assets))
                event = service.registry.record_asset_operation(
                    OperationKind.UNINSTALL,
                    outcome,
                    profile=profile,
                    before=before,
                    after=after,
                    forced=request.force,
                    diagnostics=diagnostics,
                    operation_id=operation_id,
                )
                service.registry.finish_operation(operation_id, event.outcome)
                return OperationResult(
                    "uninstall",
                    public_status,
                    operation_id=event.operation_id,
                    profile=profile,
                    assets=after if outcome is OperationOutcome.SUCCESS else before,
                    materializations=materializations,
                    diagnostics=diagnostics,
                )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if operation_id is not None:
                try:
                    event = service.registry.record_asset_operation(
                        OperationKind.UNINSTALL,
                        OperationOutcome.FAILED,
                        profile=profile,
                        before=before,
                        after=(),
                        forced=request.force,
                        diagnostics=(str(error),),
                        operation_id=operation_id,
                    )
                    service.registry.finish_operation(operation_id, event.outcome)
                    return OperationResult(
                        "uninstall",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=before,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return failed("uninstall", str(error))

    def install_sources(
        self,
        request: ZuatRequest,
        observed: Mapping[str, AssetEvidence],
    ) -> tuple[tuple[object, Path, str, AssetEvidence], ...]:
        """Resolve source identity before constructing a temporary desired profile.

        Agent resolvers own native names and locators. Existing normalized paths
        are reused so adoption and packaged installation address the same asset;
        project identity must not be inferred from equal names or bytes.
        """
        service = self.service
        selected: list[tuple[object, Path, str, AssetEvidence]] = []
        allowed_agents = set(validate_agents(request.agents))
        for asset_id in request.asset_refs:
            ref = service.registry.find_asset_ref(asset_id)
            if ref.agent not in allowed_agents:
                raise ResolutionError(
                    f"asset is outside the selected agents: {asset_id}"
                )
            before = observed.get(asset_id)
            if before is None or not before.present:
                raise ResolutionError(f"observed asset is not present: {asset_id}")
            normalized = before.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise ResolutionError(f"asset has no normalized payload: {asset_id}")
            source = service.registry.observation_root / Path(normalized)
            selected.append((ref, source, normalized, before))
        for item in request.assets:
            if item.agent not in allowed_agents:
                raise ResolutionError(
                    f"asset is outside the selected agents: {item.agent}"
                )
            if item.kind not in {"skill", "hook", "plugin"}:
                raise ResolutionError(f"unsupported asset kind: {item.kind}")
            if not item.source:
                raise ResolutionError("install source is required")
            source = Path(item.source).resolve()
            if not source.exists():
                raise ResolutionError(f"install source does not exist: {source}")
            name = item.name or source.stem
            plural = {"skill": "skills", "hook": "hooks", "plugin": "plugins"}[
                item.kind
            ]
            locator = item.locator or f"{plural}/{name}"
            if item.kind != "plugin" and item.name is None and item.locator is None:
                resolved = service._resolver(item.agent).resolve_asset_source(
                    source, AssetKind(item.kind), item.scope
                )
                name = resolved.name
                locator = str(resolved.evidence["native_locator"])
            if item.kind != "plugin":
                locator = contextual_locator(
                    item.scope, locator, project_context(service.project_root)
                )
            ref = service.registry.ensure_asset_ref(
                agent=item.agent,
                kind=item.kind,
                scope=item.scope,
                locator=locator,
            )
            before = observed.get(
                ref.id,
                AssetEvidence(
                    ref,
                    None,
                    Authority.UNAUTHORITATIVE,
                    present=False,
                    evidence={},
                ),
            )
            previous_path = before.evidence.get("normalized_path")
            if isinstance(previous_path, str):
                normalized = previous_path
            else:
                filename = (
                    name
                    if item.kind == "skill"
                    else (
                        f"{name}{source.suffix}" if item.kind == "hook" else source.name
                    )
                )
                scoped = (
                    scope_path(item.scope, project_context(service.project_root))
                    if item.kind != "plugin"
                    else Path(item.scope)
                )
                normalized = (Path(item.agent) / scoped / plural / filename).as_posix()
                before = AssetEvidence(
                    before.ref,
                    before.fingerprint,
                    before.authority,
                    present=before.present,
                    complete=before.complete,
                    evidence={**dict(before.evidence), "normalized_path": normalized},
                )
            selected.append((ref, source, normalized, before))
        ids = [item[0].id for item in selected]
        if len(ids) != len(set(ids)):
            raise ResolutionError("assets must not be repeated")
        return tuple(selected)

    def missing_observed_asset(self, asset_id: str) -> AssetEvidence:
        """Represent an unobserved requested reference as conflicting absence.

        A catalog entry alone is not evidence that native content can be removed.
        """
        service = self.service
        ref = service.registry.find_asset_ref(asset_id)
        return AssetEvidence(
            ref,
            None,
            Authority.CONFLICTING,
            present=False,
        )
