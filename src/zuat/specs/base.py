"""Agent-neutral resolver support; concrete modules retain all native policy."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from zuat.specs.interface import (
    Asset,
    AssetKind,
    ConflictPolicy,
    Materialization,
    Observation,
    PlannedAction,
    ResolutionError,
    ResolutionPlan,
)
from zuat.specs.native import Agent, HookSource, PluginRef, Scope, SkillSource, UnsupportedNativeOperation
from zuat.specs.interface import PluginAdapter
from zuat.utils.lifecycle import (
    apply_dedicated,
    apply_shared_hook,
    build_plan,
    desired_assets,
    inspect_dedicated,
    inspect_shared_hook,
    observe_extensions,
    observe_shared_hooks,
    observe_skills,
    plugin_filename,
)
from zuat.utils.assets import collect_files, fingerprint
from zuat.utils.mutation import atomic_write, remove_absent
from zuat.utils.ownership import OwnershipStore
from zuat.utils.results import materialize_plan
from zuat.utils.plugin_pointers import read_pointer, write_pointer, pointer_fingerprint, evidence_pointer
from zuat.utils.contexts import project_context, native_locator, contextual_locator


class ResolverSupport:
    """Reusable mechanics parameterized by explicit concrete-agent policy."""

    def __init__(
        self,
        *,
        agent: Agent,
        home: str | Path | None,
        project_root: str | Path | None,
        state_root: str | Path | None,
        skills: Path,
        hooks: Path,
        project_skills: Path | None,
        project_hooks: Path | None,
        hook_suffix: str,
        hook_loader: Callable[[Path], HookSource],
        scopes: frozenset[Scope],
        shared_hooks: bool,
        plugin_factory: Callable[[Path, OwnershipStore], PluginAdapter],
        read_document: Callable[[Path], dict[str, object]] | None = None,
        write_document: Callable[[dict[str, object]], bytes] | None = None,
        serialize_fragment: Callable[[object], bytes] | None = None,
        contains: Callable[[dict[str, object], object], bool] | None = None,
        add: Callable[[dict[str, object], object], dict[str, object]] | None = None,
        remove: Callable[[dict[str, object], object], dict[str, object]] | None = None,
        plugin_adapter: PluginAdapter | None = None,
    ) -> None:
        self.agent = agent
        self.home = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        self.context = project_context(self.project_root)
        self.state_root = Path(state_root).resolve() if state_root is not None else None
        self.skills = self.home / skills
        self.hooks = self.home / hooks
        self.project_skills = self.project_root / project_skills if self.project_root is not None and project_skills is not None else None
        self.project_hooks = self.project_root / project_hooks if self.project_root is not None and project_hooks is not None else None
        self.hook_suffix = hook_suffix
        self.hook_loader = hook_loader
        self.scopes = scopes
        self.shared_hooks = shared_hooks
        self.plugin_factory = plugin_factory
        self.read_document = read_document
        self.write_document = write_document
        self.serialize_fragment = serialize_fragment
        self.contains = contains
        self.add = add
        self.remove = remove
        self._plugin_adapter = plugin_adapter

    def bind(self, registry_root: Path) -> OwnershipStore:
        if self.state_root is None:
            root = Path(registry_root).resolve()
            self.state_root = (root / ".git" / "zuat" / "native") if (root / ".git").exists() else (root.parent / ".zuat-control" / "native")
        return OwnershipStore(self.state_root, self.agent.value)

    def plugins(self, store: OwnershipStore) -> PluginAdapter:
        if self._plugin_adapter is None:
            self._plugin_adapter = self.plugin_factory(self.home, store)
        return self._plugin_adapter

    def observe(self, registry_root: Path) -> Observation:
        root = Path(registry_root) / self.agent.value
        root.mkdir(parents=True, exist_ok=True)
        store = self.bind(Path(registry_root))
        try:
            plugin_records = self.plugins(store).discover()
            plugin_errors = []
        except (ResolutionError, OSError, ValueError):
            plugin_records = ()
            plugin_errors = ["plugin discovery failed"]
        plugin_roots = tuple(item.runtime_root for item in plugin_records if item.runtime_root is not None) + tuple(getattr(self.plugins(store), "unresolved_roots", ()))
        skills: list[Asset] = []
        hooks: list[Asset] = []
        rejected: list[str] = []
        hook_rejections: list[str] = []
        for scope, skill_root, hook_root in (
            (Scope.USER, self.skills, self.hooks),
            (Scope.PROJECT, self.project_skills, self.project_hooks),
        ):
            # Without provider discovery, a skill directory may actually be a
            # plugin installation. Retain prior evidence rather than ingest it.
            if skill_root is not None and not plugin_errors:
                found, failures = observe_skills(
                    agent=self.agent,
                    native_root=skill_root,
                    registry_root=root,
                    scope=scope,
                    excluded_roots=plugin_roots,
                    context=self.context,
                )
                skills.extend(found)
                rejected.extend(failures)
            if hook_root is None:
                continue
            if self.shared_hooks:
                assert self.read_document and self.serialize_fragment
                found, failures = observe_shared_hooks(
                    agent=self.agent,
                    registry_root=root,
                    read_document=self.read_document,
                    store=self.ordinary_store(store, scope),
                    native_path=hook_root,
                    serialize_fragment=self.serialize_fragment,
                    suffix=self.hook_suffix,
                    hook_loader=self.hook_loader,
                    scope=scope,
                    context=self.context,
                )
            else:
                found, failures = observe_extensions(
                    agent=self.agent,
                    native_root=hook_root,
                    registry_root=root,
                    hook_loader=self.hook_loader,
                    scope=scope,
                    context=self.context,
                )
            hooks.extend(found)
            hook_rejections.extend(failures)
        plugins, plugin_rejections = self._observe_plugins(root, store, plugin_records, complete=not plugin_errors)
        plugin_rejections.extend(plugin_errors)
        return Observation(self.agent.value, tuple((*skills, *hooks, *plugins)), tuple((*rejected, *hook_rejections, *plugin_rejections)))

    def fingerprint(self, path: Path, kind: AssetKind) -> str:
        if kind is AssetKind.SKILL:
            return SkillSource.from_path(path).fingerprint
        if kind is AssetKind.HOOK:
            return self.hook_loader(path).fingerprint
        return pointer_fingerprint(read_pointer(path))

    def _observe_plugins(self, root: Path, store: OwnershipStore, records, *, complete: bool = True) -> tuple[list[Asset], list[str]]:
        assets: list[Asset] = []
        seen: dict[str, set[str]] = {}
        for record in records:
            if not record.installed:
                continue
            prefix = f"ctx-{record.ref.context[:16]}-" if record.ref.context else ""
            filename = prefix + plugin_filename(record.ref.native_ref)
            desired = root / record.ref.scope.value / "plugins"
            output = desired / filename
            output.parent.mkdir(parents=True, exist_ok=True)
            write_pointer(output, record)
            seen.setdefault(record.ref.scope.value, set()).add(filename)
            evidence = record.to_dict()
            evidence["fingerprint"] = pointer_fingerprint(record)
            locator_prefix = f"contexts/{record.ref.context}/" if record.ref.context else ""
            evidence["native_locator"] = f"{locator_prefix}plugins/{record.ref.native_ref}"
            assets.append(Asset(self.agent.value, AssetKind.PLUGIN, record.ref.native_ref, Path(self.agent.value) / record.ref.scope.value / "plugins" / filename, record.ref.scope.value, evidence))
            try:
                for kind, identifier in self.plugins(store).contributions(record):
                    contribution = {**evidence, "provider": "plugin", "contribution_id": identifier,
                                    "native_locator": f"{locator_prefix}plugin-contributions/{record.ref.native_ref}/{kind}/{identifier}"}
                    assets.append(Asset(self.agent.value, AssetKind(kind), identifier.rsplit("/", 1)[-1],
                                        Path(self.agent.value) / record.ref.scope.value / "plugins" / filename,
                                        record.ref.scope.value, contribution))
            except (OSError, ValueError):
                return assets, ["plugin contributions could not be resolved safely"]
        diagnostics = tuple(getattr(self.plugins(store), "discovery_diagnostics", ()))
        if complete and not diagnostics:
            for scope in Scope:
                directory = root / scope.value / "plugins"
                keep = seen.get(scope.value, set())
                if scope in {Scope.PROJECT, Scope.LOCAL}:
                    from zuat.utils.contexts import project_context
                    prefix = f"ctx-{(project_context(self.project_root) or '')[:16]}-"
                    keep = keep | {path.name for path in directory.glob("*") if not path.name.startswith(prefix)}
                remove_absent(directory, keep)
        return assets, list(diagnostics)

    def plan(self, desired_root: Path, conflict_policy: ConflictPolicy) -> ResolutionPlan:
        root = Path(desired_root) / self.agent.value
        store = self.bind(Path(desired_root))
        desired = desired_assets(agent=self.agent, root=root, hook_loader=self.hook_loader, context=self.context)
        from zuat.utils.contexts import project_context
        context = project_context(self.project_root)
        records = store.for_context(context).records() if context else ()
        return build_plan(agent=self.agent, root=root, desired=desired, store=store, conflict_policy=conflict_policy, additional_records=records)

    def preflight(self, plan: ResolutionPlan) -> None:
        if plan.agent != self.agent.value:
            raise ResolutionError(f"plan belongs to {plan.agent}, not {self.agent.value}")
        store = self.bind(plan.root.parent)
        for action in plan.actions:
            asset = action.asset
            if asset.evidence.get("provider") == "plugin":
                raise UnsupportedNativeOperation("bundled plugin contributions cannot be independently mutated")
            try:
                scope = Scope(asset.scope)
            except ValueError as error:
                raise ResolutionError(f"unsupported scope: {asset.scope}") from error
            if asset.kind is AssetKind.PLUGIN:
                record = evidence_pointer(asset.evidence)
                self.plugins(store).preflight(record.ref, action.operation, desired=record if action.operation == "install" else None)
                continue
            if scope not in self.scopes:
                raise UnsupportedNativeOperation(f"{self.agent.value} does not support {scope.value} scope")
            locator = asset.evidence.get("native_locator")
            if scope is Scope.PROJECT and isinstance(locator, str):
                contextual_locator(scope.value, locator, self.context)
            selected_store = self.ordinary_store(store, scope)
            if asset.evidence.get("targeted"):
                from zuat.utils.inspection import inspect_target
                target = inspect_target(self, asset.path, asset.kind, asset.scope, name=asset.name)
                if target.classification in {"conflict", "unowned"} and plan.conflict_policy is ConflictPolicy.ABORT:
                    raise ResolutionError("force is required for conflicting or unowned replacement")
                continue
            record = selected_store.load(asset.kind.value, asset.name, scope.value)
            destination = self._destination(asset, scope)
            if action.operation == "remove":
                if record is None and plan.conflict_policy is ConflictPolicy.ABORT:
                    raise ResolutionError(f"unmanaged {asset.kind.value} cannot be removed: {asset.name}")
                continue
            source = SkillSource.from_path(asset.path) if asset.kind is AssetKind.SKILL else self.hook_loader(asset.path)
            if asset.kind is AssetKind.HOOK and self.shared_hooks:
                assert self.read_document and self.contains
                inspection = inspect_shared_hook(source=source, destination=destination, store=selected_store, read_document=self.read_document, contains=self.contains, scope=scope)
            else:
                inspection = inspect_dedicated(source, destination, record)
            if inspection.status.value in {"unmanaged", "conflict"} and plan.conflict_policy is ConflictPolicy.ABORT:
                raise ResolutionError(f"{self.agent.value} {asset.kind.value} {asset.name}: {inspection.status.value}")

    def materialize(self, plan: ResolutionPlan) -> Materialization:
        if plan.agent != self.agent.value:
            raise ResolutionError(f"plan belongs to {plan.agent}, not {self.agent.value}")
        return materialize_plan(self.agent.value, plan, lambda action: self._apply(plan, action))

    def plan_uninstall(
        self,
        assets: tuple[Asset, ...],
        *,
        conflict_policy: ConflictPolicy = ConflictPolicy.ABORT,
    ) -> ResolutionPlan:
        for asset in assets:
            if asset.agent != self.agent.value:
                raise ResolutionError(
                    f"asset belongs to {asset.agent}, not {self.agent.value}"
                )
        ordered = tuple(sorted(assets, key=self._uninstall_order))
        root = assets[0].path.parent if assets else self.home
        return ResolutionPlan(
            self.agent.value,
            root,
            tuple(PlannedAction("remove", asset) for asset in ordered),
            ConflictPolicy(conflict_policy),
        )

    def _uninstall_order(self, asset: Asset) -> tuple[object, ...]:
        """Remove indexed shared fragments from the tail toward the head."""
        native = asset.evidence.get("native_locator")
        if (
            self.shared_hooks
            and asset.kind is AssetKind.HOOK
            and isinstance(native, str)
        ):
            parts = native.split("/")
            if parts and parts[-1].isdigit():
                return (0, "/".join(parts[:-1]), -int(parts[-1]), asset.name)
        return (1, asset.kind.value, asset.scope, asset.name)

    def _destination(self, asset: Asset, scope: Scope) -> Path:
        if scope is Scope.PROJECT:
            selected = self.project_skills if asset.kind is AssetKind.SKILL else self.project_hooks
            if selected is None:
                raise UnsupportedNativeOperation(f"{self.agent.value} native {asset.kind.value} project scope requires a project root")
            if asset.kind is AssetKind.SKILL:
                return selected / asset.name
            return selected if self.shared_hooks else selected / asset.path.name
        if scope is not Scope.USER:
            raise UnsupportedNativeOperation(f"{self.agent.value} does not support native {asset.kind.value} scope {scope.value}")
        if asset.kind is AssetKind.SKILL:
            return self.skills / asset.name
        if self.shared_hooks:
            return self.hooks
        return self.hooks / asset.path.name

    def ordinary_store(self, store: OwnershipStore, scope: Scope) -> OwnershipStore:
        if scope is Scope.PROJECT:
            contextual_locator(scope.value, "assets", self.context)
            if any(record.scope == "project" and record.kind != "plugin" for record in store.records()):
                raise ResolutionError("ambiguous context-free project ownership; use a fresh registry")
            return store.for_context(self.context)
        return store

    def _apply(self, plan: ResolutionPlan, action: PlannedAction):
        asset = action.asset
        scope = Scope(asset.scope)
        store = self.bind(plan.root.parent)
        if asset.kind is AssetKind.PLUGIN:
            record = evidence_pointer(asset.evidence)
            return self.plugins(store).remove(record.ref) if action.operation == "remove" else self.plugins(store).reconcile(record)
        store = self.ordinary_store(store, scope)
        if asset.evidence.get("targeted"):
            from zuat.utils.inspection import inspect_target, replace_target
            from zuat.specs.native import LifecycleResult
            target = inspect_target(self, asset.path, asset.kind, asset.scope, name=asset.name)
            if target.classification != "absent":
                replace_target(self, target)
                return LifecycleResult("install", "updated", target.destination)
        destination = self._destination(asset, scope)
        source = None
        if action.operation != "remove" or (
            asset.kind is AssetKind.HOOK
            and self.shared_hooks
            and plan.conflict_policy is ConflictPolicy.REPLACE
        ):
            source = SkillSource.from_path(asset.path) if asset.kind is AssetKind.SKILL else self.hook_loader(asset.path)
        if asset.kind is AssetKind.HOOK and self.shared_hooks:
            assert self.read_document and self.write_document and self.contains and self.add and self.remove
            locator = asset.evidence.get("native_locator")
            return apply_shared_hook(operation=action.operation, source=source, destination=destination, store=store, name=asset.name, scope=scope, policy=plan.conflict_policy, read_document=self.read_document, write_document=self.write_document, contains=self.contains, add=self.add, remove=self.remove, native_locator=native_locator(locator) if isinstance(locator, str) else None)
        return apply_dedicated(operation=action.operation, source=source, destination=destination, store=store, kind=asset.kind.value, name=asset.name, scope=scope, policy=plan.conflict_policy)
