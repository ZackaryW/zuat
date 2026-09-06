"""Kimi-owned native paths, TOML format, scopes, and lifecycle behavior."""

from __future__ import annotations

from pathlib import Path

from zuat.specs.base import ResolverSupport
from zuat.specs.interface import ConflictPolicy, Materialization, Observation, ResolutionPlan
from zuat.specs.native import Agent, HookSource, Scope
from zuat.specs.kimi_plugins import KimiPluginAdapter
from zuat.specs.interface import PluginAdapter
from zuat.utils.documents import add_fragment, contains_fragment, read_toml, remove_fragment, write_toml
from zuat.utils.assets import load_toml_hook


class KimiResolver:
    agent = "kimi"
    native_agent = Agent.KIMI

    def __init__(self, *, home: str | Path | None = None, project_root: str | Path | None = None, state_root: str | Path | None = None, plugins: PluginAdapter | None = None, trust_project: bool = False) -> None:
        self._support = ResolverSupport(
            agent=Agent.KIMI, home=home, project_root=project_root, state_root=state_root,
            skills=Path(".kimi-code/skills"), hooks=Path(".kimi-code/config.toml"),
            project_skills=Path(".kimi-code/skills"), project_hooks=None, hook_suffix=".toml",
            hook_loader=load_toml_hook,
            scopes=frozenset({Scope.USER, Scope.PROJECT}), shared_hooks=True,
            plugin_factory=lambda native_home, store: KimiPluginAdapter(home=native_home, store=store),
            read_document=read_toml, write_document=write_toml,
            serialize_fragment=lambda fragment: write_toml({"hooks": fragment}),
            contains=contains_fragment, add=add_fragment, remove=remove_fragment, plugin_adapter=plugins,
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
