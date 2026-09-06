"""Pi-owned native paths, extension rules, scopes, and lifecycle behavior."""

from __future__ import annotations

from pathlib import Path

from zuat.specs.base import ResolverSupport
from zuat.specs.interface import ConflictPolicy, Materialization, Observation, ResolutionPlan
from zuat.specs.native import Agent, HookSource, Scope
from zuat.specs.pi_plugins import PiPluginAdapter
from zuat.specs.interface import PluginAdapter
from zuat.utils.assets import load_pi_extension


class PiResolver:
    agent = "pi"
    native_agent = Agent.PI

    def __init__(self, *, home: str | Path | None = None, project_root: str | Path | None = None, state_root: str | Path | None = None, plugins: PluginAdapter | None = None, trust_project: bool = False) -> None:
        self._support = ResolverSupport(
            agent=Agent.PI, home=home, project_root=project_root, state_root=state_root,
            skills=Path(".pi/agent/skills"), hooks=Path(".pi/agent/extensions"),
            project_skills=Path(".pi/skills"), project_hooks=Path(".pi/extensions"), hook_suffix="",
            hook_loader=load_pi_extension,
            scopes=frozenset({Scope.USER, Scope.PROJECT}), shared_hooks=False,
            plugin_factory=lambda native_home, store: PiPluginAdapter(home=native_home, store=store, project_root=Path(project_root) if project_root else None, trust_project=trust_project), plugin_adapter=plugins,
        )
        self.home = self._support.home

    def observe(self, registry_root: Path) -> Observation:
        return self._support.observe(registry_root)

    def fingerprint(self, path: Path, kind) -> str:
        return self._support.fingerprint(path, kind)

    def plan(self, desired_root: Path, *, conflict_policy: ConflictPolicy = ConflictPolicy.ABORT) -> ResolutionPlan:
        return self._support.plan(desired_root, conflict_policy)

    def preflight(self, plan: ResolutionPlan) -> None:
        self._support.preflight(plan)

    def plan_uninstall(self, assets, *, conflict_policy: ConflictPolicy = ConflictPolicy.ABORT) -> ResolutionPlan:
        return self._support.plan_uninstall(assets, conflict_policy=conflict_policy)

    def materialize(self, plan: ResolutionPlan) -> Materialization:
        return self._support.materialize(plan)

    def plugin_adapter(self):
        return self._support.plugins(self._support.bind(self._support.state_root or self.home))
