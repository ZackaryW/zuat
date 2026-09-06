"""Public facade and shared runtime context for Zuat operations.

Keep entry points here, not transaction implementations. Focused collaborators
own observation, asset lifecycle, profiles, and recovery while sharing this
registry and resolver cache. Native agent policy stays in specs; private Git
persistence stays in gitcore. Importing the public API does not require Click.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from zuat.gitcore import (
    GitRegistry,
    RegistryError,
)
from zuat.pub.models import (
    AssetInput,
    AssetInspection,
    AssetSelector,
    OperationResult,
    OperationStatus,
    ZuatRequest,
)
from zuat.pub.results import failed
from zuat.specs.interface import (
    AgentResolver,
)
from zuat.specs.registry import resolver_for


class Zuat:
    """Stateful public API; use as a context manager to close owned resources.

    A supplied registry remains caller-owned. All collaborators use this same
    runtime context and registry lock; splitting orchestration must not create
    separate transactions or caches for one logical operation.
    """

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
        """Share one registry and resolver cache across all operation collaborators.

        Borrowed registries remain caller-owned; lazily constructed resolvers keep
        opening a service independent of native agent availability.
        """
        from zuat.pub.artifacts import ArtifactOperations
        from zuat.pub.assets import AssetOperations
        from zuat.pub.lifecycle import LifecycleOperations
        from zuat.pub.observations import ObservationOperations
        from zuat.pub.profile_operations import ProfileOperations
        from zuat.pub.projections import AssetProjections
        from zuat.pub.recovery import RecoveryOperations

        self.registry = registry or GitRegistry(root)
        self._owns_registry = registry is None
        self.home = Path(home).resolve() if home is not None else None
        self.project_root = (
            Path(project_root).resolve() if project_root is not None else None
        )
        self._resolvers = dict(resolvers or {})
        self.trust_project = trust_project
        self._artifacts = ArtifactOperations(self)
        self._assets = AssetOperations(self)
        self._observations = ObservationOperations(self)
        self._lifecycle = LifecycleOperations(self)
        self._profiles = ProfileOperations(self)
        self._recovery = RecoveryOperations(self)
        self._projections = AssetProjections(self)

    def inspect_asset(self, asset: AssetInput) -> AssetInspection:
        """Compare one source against its native target without adopting or mutating it."""
        return self._assets.inspect(asset)

    def update_asset(
        self, asset: AssetInput, *, force: bool = False
    ) -> OperationResult:
        """Replace one existing independent asset; force permits conflict, not ambiguity."""
        return self._assets.update(asset, force=force)

    def register_artifact(self, extension):
        """Register runtime locator code on this service, never in the journal."""
        return self._artifacts.register(extension)

    def artifact_status(self, ref, identifier, *, revision=None):
        """Check current artifact eligibility; host policy cannot enable native plugins."""
        return self._artifacts.status(ref, identifier, revision=revision)

    def resolve_artifacts(self, agent, identifier):
        """Resolve only artifacts eligible in this service's installation context."""
        return self._artifacts.resolve(agent, identifier)

    def set_artifact_policy(self, ref, identifier, policy):
        """Record host selection policy without changing native plugin activation."""
        return self._artifacts.set_policy(ref, identifier, policy)

    def clear_artifact_policy(self, ref, identifier):
        """Return host selection to inheritance through a new policy event."""
        return self._artifacts.set_policy(ref, identifier, "inherit")

    def close(self) -> None:
        """Close an owned registry only; a supplied registry belongs to the caller."""
        if self._owns_registry:
            self.registry.close()

    def __enter__(self) -> Zuat:
        """Keep one runtime context across a sequence of public operations."""
        return self

    def __exit__(self, *_: object) -> None:
        """Release owned resources without performing native rollback or cleanup."""
        self.close()

    def status(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        """Report unresolved intent before observing native state."""
        return self._observations.status(request)

    def discover_plugins(self, agent: str, *, include_available: bool = False):
        """Discover plugin revisions and contributions without snapshotting their bodies."""
        from zuat.pub.plugins import PluginOperations

        return PluginOperations(self).discover(
            agent, include_available=include_available
        )

    def install_plugin(self, ref, *, trust: bool = False, force: bool = False):
        """Ask the native manager to install; persist only verified revision pointers."""
        from zuat.pub.plugins import PluginOperations

        return PluginOperations(self).mutate("install", ref, trust=trust, force=force)

    def update_plugin(self, ref, *, force: bool = False):
        """Update through the native manager with authority checks and recovery intent."""
        from zuat.pub.plugins import PluginOperations

        return PluginOperations(self).mutate("update", ref, force=force)

    def remove_plugin(self, ref, *, force: bool = False):
        """Remove the installation through its manager, not individual contributions."""
        from zuat.pub.plugins import PluginOperations

        return PluginOperations(self).mutate("remove", ref, force=force)

    def recover_plugins(self):
        """Observe an interrupted plugin operation without replaying the manager call."""
        from zuat.pub.plugins import PluginOperations

        return PluginOperations(self).recover()

    def list_assets(self, selector: AssetSelector) -> OperationResult:
        """Observe under the shared lock, then filter the resulting evidence."""
        return self._observations.list_assets(selector)

    def adopt_all(
        self, selector: AssetSelector, *, force: bool = False
    ) -> OperationResult:
        """Select and install under one reentrant registry lock."""
        return self._lifecycle.adopt_all(selector, force=force)

    def uninstall_all(
        self, selector: AssetSelector, *, force: bool = False
    ) -> OperationResult:
        """Select and remove under the same lock used by single-operation removal."""
        return self._lifecycle.uninstall_all(selector, force=force)

    def profiles(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        """List desired profiles without implying they have been applied natively."""
        return self._profiles.profiles(request)

    def create_profile(self, request: ZuatRequest) -> OperationResult:
        """Observe before creating a profile so current drift remains in the trail."""
        return self._profiles.create_profile(request)

    def switch_profile(self, request: ZuatRequest) -> OperationResult:
        """Preflight every agent before starting a named-profile transition."""
        return self._profiles.switch_profile(request)

    def history(self, request: ZuatRequest = ZuatRequest()) -> OperationResult:
        """Read forward domain transitions without exposing private Git identifiers."""
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
            return failed("history", str(error))

    def install(self, request: ZuatRequest) -> OperationResult:
        """Plan selected installs from a frozen profile, then publish verified state."""
        return self._lifecycle.install(request)

    def uninstall(self, request: ZuatRequest) -> OperationResult:
        """Remove selected native assets before dropping their managed projections."""
        return self._lifecycle.uninstall(request)

    def revert(self, request: ZuatRequest) -> OperationResult:
        """Invert one successful transition against freshly observed current state."""
        return self._recovery.revert(request)

    def restore_all(
        self,
        operation_id: str,
        selector: AssetSelector,
        *,
        force: bool = False,
    ) -> OperationResult:
        """Recover selected before-state assets without deleting later additions."""
        return self._recovery.restore_all(operation_id, selector, force=force)

    def _resolver(self, agent: str) -> AgentResolver:
        """Reuse each agent's resolver so native policy and injected adapters stay local.

        Construction is deferred until that agent is requested; merely opening the
        public service must not probe every agent or require optional CLI tooling.
        """
        if agent not in self._resolvers:
            self._resolvers[agent] = resolver_for(
                agent,
                home=self.home,
                project_root=self.project_root,
                state_root=self.registry.control_root / "native",
                trust_project=self.trust_project,
            )
        return self._resolvers[agent]
