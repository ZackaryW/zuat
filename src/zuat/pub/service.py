"""Domain orchestration over the private journal and agent resolvers."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    GitRegistry,
    OperationKind,
    OperationOutcome,
    RegistryError,
)
from zuat.pub.models import (
    AssetInput,
    AssetSelector,
    OperationResult,
    OperationStatus,
    SUPPORTED_AGENTS,
    ZuatRequest,
)
from zuat.specs.interface import (
    AgentResolver,
    Asset,
    AssetKind,
    ConflictPolicy,
    Materialization,
    ResolutionError,
    ResolutionPlan,
)
from zuat.specs.registry import resolver_for


class Zuat:
    """Stateful public service suitable for Python callers and the CLI."""

    def __init__(
        self,
        *,
        registry: GitRegistry | None = None,
        root: str | Path | None = None,
        home: str | Path | None = None,
        project_root: str | Path | None = None,
        resolvers: Mapping[str, AgentResolver] | None = None,
        trust_project: bool = False,
    ) -> None:
        self.registry = registry or GitRegistry(root)
        self._owns_registry = registry is None
        self.home = Path(home).resolve() if home is not None else None
        self.project_root = (
            Path(project_root).resolve() if project_root is not None else None
        )
        self._resolvers = dict(resolvers or {})
        self.trust_project = trust_project
        from zuat.pub.artifacts import ArtifactOperations
        self._artifacts = ArtifactOperations(self)

    def register_artifact(self, extension):
        return self._artifacts.register(extension)

    def artifact_status(self, ref, identifier, *, revision=None):
        return self._artifacts.status(ref, identifier, revision=revision)

    def resolve_artifacts(self, agent, identifier):
        return self._artifacts.resolve(agent, identifier)

    def set_artifact_policy(self, ref, identifier, policy):
        return self._artifacts.set_policy(ref, identifier, policy)

    def clear_artifact_policy(self, ref, identifier):
        return self._artifacts.set_policy(ref, identifier, "inherit")

    def close(self) -> None:
        if self._owns_registry:
            self.registry.close()

    def __enter__(self) -> Zuat:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        try:
            with self.registry.operation():
                assets, event, completeness, diagnostics = self._observe(
                    request.agents
                )
            return OperationResult(
                operation="status",
                status=(
                    OperationStatus.PARTIAL
                    if completeness != "complete"
                    else self._observation_status(assets)
                ),
                operation_id=event.operation_id if event else None,
                profile=self.registry.projected_state().selected_profile,
                completeness=completeness,
                assets=assets,
                diagnostics=diagnostics,
            )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return self._failed("status", str(error))

    def discover_plugins(self, agent: str, *, include_available: bool = False):
        from zuat.pub.plugins import PluginOperations
        return PluginOperations(self).discover(agent, include_available=include_available)

    def install_plugin(self, ref, *, trust: bool = False, force: bool = False):
        from zuat.pub.plugins import PluginOperations
        return PluginOperations(self).mutate("install", ref, trust=trust, force=force)

    def update_plugin(self, ref, *, force: bool = False):
        from zuat.pub.plugins import PluginOperations
        return PluginOperations(self).mutate("update", ref, force=force)

    def remove_plugin(self, ref, *, force: bool = False):
        from zuat.pub.plugins import PluginOperations
        return PluginOperations(self).mutate("remove", ref, force=force)

    def recover_plugins(self):
        from zuat.pub.plugins import PluginOperations
        return PluginOperations(self).recover()

    def list_assets(self, selector: AssetSelector) -> OperationResult:
        """Observe and return only evidence matching ``selector``."""
        try:
            with self.registry.operation():
                assets, event, completeness, diagnostics = self._observe(
                    (selector.agent,)
                )
                selected = tuple(item for item in assets if selector.matches(item))
            return OperationResult(
                operation="asset-list",
                status=(
                    OperationStatus.PARTIAL
                    if completeness != "complete"
                    else self._observation_status(selected)
                ),
                operation_id=event.operation_id if event else None,
                profile=self.registry.projected_state().selected_profile,
                completeness=completeness,
                assets=selected,
                diagnostics=diagnostics,
            )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return self._failed("asset-list", str(error))

    def adopt_all(
        self, selector: AssetSelector, *, force: bool = False
    ) -> OperationResult:
        """Make every matching present asset authoritative in one transaction."""
        try:
            with self.registry.operation():
                assets, _, _, _ = self._observe((selector.agent,))
                selected = self._select_present(assets, selector)
                if not selected:
                    return self._empty_bulk_result("adopt-all")
                result = self.install(
                    ZuatRequest(
                        agents=(selector.agent,),
                        asset_refs=tuple(item.ref.id for item in selected),
                        force=force,
                    )
                )
                return replace(result, operation="adopt-all")
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return self._failed("adopt-all", str(error))

    def uninstall_all(
        self, selector: AssetSelector, *, force: bool = False
    ) -> OperationResult:
        """Remove every matching present asset in one transaction."""
        try:
            with self.registry.operation():
                assets, _, _, _ = self._observe((selector.agent,))
                selected = self._select_present(assets, selector)
                if not selected:
                    return self._empty_bulk_result("uninstall-all")
                result = self.uninstall(
                    ZuatRequest(
                        agents=(selector.agent,),
                        asset_refs=tuple(item.ref.id for item in selected),
                        force=force,
                    )
                )
                return replace(result, operation="uninstall-all")
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return self._failed("uninstall-all", str(error))

    def profiles(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        del request
        try:
            state = self.registry.projected_state()
            return OperationResult(
                operation="profile-list",
                status=OperationStatus.SUCCESS,
                profile=state.selected_profile,
                profiles=state.profiles,
            )
        except RegistryError as error:
            return self._failed("profile-list", str(error))

    def create_profile(self, request: ZuatRequest) -> OperationResult:
        if not request.profile:
            return self._failed("profile-create", "a profile is required")
        try:
            with self.registry.operation():
                self._observe(request.agents)
                event = self.registry.create_profile(request.profile)
                state = self.registry.projected_state()
            return OperationResult(
                operation="profile-create",
                status=OperationStatus.SUCCESS,
                operation_id=event.operation_id,
                profile=state.selected_profile,
                profiles=state.profiles,
            )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return self._failed("profile-create", str(error))

    def switch_profile(self, request: ZuatRequest) -> OperationResult:
        if not request.profile:
            return self._failed("profile-switch", "a profile is required")
        selected_agents = request.agents
        operation_id: str | None = None
        try:
            with self.registry.operation():
                before, _, _, _ = self._observe(selected_agents)
                target_root = self.registry.profile_root(request.profile)
                policy = (
                    ConflictPolicy.REPLACE if request.force else ConflictPolicy.ABORT
                )
                plans = tuple(
                    self._resolver(agent).plan(target_root, conflict_policy=policy)
                    for agent in self._agents(selected_agents)
                )
                try:
                    for plan in plans:
                        self._resolver(plan.agent).preflight(plan)
                except (ResolutionError, ValueError, OSError) as error:
                    event = self.registry.record_profile_switch(
                        request.profile,
                        OperationOutcome.REJECTED,
                        forced=request.force,
                        before=before,
                        diagnostics=(str(error),),
                    )
                    return OperationResult(
                        operation="profile-switch",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=self.registry.projected_state().selected_profile,
                        assets=before,
                        diagnostics=(str(error),),
                    )

                operation_id = self.registry.begin_operation(
                    OperationKind.PROFILE_SWITCH,
                    profile=request.profile,
                    before=before,
                )
                materializations = tuple(
                    self._resolver(plan.agent).materialize(plan) for plan in plans
                )
                public_status, outcome = self._materialization_outcome(materializations)
                diagnostics = tuple(
                    message
                    for item in materializations
                    for message in item.diagnostics
                )
                event = self.registry.record_profile_switch(
                    request.profile,
                    outcome,
                    forced=request.force,
                    before=before,
                    diagnostics=diagnostics,
                    operation_id=operation_id,
                )
                self.registry.finish_operation(operation_id, event.outcome)
                return OperationResult(
                    operation="profile-switch",
                    status=public_status,
                    operation_id=event.operation_id,
                    profile=self.registry.projected_state().selected_profile,
                    assets=before,
                    materializations=materializations,
                    diagnostics=diagnostics,
                )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if operation_id is not None:
                try:
                    event = self.registry.record_profile_switch(
                        request.profile,
                        OperationOutcome.FAILED,
                        forced=request.force,
                        diagnostics=(str(error),),
                        operation_id=operation_id,
                    )
                    self.registry.finish_operation(operation_id, event.outcome)
                    return OperationResult(
                        operation="profile-switch",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=self.registry.projected_state().selected_profile,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return self._failed("profile-switch", str(error))

    def history(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        del request
        try:
            state = self.registry.projected_state()
            return OperationResult(
                operation="history",
                status=OperationStatus.SUCCESS,
                profile=state.selected_profile,
                history=self.registry.history(),
            )
        except RegistryError as error:
            return self._failed("history", str(error))

    def install(self, request: ZuatRequest) -> OperationResult:
        if not request.assets and not request.asset_refs:
            return self._failed("install", "at least one asset is required")
        profile = request.profile or self.registry.projected_state().selected_profile
        if profile != self.registry.projected_state().selected_profile:
            return self._failed("install", "install requires the selected profile")
        operation_id: str | None = None
        try:
            with self.registry.operation(), tempfile.TemporaryDirectory() as temporary:
                observed, _, _, _ = self._observe(request.agents)
                observed_by_id = {item.ref.id: item for item in observed}
                selected = self._install_sources(request, observed_by_id)
                before = tuple(item[3] for item in selected)
                temporary_profile = Path(temporary) / "profile"
                shutil.copytree(self.registry.profile_root(profile), temporary_profile)
                for ref, source, normalized, _ in selected:
                    target = temporary_profile / Path(normalized)
                    self._copy_asset(source, target)
                    self._write_asset_metadata(target, ref)
                after = tuple(
                    AssetEvidence(
                        ref,
                        self._profile_fingerprint(
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
                    self._resolver(agent).plan(
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
                        self._resolver(plan.agent).preflight(plan)
                except (ResolutionError, ValueError, OSError) as error:
                    event = self.registry.record_asset_operation(
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

                operation_id = self.registry.begin_operation(
                    OperationKind.INSTALL,
                    profile=profile,
                    before=before,
                )
                for ref, source, normalized, previous in selected:
                    if previous.present and previous.fingerprint is not None:
                        observed_source = self.registry.observation_root / Path(
                            str(previous.evidence["normalized_path"])
                        )
                        self.registry.archive_asset(
                            ref,
                            normalized,
                            observed_source,
                            previous.fingerprint,
                        )
                materializations = tuple(
                    self._resolver(plan.agent).materialize(plan) for plan in plans
                )
                public_status, outcome = self._materialization_outcome(materializations)
                diagnostics = tuple(
                    message
                    for item in materializations
                    for message in item.diagnostics
                )
                if outcome is OperationOutcome.SUCCESS:
                    for (ref, source, normalized, _), item in zip(selected, after):
                        assert item.fingerprint is not None
                        self.registry.store_profile_asset(
                            profile, ref, normalized, source, item.fingerprint
                        )
                    # Refresh the concrete top-level agent projection after the
                    # verified native mutation and before journaling its outcome.
                    self._observe(target_agents)
                event = self.registry.record_asset_operation(
                    OperationKind.INSTALL,
                    outcome,
                    profile=profile,
                    before=before,
                    after=after,
                    forced=request.force,
                    diagnostics=diagnostics,
                    operation_id=operation_id,
                )
                self.registry.finish_operation(operation_id, event.outcome)
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
                    event = self.registry.record_asset_operation(
                        OperationKind.INSTALL,
                        OperationOutcome.FAILED,
                        profile=profile,
                        before=(),
                        after=(),
                        forced=request.force,
                        diagnostics=(str(error),),
                        operation_id=operation_id,
                    )
                    self.registry.finish_operation(operation_id, event.outcome)
                    return OperationResult(
                        "install",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return self._failed("install", str(error))

    def uninstall(self, request: ZuatRequest) -> OperationResult:
        if not request.asset_refs:
            return self._failed("uninstall", "at least one asset reference is required")
        profile = request.profile or self.registry.projected_state().selected_profile
        if profile != self.registry.projected_state().selected_profile:
            return self._failed("uninstall", "uninstall requires the selected profile")
        operation_id: str | None = None
        before: tuple[AssetEvidence, ...] = ()
        try:
            with self.registry.operation():
                observed, _, _, _ = self._observe(request.agents)
                observed_by_id = {item.ref.id: item for item in observed}
                before = tuple(
                    observed_by_id.get(asset_id)
                    or self._missing_observed_asset(asset_id)
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
                    after = tuple(self._absent_evidence(item) for item in before)
                    event = self.registry.record_asset_operation(
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
                    source = self.registry.observation_root / Path(normalized)
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
                    self._resolver(agent).plan_uninstall(
                        tuple(assets), conflict_policy=policy
                    )
                    for agent, assets in native_assets.items()
                )
                try:
                    for plan in plans:
                        self._resolver(plan.agent).preflight(plan)
                except (ResolutionError, ValueError, OSError) as error:
                    after = tuple(self._absent_evidence(item) for item in before)
                    event = self.registry.record_asset_operation(
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
                operation_id = self.registry.begin_operation(
                    OperationKind.UNINSTALL,
                    profile=profile,
                    before=before,
                )
                for item in before:
                    normalized = str(item.evidence["normalized_path"])
                    source = self.registry.observation_root / Path(normalized)
                    if item.fingerprint is not None:
                        self.registry.archive_asset(
                            item.ref,
                            normalized,
                            source,
                            item.fingerprint,
                        )
                materializations = tuple(
                    self._resolver(plan.agent).materialize(plan) for plan in plans
                )
                public_status, outcome = self._materialization_outcome(materializations)
                diagnostics = tuple(
                    message
                    for item in materializations
                    for message in item.diagnostics
                )
                after = tuple(self._absent_evidence(item) for item in before)
                if outcome is OperationOutcome.SUCCESS:
                    profile_ids = set(
                        self.registry.projected_state().profile(profile).assets
                    )
                    for item in before:
                        if item.ref.id in profile_ids:
                            self.registry.remove_profile_asset(
                                profile,
                                item.ref,
                                str(item.evidence["normalized_path"]),
                            )
                    # Native removal and desired-state removal have both been
                    # verified; project that new observation into the Git tree.
                    self._observe(tuple(native_assets))
                event = self.registry.record_asset_operation(
                    OperationKind.UNINSTALL,
                    outcome,
                    profile=profile,
                    before=before,
                    after=after,
                    forced=request.force,
                    diagnostics=diagnostics,
                    operation_id=operation_id,
                )
                self.registry.finish_operation(operation_id, event.outcome)
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
                    event = self.registry.record_asset_operation(
                        OperationKind.UNINSTALL,
                        OperationOutcome.FAILED,
                        profile=profile,
                        before=before,
                        after=(),
                        forced=request.force,
                        diagnostics=(str(error),),
                        operation_id=operation_id,
                    )
                    self.registry.finish_operation(operation_id, event.outcome)
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
            return self._failed("uninstall", str(error))

    def revert(self, request: ZuatRequest) -> OperationResult:
        if not request.operation_id:
            return self._failed("revert", "an operation id is required")
        marker_id: str | None = None
        current: tuple[AssetEvidence, ...] = ()
        try:
            with self.registry.operation():
                target = self.registry.event(request.operation_id)
                if target.outcome is not OperationOutcome.SUCCESS:
                    raise RegistryError("only a successful operation can be reverted")
                if target.kind is OperationKind.PROFILE_SWITCH or (
                    target.kind is OperationKind.REVERT
                    and target.metadata.get("state_kind") == "profile-switch"
                ):
                    return self._revert_profile_switch(request, target)
                if target.kind not in {
                    OperationKind.INSTALL,
                    OperationKind.UPDATE,
                    OperationKind.UNINSTALL,
                    OperationKind.REVERT,
                }:
                    raise RegistryError(
                        f"operation cannot be reverted: {target.kind.value}"
                    )

                profile = target.profile or self.registry.projected_state().selected_profile
                if profile != self.registry.projected_state().selected_profile:
                    raise RegistryError("asset revert requires the selected profile")
                affected = self._affected_evidence(target.before, target.after)
                required_agents = tuple(dict.fromkeys(item.ref.agent for item in affected))
                selected_agents = self._agents(request.agents)
                if not set(required_agents).issubset(selected_agents):
                    raise ResolutionError(
                        "revert agents must include: " + ", ".join(required_agents)
                    )
                observed, _, _, observation_diagnostics = self._observe(selected_agents)
                current = self._current_evidence(affected, observed)
                if self.registry.revert_conflicts(target.operation_id, current):
                    if not request.force:
                        event = self.registry.record_revert(
                            target.operation_id,
                            current=current,
                            diagnostics=observation_diagnostics,
                        )
                        return OperationResult(
                            "revert",
                            OperationStatus.FAILED,
                            operation_id=event.operation_id,
                            profile=profile,
                            assets=current,
                            diagnostics=event.diagnostics,
                        )
                    self._archive_current_evidence(current)

                desired = self._desired_inverse(target.before, affected)
                with tempfile.TemporaryDirectory() as temporary:
                    temporary_profile = Path(temporary) / "profile"
                    shutil.copytree(
                        self.registry.profile_root(profile), temporary_profile
                    )
                    self._write_inverse_profile(temporary_profile, desired)
                    policy = (
                        ConflictPolicy.REPLACE
                        if request.force
                        else ConflictPolicy.ABORT
                    )
                    plans = tuple(
                        self._resolver(agent).plan(
                            temporary_profile, conflict_policy=policy
                        )
                        for agent in required_agents
                    )
                    try:
                        for plan in plans:
                            self._resolver(plan.agent).preflight(plan)
                    except (ResolutionError, ValueError, OSError) as error:
                        event = self.registry.append_event(
                            OperationKind.REVERT,
                            OperationOutcome.REJECTED,
                            profile=profile,
                            forced=request.force,
                            before=current,
                            after=desired,
                            reverts=target.operation_id,
                            diagnostics=(str(error),),
                            metadata={
                                "reverted_kind": target.kind.value,
                                "state_kind": "asset",
                            },
                        )
                        return OperationResult(
                            "revert",
                            OperationStatus.FAILED,
                            operation_id=event.operation_id,
                            profile=profile,
                            assets=current,
                            diagnostics=(str(error),),
                        )

                    marker_id = self.registry.begin_operation(
                        OperationKind.REVERT,
                        profile=profile,
                        before=current,
                        metadata={"reverts": target.operation_id},
                    )
                    materializations = tuple(
                        self._resolver(plan.agent).materialize(plan) for plan in plans
                    )
                    public_status, outcome = self._materialization_outcome(
                        materializations
                    )
                    diagnostics = tuple(
                        message
                        for item in materializations
                        for message in item.diagnostics
                    )
                    if outcome is OperationOutcome.SUCCESS:
                        self._project_inverse_profile(profile, desired)
                        event = self.registry.record_revert(
                            target.operation_id,
                            current=current,
                            forced=request.force,
                            diagnostics=diagnostics,
                            event_operation_id=marker_id,
                        )
                    else:
                        event = self.registry.append_event(
                            OperationKind.REVERT,
                            outcome,
                            profile=profile,
                            forced=request.force,
                            before=current,
                            after=desired,
                            reverts=target.operation_id,
                            diagnostics=diagnostics,
                            metadata={
                                "reverted_kind": target.kind.value,
                                "state_kind": "asset",
                            },
                            operation_id=marker_id,
                        )
                    self.registry.finish_operation(marker_id, event.outcome)
                    marker_id = None
                    return OperationResult(
                        "revert",
                        public_status,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=desired if outcome is OperationOutcome.SUCCESS else current,
                        materializations=materializations,
                        diagnostics=diagnostics,
                    )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if marker_id is not None:
                try:
                    event = self.registry.append_event(
                        OperationKind.REVERT,
                        OperationOutcome.FAILED,
                        profile=self.registry.projected_state().selected_profile,
                        forced=request.force,
                        before=current,
                        reverts=request.operation_id,
                        diagnostics=(str(error),),
                        metadata={"state_kind": "asset"},
                        operation_id=marker_id,
                    )
                    self.registry.finish_operation(marker_id, event.outcome)
                    return OperationResult(
                        "revert",
                        OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=event.profile,
                        assets=current,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return self._failed("revert", str(error))

    def restore_all(
        self,
        operation_id: str,
        selector: AssetSelector,
        *,
        force: bool = False,
    ) -> OperationResult:
        """Recover matching assets that were present before an operation."""
        marker_id: str | None = None
        current: tuple[AssetEvidence, ...] = ()
        profile = self.registry.projected_state().selected_profile
        try:
            with self.registry.operation():
                target = self.registry.event(operation_id)
                profile = target.profile or profile
                if profile != self.registry.projected_state().selected_profile:
                    raise RegistryError("restore requires the selected profile")
                desired = tuple(
                    item
                    for item in target.before
                    if item.present and selector.matches(item)
                )
                if not desired:
                    return self._empty_bulk_result("restore-all")

                observed, _, _, observation_diagnostics = self._observe(
                    (selector.agent,)
                )
                all_current = self._current_evidence(desired, observed)
                repair_pairs = tuple(
                    (expected, actual)
                    for expected, actual in zip(desired, all_current)
                    if not self._same_recovery_state(expected, actual)
                )
                if not repair_pairs:
                    return OperationResult(
                        operation="restore-all",
                        status=OperationStatus.SUCCESS,
                        profile=profile,
                        assets=desired,
                    )

                repairs = tuple(expected for expected, _ in repair_pairs)
                current = tuple(actual for _, actual in repair_pairs)
                conflicts = tuple(
                    actual
                    for expected, actual in repair_pairs
                    if actual.present
                    and actual.fingerprint != expected.fingerprint
                )
                if conflicts and not force:
                    diagnostic = (
                        "force is required to restore over conflicting assets: "
                        + ", ".join(item.ref.id for item in conflicts)
                    )
                    event = self.registry.append_event(
                        OperationKind.RESTORE,
                        OperationOutcome.REJECTED,
                        profile=profile,
                        before=current,
                        after=repairs,
                        diagnostics=tuple((*observation_diagnostics, diagnostic)),
                        metadata={"restores": operation_id},
                    )
                    return OperationResult(
                        operation="restore-all",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=current,
                        diagnostics=event.diagnostics,
                    )
                if conflicts:
                    self._archive_current_evidence(conflicts)

                with tempfile.TemporaryDirectory() as temporary:
                    temporary_profile = Path(temporary) / "profile"
                    shutil.copytree(
                        self.registry.profile_root(profile), temporary_profile
                    )
                    try:
                        self._write_inverse_profile(temporary_profile, repairs)
                        plans = self._restore_plans(temporary_profile, repairs)
                        for plan in plans:
                            self._resolver(plan.agent).preflight(plan)
                    except (RegistryError, ResolutionError, ValueError, OSError) as error:
                        event = self.registry.append_event(
                            OperationKind.RESTORE,
                            OperationOutcome.REJECTED,
                            profile=profile,
                            forced=force,
                            before=current,
                            after=repairs,
                            diagnostics=(str(error),),
                            metadata={"restores": operation_id},
                        )
                        return OperationResult(
                            operation="restore-all",
                            status=OperationStatus.FAILED,
                            operation_id=event.operation_id,
                            profile=profile,
                            assets=current,
                            diagnostics=(str(error),),
                        )

                    marker_id = self.registry.begin_operation(
                        OperationKind.RESTORE,
                        profile=profile,
                        before=current,
                        metadata={"restores": operation_id},
                    )
                    materializations = tuple(
                        self._resolver(plan.agent).materialize(plan)
                        for plan in plans
                    )
                    public_status, outcome = self._materialization_outcome(
                        materializations
                    )
                    diagnostics = tuple(
                        message
                        for item in materializations
                        for message in item.diagnostics
                    )
                    result_assets: tuple[AssetEvidence, ...] = current
                    if outcome is OperationOutcome.SUCCESS:
                        self._project_inverse_profile(profile, repairs)
                        refreshed, _, _, refresh_diagnostics = self._observe(
                            (selector.agent,)
                        )
                        verified = self._current_evidence(repairs, refreshed)
                        if all(
                            self._same_recovery_state(expected, actual)
                            for expected, actual in zip(repairs, verified)
                        ):
                            result_assets = repairs
                        else:
                            public_status = OperationStatus.PARTIAL
                            outcome = OperationOutcome.PARTIAL
                            diagnostics = tuple(
                                (*diagnostics, *refresh_diagnostics, "restore verification failed")
                            )
                            result_assets = verified
                    event = self.registry.append_event(
                        OperationKind.RESTORE,
                        outcome,
                        profile=profile,
                        forced=force,
                        before=current,
                        after=repairs,
                        diagnostics=diagnostics,
                        metadata={"restores": operation_id},
                        operation_id=marker_id,
                    )
                    self.registry.finish_operation(marker_id, event.outcome)
                    marker_id = None
                    return OperationResult(
                        operation="restore-all",
                        status=public_status,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=result_assets,
                        materializations=materializations,
                        diagnostics=diagnostics,
                    )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            if marker_id is not None:
                try:
                    event = self.registry.append_event(
                        OperationKind.RESTORE,
                        OperationOutcome.FAILED,
                        profile=profile,
                        forced=force,
                        before=current,
                        diagnostics=(str(error),),
                        metadata={"restores": operation_id},
                        operation_id=marker_id,
                    )
                    self.registry.finish_operation(marker_id, event.outcome)
                    return OperationResult(
                        operation="restore-all",
                        status=OperationStatus.FAILED,
                        operation_id=event.operation_id,
                        profile=profile,
                        assets=current,
                        diagnostics=(str(error),),
                    )
                except RegistryError:
                    pass
            return self._failed("restore-all", str(error))

    def _revert_profile_switch(self, request: ZuatRequest, target) -> OperationResult:
        destination = target.metadata.get("from_profile")
        if not isinstance(destination, str):
            raise RegistryError("profile transition has no prior profile")
        current_profile = self.registry.projected_state().selected_profile
        if self.registry.revert_conflicts(target.operation_id) and not request.force:
            event = self.registry.record_revert(target.operation_id)
            return OperationResult(
                "revert",
                OperationStatus.FAILED,
                operation_id=event.operation_id,
                profile=current_profile,
                diagnostics=event.diagnostics,
            )
        before, _, _, _ = self._observe(request.agents)
        target_root = self.registry.profile_root(destination)
        policy = ConflictPolicy.REPLACE if request.force else ConflictPolicy.ABORT
        plans = tuple(
            self._resolver(agent).plan(target_root, conflict_policy=policy)
            for agent in self._agents(request.agents)
        )
        try:
            for plan in plans:
                self._resolver(plan.agent).preflight(plan)
        except (ResolutionError, ValueError, OSError) as error:
            event = self.registry.append_event(
                OperationKind.REVERT,
                OperationOutcome.REJECTED,
                profile=current_profile,
                forced=request.force,
                before=before,
                reverts=target.operation_id,
                diagnostics=(str(error),),
                metadata={
                    "reverted_kind": target.kind.value,
                    "state_kind": "profile-switch",
                },
            )
            return OperationResult(
                "revert",
                OperationStatus.FAILED,
                operation_id=event.operation_id,
                profile=current_profile,
                assets=before,
                diagnostics=(str(error),),
            )
        marker_id = self.registry.begin_operation(
            OperationKind.REVERT,
            profile=current_profile,
            before=before,
            metadata={"reverts": target.operation_id},
        )
        materializations = tuple(
            self._resolver(plan.agent).materialize(plan) for plan in plans
        )
        public_status, outcome = self._materialization_outcome(materializations)
        diagnostics = tuple(
            message for item in materializations for message in item.diagnostics
        )
        if outcome is OperationOutcome.SUCCESS:
            event = self.registry.record_revert(
                target.operation_id,
                forced=request.force,
                diagnostics=diagnostics,
                event_operation_id=marker_id,
            )
        else:
            event = self.registry.append_event(
                OperationKind.REVERT,
                outcome,
                profile=current_profile,
                forced=request.force,
                before=before,
                reverts=target.operation_id,
                diagnostics=diagnostics,
                metadata={
                    "reverted_kind": target.kind.value,
                    "state_kind": "profile-switch",
                },
                operation_id=marker_id,
            )
        self.registry.finish_operation(marker_id, event.outcome)
        return OperationResult(
            "revert",
            public_status,
            operation_id=event.operation_id,
            profile=self.registry.projected_state().selected_profile,
            assets=before,
            materializations=materializations,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _affected_evidence(
        before: Sequence[AssetEvidence], after: Sequence[AssetEvidence]
    ) -> tuple[AssetEvidence, ...]:
        selected: dict[str, AssetEvidence] = {item.ref.id: item for item in after}
        selected.update({item.ref.id: item for item in before})
        return tuple(selected[key] for key in sorted(selected))

    @staticmethod
    def _current_evidence(
        affected: Sequence[AssetEvidence], observed: Sequence[AssetEvidence]
    ) -> tuple[AssetEvidence, ...]:
        observed_by_id = {item.ref.id: item for item in observed}
        return tuple(
            observed_by_id.get(item.ref.id)
            or AssetEvidence(
                item.ref,
                None,
                Authority.CONFLICTING,
                present=False,
                evidence=dict(item.evidence),
            )
            for item in affected
        )

    @staticmethod
    def _desired_inverse(
        inverse: Sequence[AssetEvidence], affected: Sequence[AssetEvidence]
    ) -> tuple[AssetEvidence, ...]:
        desired = {item.ref.id: item for item in inverse}
        return tuple(
            desired.get(item.ref.id)
            or AssetEvidence(
                item.ref,
                None,
                Authority.UNAUTHORITATIVE,
                present=False,
                evidence=dict(item.evidence),
            )
            for item in affected
        )

    def _archive_current_evidence(
        self, evidence: Sequence[AssetEvidence]
    ) -> None:
        for item in evidence:
            if not item.present or not item.fingerprint:
                continue
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(
                    f"asset has no normalized payload: {item.ref.id}"
                )
            self.registry.archive_asset(
                item.ref,
                normalized,
                self.registry.observation_root / Path(normalized),
                item.fingerprint,
            )

    @staticmethod
    def _same_recovery_state(
        expected: AssetEvidence, actual: AssetEvidence
    ) -> bool:
        return (
            actual.present
            and actual.fingerprint == expected.fingerprint
            and actual.authority is expected.authority
        )

    def _restore_plans(
        self, temporary_profile: Path, desired: Sequence[AssetEvidence]
    ) -> tuple[ResolutionPlan, ...]:
        selected_keys: dict[str, set[tuple[str, str, str]]] = {}
        for item in desired:
            selected_keys.setdefault(item.ref.agent, set()).add(
                (item.ref.kind, item.ref.scope, item.ref.locator)
            )
        complete = tuple(
            self._resolver(agent).plan(
                temporary_profile,
                conflict_policy=ConflictPolicy.REPLACE,
            )
            for agent in selected_keys
        )
        return tuple(
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
            for plan in complete
        )

    def _write_inverse_profile(
        self, root: Path, desired: Sequence[AssetEvidence]
    ) -> None:
        for item in desired:
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(
                    f"asset has no normalized payload: {item.ref.id}"
                )
            target = root / Path(normalized)
            if item.present:
                if item.ref.kind == "plugin":
                    from zuat.utils.plugin_pointers import evidence_pointer, write_pointer
                    write_pointer(target, evidence_pointer(item.evidence))
                    self._write_asset_metadata(target, item.ref)
                    continue
                payload = self.registry.asset_payload(item.ref, item.fingerprint)
                if not payload.exists():
                    raise RegistryError(
                        f"archived payload is unavailable: {item.ref.id}"
                    )
                self._copy_asset(payload, target)
                self._write_asset_metadata(target, item.ref)
            else:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
                target.with_name(f"{target.name}.zuat.json").unlink(missing_ok=True)

    def _project_inverse_profile(
        self, profile: str, desired: Sequence[AssetEvidence]
    ) -> None:
        profile_ids = set(self.registry.projected_state().profile(profile).assets)
        for item in desired:
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(
                    f"asset has no normalized payload: {item.ref.id}"
                )
            if item.present and item.authority is Authority.AUTHORITATIVE:
                if item.ref.kind == "plugin":
                    from zuat.utils.plugin_pointers import evidence_pointer
                    self.registry.store_profile_pointer(profile, item.ref, normalized, evidence_pointer(item.evidence))
                    continue
                payload = self.registry.asset_payload(item.ref, item.fingerprint)
                assert item.fingerprint is not None
                self.registry.store_profile_asset(
                    profile, item.ref, normalized, payload, item.fingerprint
                )
            elif item.ref.id in profile_ids:
                self.registry.remove_profile_asset(profile, item.ref, normalized)

    def _observe(self, agents: tuple[str, ...]):
        from zuat.utils.contexts import project_context
        context = project_context(self.project_root)
        previous = {item.ref.id: item for item in self.registry.latest_observation()}
        selected = self._agents(agents)
        observations = tuple(
            self._resolver(agent).observe(self.registry.observation_root)
            for agent in selected
        )
        evidence: list[AssetEvidence] = []
        observed_ids: set[str] = set()
        selected_profile = self.registry.projected_state().profile(
            self.registry.projected_state().selected_profile
        )
        desired_ids = set(selected_profile.assets)
        for observation in observations:
            for asset in observation.assets:
                locator = self._locator(asset)
                ref = self.registry.ensure_asset_ref(
                    agent=asset.agent,
                    kind=asset.kind.value,
                    scope=asset.scope,
                    locator=locator,
                )
                observed_ids.add(ref.id)
                fingerprint = self._asset_fingerprint(
                    self.registry.observation_root / asset.path, asset
                )
                authority = Authority.UNAUTHORITATIVE
                if ref.id in desired_ids:
                    desired = self.registry.profile_root() / asset.path
                    authority = (
                        Authority.AUTHORITATIVE
                        if desired.exists()
                        and self._profile_fingerprint(ref, desired) == fingerprint
                        else Authority.CONFLICTING
                    )
                evidence.append(
                    AssetEvidence(
                        ref,
                        fingerprint,
                        authority,
                        evidence={
                            **dict(asset.evidence),
                            "asset_name": asset.name,
                            "normalized_path": asset.path.as_posix(),
                        },
                    )
                )
        for asset_id in sorted(desired_ids.difference(observed_ids)):
            ref = self.registry.find_asset_ref(asset_id)
            prior = previous.get(asset_id)
            if prior and prior.evidence.get("ref", {}).get("context") not in {None, context}:
                continue
            if ref.agent in selected and not any(obs.agent == ref.agent and obs.rejected for obs in observations):
                if prior and (ref.kind == "plugin" or prior.evidence.get("provider") == "plugin"):
                    evidence.append(self._absent_evidence(prior))
                    continue
                evidence.append(
                    AssetEvidence(
                        ref,
                        None,
                        Authority.CONFLICTING,
                        present=False,
                    )
                )
        rejected = tuple(
            message for observation in observations for message in observation.rejected
        )
        completeness = "partial" if rejected else "complete"
        ordered = tuple(sorted(evidence, key=lambda item: item.ref.id))
        event = self.registry.record_observation(
            ordered,
            agents=selected,
            completeness=completeness,
            diagnostics=rejected,
            context=context,
        )
        return ordered, event, completeness, rejected

    def _resolver(self, agent: str) -> AgentResolver:
        if agent not in self._resolvers:
            self._resolvers[agent] = resolver_for(
                agent,
                home=self.home,
                project_root=self.project_root,
                state_root=self.registry.control_root / "native",
                trust_project=self.trust_project,
            )
        return self._resolvers[agent]

    @staticmethod
    def _select_present(
        assets: Sequence[AssetEvidence], selector: AssetSelector
    ) -> tuple[AssetEvidence, ...]:
        selected = tuple(
            item for item in assets if item.present and selector.matches(item)
        )
        if selector.name and len(selected) > 1:
            raise ResolutionError("ambiguous asset name; select its provider")
        if any(item.evidence.get("provider") == "plugin" for item in selected):
            raise ResolutionError("bundled plugin contributions cannot be independently mutated")
        return selected

    def _empty_bulk_result(self, operation: str) -> OperationResult:
        return OperationResult(
            operation=operation,
            status=OperationStatus.SUCCESS,
            profile=self.registry.projected_state().selected_profile,
        )

    def _profile_fingerprint(self, ref, path: Path) -> str:
        value = self._resolver(ref.agent).fingerprint(path, AssetKind(ref.kind))
        return value if ":" in value else f"sha256:{value}"

    def _install_sources(
        self,
        request: ZuatRequest,
        observed: Mapping[str, AssetEvidence],
    ) -> tuple[tuple[object, Path, str, AssetEvidence], ...]:
        selected: list[tuple[object, Path, str, AssetEvidence]] = []
        allowed_agents = set(self._agents(request.agents))
        for asset_id in request.asset_refs:
            ref = self.registry.find_asset_ref(asset_id)
            if ref.agent not in allowed_agents:
                raise ResolutionError(f"asset is outside the selected agents: {asset_id}")
            before = observed.get(asset_id)
            if before is None or not before.present:
                raise ResolutionError(f"observed asset is not present: {asset_id}")
            normalized = before.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise ResolutionError(f"asset has no normalized payload: {asset_id}")
            source = self.registry.observation_root / Path(normalized)
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
            ref = self.registry.ensure_asset_ref(
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
                        f"{name}{source.suffix}"
                        if item.kind == "hook"
                        else source.name
                    )
                )
                normalized = f"{item.agent}/{item.scope}/{plural}/{filename}"
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

    def _missing_observed_asset(self, asset_id: str) -> AssetEvidence:
        ref = self.registry.find_asset_ref(asset_id)
        return AssetEvidence(
            ref,
            None,
            Authority.CONFLICTING,
            present=False,
        )

    @staticmethod
    def _absent_evidence(item: AssetEvidence) -> AssetEvidence:
        return AssetEvidence(
            item.ref,
            None,
            Authority.UNAUTHORITATIVE,
            present=False,
            evidence=dict(item.evidence),
        )

    @staticmethod
    def _copy_asset(source: Path, target: Path) -> None:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    @staticmethod
    def _write_asset_metadata(target: Path, ref) -> None:
        metadata = target.with_name(f"{target.name}.zuat.json")
        metadata.write_text(
            json.dumps(
                {"scope": ref.scope, "native_locator": ref.locator},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _agents(agents: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(agents).difference(SUPPORTED_AGENTS)
        if unknown:
            raise ResolutionError(f"unsupported agents: {', '.join(sorted(unknown))}")
        if len(set(agents)) != len(agents):
            raise ResolutionError("agents must not be repeated")
        return agents

    @staticmethod
    def _locator(asset: Asset) -> str:
        native = asset.evidence.get("native_locator")
        if isinstance(native, str) and native:
            return native
        value = asset.path.as_posix().strip("/")
        prefix = f"{asset.agent}/"
        return value[len(prefix) :] if value.startswith(prefix) else value

    @classmethod
    def _asset_fingerprint(cls, path: Path, asset: Asset) -> str | None:
        supplied = asset.evidence.get("fingerprint")
        if isinstance(supplied, str) and supplied:
            return supplied if ":" in supplied else f"sha256:{supplied}"
        return cls._fingerprint_path(path) if path.exists() else None

    @staticmethod
    def _fingerprint_path(path: Path) -> str:
        digest = hashlib.sha256()
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        else:
            for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
                digest.update(item.relative_to(path).as_posix().encode("utf-8"))
                digest.update(b"\0")
                digest.update(item.read_bytes())
                digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _materialization_outcome(
        materializations: Sequence[Materialization],
    ) -> tuple[OperationStatus, OperationOutcome]:
        if all(item.verified for item in materializations):
            return OperationStatus.SUCCESS, OperationOutcome.SUCCESS
        if any(item.verified for item in materializations):
            return OperationStatus.PARTIAL, OperationOutcome.PARTIAL
        if any(item.state == "indeterminate" for item in materializations):
            return OperationStatus.PARTIAL, OperationOutcome.INDETERMINATE
        if any(item.state == "partial" for item in materializations):
            return OperationStatus.PARTIAL, OperationOutcome.PARTIAL
        return OperationStatus.FAILED, OperationOutcome.FAILED

    @staticmethod
    def _observation_status(assets: Sequence[AssetEvidence]) -> OperationStatus:
        if any(item.authority in {Authority.PARTIAL, Authority.INDETERMINATE} for item in assets):
            return OperationStatus.PARTIAL
        return OperationStatus.SUCCESS

    @staticmethod
    def _failed(operation: str, diagnostic: str) -> OperationResult:
        return OperationResult(
            operation=operation,
            status=OperationStatus.FAILED,
            diagnostics=(diagnostic,),
        )
