"""Claude-owned native paths, formats, scopes, and lifecycle behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from zuat.specs.base import ResolverSupport
from zuat.specs.interface import ConflictPolicy, Materialization, Observation, ResolutionPlan
from zuat.specs.native import Agent, HookSource, Scope
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.interface import PluginAdapter
from zuat.utils.documents import add_fragment, contains_fragment, read_json, remove_fragment, write_json
from zuat.utils.assets import load_json_hook
from zuat.utils.skill_lookup import SkillSearch, directory_chain, tiers_under


def _managed_root() -> Path:
    """Managed-settings directory per the Claude Code managed-settings documentation."""
    if sys.platform == "win32":
        return Path(r"C:\Program Files\ClaudeCode")
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode")
    return Path("/etc/claude-code")


class ClaudeResolver:
    agent = "claude"
    native_agent = Agent.CLAUDE
    # Class attribute so tests can redirect the machine-wide location.
    MANAGED_ROOT = _managed_root()

    def __init__(self, *, home: str | Path | None = None, project_root: str | Path | None = None, state_root: str | Path | None = None, plugins: PluginAdapter | None = None, trust_project: bool = False) -> None:
        self._support = ResolverSupport(
            agent=Agent.CLAUDE, home=home, project_root=project_root, state_root=state_root,
            skills=Path(".claude/skills"), hooks=Path(".claude/settings.json"),
            project_skills=Path(".claude/skills"), project_hooks=Path(".claude/settings.json"), hook_suffix=".json",
            hook_loader=lambda path: load_json_hook(path, agent=Agent.CLAUDE),
            scopes=frozenset({Scope.USER, Scope.PROJECT}), shared_hooks=True,
            plugin_factory=lambda native_home, store: ClaudePluginAdapter(home=native_home, store=store, project_root=Path(project_root) if project_root else None, trust_project=trust_project),
            read_document=read_json, write_document=write_json,
            serialize_fragment=lambda fragment: (json.dumps({"hooks": fragment}, indent=2, sort_keys=True) + "\n").encode(),
            contains=contains_fragment, add=add_fragment, remove=remove_fragment, plugin_adapter=plugins,
        )
        self.home = self._support.home

    def skill_search(self, cwd: Path) -> SkillSearch:
        """Enterprise > personal > project; project skills load from cwd up to the repository root.

        Source: Claude Code skills documentation (name resolution, nested discovery).
        Skills below the invocation directory load lazily during a session and
        plugin skills are namespaced; neither is modeled here.
        """
        project_levels = directory_chain(cwd)
        return SkillSearch(
            tiers=(
                *tiers_under((self.home,), ".claude/skills", scope="user", follow_symlinks=True),
                *tiers_under(project_levels, ".claude/skills", scope="project", follow_symlinks=True),
            ),
            unmodeled=tiers_under(
                (self.MANAGED_ROOT,), ".claude/skills", scope="managed",
                follow_symlinks=True, label="managed",
            ),
            prefer=("user", "project"),
        )

    def observe(self, registry_root: Path) -> Observation:
        return self._support.observe(registry_root)

    def inspect_asset(self, source, kind, scope, *, name=None, locator=None):
        from zuat.utils.inspection import inspect_target
        return inspect_target(self._support, source, kind, scope, name=name, locator=locator)

    def resolve_asset_source(self, source, kind, scope):
        from zuat.utils.inspection import resolve_source
        return resolve_source(self._support, source, kind, scope)[0]

    def capture_asset(self, target, output):
        from zuat.utils.inspection import capture_target
        return capture_target(self._support, target, output)

    def replace_asset(self, target):
        from zuat.utils.inspection import replace_target
        return replace_target(self._support, target)

    def restore_asset_ownership(self, asset, ownership):
        from zuat.utils.inspection import restore_receipt
        return restore_receipt(self._support, asset, ownership)

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

    def bundle_adapter(self):
        """Keep generated manifests and native bootstrap policy agent-owned."""
        from zuat.specs.claude_bundles import ClaudeBundleAdapter
        return ClaudeBundleAdapter()
