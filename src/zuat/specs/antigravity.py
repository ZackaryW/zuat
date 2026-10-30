"""Antigravity-owned native paths, name-keyed hooks, scopes, and lookup behavior."""

from __future__ import annotations

import json
from pathlib import Path

from zuat.specs.antigravity_plugins import AntigravityPluginAdapter
from zuat.specs.base import ResolverSupport
from zuat.specs.interface import ConflictPolicy, Materialization, Observation, PluginAdapter, ResolutionPlan
from zuat.specs.native import Agent, Scope
from zuat.utils.assets import load_keyed_json_hook
from zuat.utils.documents import add_keyed, contains_keyed, read_keyed_json, remove_keyed, write_json
from zuat.utils.hook_documents import KeyedHookDocument
from zuat.utils.skill_lookup import SkillSearch, directory_chain, tiers_under

# Workspace customization roots agy accepts; ".agents" is the default spelling.
WORKSPACE_ROOTS = (".agents", ".agent", "_agents", "_agent")
# The unified root agy writes to, the CLI-specific root, and the legacy IDE root.
USER_SKILL_ROOTS = (".gemini/config/skills", ".gemini/antigravity-cli/skills", ".gemini/antigravity/skills")
MAX_INHERITANCE = 8


def _declared_skill_dirs(
    configs: tuple[tuple[Path, Path | None], ...], home: Path, project_root: Path
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Directories declared by ``skills.json`` files, following ``inherits``.

    ``include_only``/``exclude`` are deliberately ignored: a directory that could
    hold the skill counts as a possible shadow. Unreadable declarations are
    returned as reasons rather than guessed around.
    """
    directories: list[Path] = []
    errors: list[str] = []
    seen: set[Path] = set()

    def resolve(raw: str, base: Path | None) -> Path:
        if raw == "~" or raw.startswith(("~/", "~\\")):
            return home / raw[2:]
        path = Path(raw)
        if path.is_absolute():
            return path
        if base is not None and (base / path).exists():
            return base / path
        return project_root / path

    def visit(path: Path, base: Path | None, depth: int) -> None:
        key = path.resolve()
        if key in seen:
            return
        seen.add(key)
        if depth > MAX_INHERITANCE:
            errors.append(f"Antigravity skills.json inheritance is deeper than {MAX_INHERITANCE}: {path}")
            return
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"cannot read Antigravity skills.json {path}: {error}")
            return
        entries = document.get("entries", []) if isinstance(document, dict) else None
        inherits = document.get("inherits", []) if isinstance(document, dict) else None
        if (
            not isinstance(entries, list)
            or not isinstance(inherits, list)
            or any(not isinstance(item, dict) or not isinstance(item.get("path"), str) for item in (*entries, *inherits))
        ):
            errors.append(f"Antigravity skills.json {path}: entries and inherits must list objects with a path")
            return
        directories.extend(resolve(item["path"], base) for item in entries)
        for item in inherits:
            target = resolve(item["path"], base)
            if not target.is_file():
                errors.append(f"Antigravity skills.json {path}: inherited config not found: {target}")
                continue
            visit(target, target.parent, depth + 1)

    for path, base in configs:
        if path.is_file():
            visit(path, base, 0)
    return tuple(dict.fromkeys(directories)), tuple(errors)


class AntigravityResolver:
    agent = "antigravity"
    native_agent = Agent.ANTIGRAVITY

    def __init__(self, *, home: str | Path | None = None, project_root: str | Path | None = None, state_root: str | Path | None = None, plugins: PluginAdapter | None = None, trust_project: bool = False) -> None:
        self._support = ResolverSupport(
            agent=Agent.ANTIGRAVITY, home=home, project_root=project_root, state_root=state_root,
            skills=Path(".gemini/config/skills"), hooks=Path(".gemini/config/hooks.json"),
            project_skills=Path(".agents/skills"), project_hooks=Path(".agents/hooks.json"), hook_suffix=".json",
            hook_loader=lambda path: load_keyed_json_hook(path, agent=Agent.ANTIGRAVITY),
            scopes=frozenset({Scope.USER, Scope.PROJECT}), shared_hooks=True,
            plugin_factory=lambda native_home, store: AntigravityPluginAdapter(home=native_home, store=store),
            read_document=read_keyed_json, write_document=write_json, serialize_fragment=write_json,
            contains=contains_keyed, add=add_keyed, remove=remove_keyed, plugin_adapter=plugins,
            hook_document=KeyedHookDocument(),
        )
        self.home = self._support.home

    def skill_search(self, cwd: Path) -> SkillSearch:
        """Project > declared > user > built-in, per the agy customization guide.

        Project skills are found from ``cwd`` up to the repository root in every
        accepted workspace spelling. Same-named copies within one scope, symlinks,
        and copies only reachable through ``skills.json`` are never chosen.
        Built-in skills rank below user skills and are not modeled.
        """
        levels = directory_chain(cwd)
        declared, errors = _declared_skill_dirs(
            (
                *((level / root / "skills.json", level) for level in levels for root in WORKSPACE_ROOTS),
                (self.home / ".gemini/config/skills.json", None),
            ),
            self.home,
            levels[-1],
        )
        return SkillSearch(
            tiers=(
                *(tier for root in WORKSPACE_ROOTS
                  for tier in tiers_under(levels, f"{root}/skills", scope="project", follow_symlinks=False)),
                *(tier for root in USER_SKILL_ROOTS
                  for tier in tiers_under((self.home,), root, scope="user", follow_symlinks=False)),
            ),
            unmodeled=tiers_under(declared, "", scope="declared", follow_symlinks=False),
            prefer=("project", "user"),
            blocking=errors,
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
        """agy has a plugin manager, but bundle bootstrap through it is not modeled yet."""
        return None
