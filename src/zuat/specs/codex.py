"""Codex-owned native paths, formats, scopes, and lifecycle behavior."""

from __future__ import annotations

import json
from pathlib import Path

from zuat.specs.base import ResolverSupport
from zuat.specs.interface import ConflictPolicy, Materialization, Observation, ResolutionPlan
from zuat.specs.native import Agent, HookSource, InvalidAssetError, Scope
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.interface import PluginAdapter
from zuat.utils.documents import add_fragment, contains_fragment, read_json, read_toml, remove_fragment, write_json
from zuat.utils.assets import load_json_hook
from zuat.utils.skill_lookup import SkillSearch, SkillTier, directory_chain, tiers_under


def _disabled_skills(config: Path) -> tuple[frozenset[Path], tuple[str, ...]]:
    """Canonical skill roots switched off by ``[[skills.config]] enabled = false``.

    A missing config disables nothing. An unreadable one is reported, because
    which copy Codex loads may then be undeterminable.
    """
    if not config.is_file():
        return frozenset(), ()
    try:
        document = read_toml(config)
    except (InvalidAssetError, OSError) as error:
        return frozenset(), (f"cannot read Codex config {config}: {error}",)
    entries = document.get("skills", {})
    entries = entries.get("config", []) if isinstance(entries, dict) else []
    disabled: set[Path] = set()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("enabled") is not False:
            continue
        path = entry.get("path")
        if not isinstance(path, str):
            continue
        target = Path(path).expanduser()
        disabled.add((target.parent if target.name == "SKILL.md" else target).resolve())
    return frozenset(disabled), ()


class CodexResolver:
    agent = "codex"
    native_agent = Agent.CODEX
    # Class attribute so tests can redirect the machine-wide location.
    ADMIN_ROOT = Path("/etc/codex/skills")

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

    def skill_search(self, cwd: Path) -> SkillSearch:
        """Codex lists same-named skills side by side and never picks one itself.

        Source: Codex skills documentation. Selection therefore needs caller
        evidence or ``[[skills.config]]`` disabling; bundled system skills are
        not modeled.
        """
        disabled, errors = _disabled_skills(self.home / ".codex" / "config.toml")
        return SkillSearch(
            tiers=(
                *tiers_under((self.home,), ".codex/skills", scope="user", follow_symlinks=True),
                *tiers_under((self.home,), ".agents/skills", scope="user", follow_symlinks=True),
                *tiers_under(directory_chain(cwd), ".agents/skills", scope="project", follow_symlinks=True),
            ),
            unmodeled=(SkillTier("admin", "admin", self.ADMIN_ROOT, True),),
            disabled=disabled,
            evidence_errors=errors,
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
        from zuat.specs.codex_bundles import CodexBundleAdapter
        return CodexBundleAdapter()
