"""Codex-owned native paths, formats, scopes, and lifecycle behavior."""

from __future__ import annotations

import json
from pathlib import Path

from zuat.specs.base import ResolverSupport
from zuat.specs.interface import ConflictPolicy, Materialization, Observation, ResolutionPlan
from zuat.specs.native import Agent, HookSource, Scope
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.interface import PluginAdapter
from zuat.utils.documents import add_fragment, contains_fragment, read_json, remove_fragment, write_json
from zuat.utils.assets import load_json_hook


class CodexResolver:
    agent = "codex"
    native_agent = Agent.CODEX

    def __init__(self, *, home: str | Path | None = None, project_root: str | Path | None = None, state_root: str | Path | None = None, plugins: PluginAdapter | None = None, trust_project: bool = False) -> None:
        self._support = ResolverSupport(
            agent=Agent.CODEX, home=home, project_root=project_root, state_root=state_root,
            skills=Path(".codex/skills"), hooks=Path(".codex/hooks.json"),
            project_skills=Path(".agents/skills"), project_hooks=Path(".codex/hooks.json"), hook_suffix=".json",
            hook_loader=lambda path: load_json_hook(path, agent=Agent.CODEX),
            scopes=frozenset({Scope.USER, Scope.PROJECT}), shared_hooks=True,
            plugin_factory=lambda native_home, store: CodexPluginAdapter(home=native_home, store=store, project_root=Path(project_root) if project_root else None, trust_project=trust_project),
            read_document=read_json, write_document=write_json,
            serialize_fragment=lambda fragment: (json.dumps({"hooks": fragment}, indent=2, sort_keys=True) + "\n").encode(),
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
