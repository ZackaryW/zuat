"""Observation and context validation for the public orchestration layer.

Resolvers report native facts; this layer relates them to the selected profile
and journals observations. It must not infer absence in a different project or
turn incomplete provider discovery into permission to mutate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    RegistryError,
)
from zuat.pub.models import (
    AssetSelector,
    OperationResult,
    OperationStatus,
    ZuatRequest,
)
from zuat.pub.results import (
    failed,
    observation_status,
)
from zuat.pub.selection import validate_agents
from zuat.specs.interface import (
    ResolutionError,
)
from zuat.utils.contexts import (
    evidence_context,
    locator_context,
    project_context,
)
from zuat.utils.evidence import (
    absent_evidence,
)
from zuat.utils.payloads import (
    asset_fingerprint,
    asset_locator,
)

if TYPE_CHECKING:
    from zuat.pub.service import Zuat


class ObservationOperations:
    """Focused orchestration using the facade's shared registry and resolver context."""

    def __init__(self, service: Zuat) -> None:
        self.service = service

    def status(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        """Report unresolved intent before observing native state.

        A fresh observation cannot prove an interrupted update completed; returning
        its recovery requirement first prevents status from implying convergence.
        """
        service = self.service
        try:
            with service.registry.operation():
                pending = service._assets.pending_status()
                if pending is not None:
                    return pending
                assets, event, completeness, diagnostics = self.observe(request.agents)
            return OperationResult(
                operation="status",
                status=(
                    OperationStatus.PARTIAL
                    if completeness != "complete"
                    else observation_status(assets)
                ),
                operation_id=event.operation_id if event else None,
                profile=service.registry.projected_state().selected_profile,
                completeness=completeness,
                assets=assets,
                diagnostics=diagnostics,
            )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return failed("status", str(error))

    def list_assets(self, selector: AssetSelector) -> OperationResult:
        """Observe under the shared lock, then filter the resulting evidence.

        Filtering after observation preserves complete evidence for the selected
        agent rather than teaching the registry that unselected assets disappeared.
        """
        service = self.service
        try:
            with service.registry.operation():
                assets, event, completeness, diagnostics = self.observe(
                    (selector.agent,)
                )
                selected = tuple(item for item in assets if selector.matches(item))
            return OperationResult(
                operation="asset-list",
                status=(
                    OperationStatus.PARTIAL
                    if completeness != "complete"
                    else observation_status(selected)
                ),
                operation_id=event.operation_id if event else None,
                profile=service.registry.projected_state().selected_profile,
                completeness=completeness,
                assets=selected,
                diagnostics=diagnostics,
            )
        except (RegistryError, ResolutionError, ValueError, OSError) as error:
            return failed("asset-list", str(error))

    def observe(self, agents: tuple[str, ...]):
        """Relate native facts to desired state without assigning new ownership.

        The caller holds the registry lock across observation and any later
        selection/mutation. Context checks precede resolver I/O; missing assets
        are reported only for this context and complete agent observations.
        """
        service = self.service
        self.validate_context_catalog()
        from zuat.utils.contexts import project_context

        context = project_context(service.project_root)
        previous = {item.ref.id: item for item in service.registry.latest_observation()}
        selected = validate_agents(agents)
        observations = tuple(
            service._resolver(agent).observe(service.registry.observation_root)
            for agent in selected
        )
        evidence: list[AssetEvidence] = []
        observed_ids: set[str] = set()
        selected_profile = service.registry.projected_state().profile(
            service.registry.projected_state().selected_profile
        )
        desired_ids = set(selected_profile.assets)
        for observation in observations:
            for asset in observation.assets:
                locator = asset_locator(asset)
                ref = service.registry.ensure_asset_ref(
                    agent=asset.agent,
                    kind=asset.kind.value,
                    scope=asset.scope,
                    locator=locator,
                )
                observed_ids.add(ref.id)
                fingerprint = asset_fingerprint(
                    service.registry.observation_root / asset.path, asset
                )
                authority = Authority.UNAUTHORITATIVE
                if ref.id in desired_ids:
                    desired = service.registry.profile_root() / asset.path
                    authority = (
                        Authority.AUTHORITATIVE
                        if desired.exists()
                        and service._projections.profile_fingerprint(ref, desired)
                        == fingerprint
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
            ref = service.registry.find_asset_ref(asset_id)
            prior = previous.get(asset_id)
            if locator_context(ref.locator) not in {None, context}:
                continue
            if prior and evidence_context(prior) not in {None, context}:
                continue
            if ref.agent in selected and not any(
                obs.agent == ref.agent and obs.rejected for obs in observations
            ):
                if prior and (
                    ref.kind == "plugin" or prior.evidence.get("provider") == "plugin"
                ):
                    evidence.append(absent_evidence(prior))
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
        event = service.registry.record_observation(
            ordered,
            agents=selected,
            completeness=completeness,
            diagnostics=rejected,
            context=context,
        )
        return ordered, event, completeness, rejected

    def validate_context_catalog(self):
        """Reject ambiguous project identities before any native observation.

        Guessing a context from the current project would silently reassign old
        records and make subsequent restore/remove operations unsafe.
        """
        service = self.service
        for ref in service.registry.projected_state().catalog:
            if (
                ref.scope == "project"
                and ref.kind != "plugin"
                and not locator_context(ref.locator)
            ):
                raise ResolutionError(
                    "ambiguous context-free project state; use a fresh registry"
                )

    def validate_refs(self, asset_ids):
        """Validate original project association before resolving native targets.

        Explicit references never override the caller's selected project. Recovery
        uses this same gate before observing or compensating an interrupted write.
        """
        service = self.service
        self.validate_context_catalog()
        for asset_id in asset_ids:
            ref = service.registry.find_asset_ref(asset_id)
            if ref.scope == "project" and locator_context(
                ref.locator
            ) != project_context(service.project_root):
                raise ResolutionError(
                    "asset requires its original project context and explicit project root"
                )
