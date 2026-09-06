"""Agent-neutral observation, planning, inspection, and filesystem lifecycle mechanics."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from hashlib import sha256
from pathlib import Path

from zuat.specs.interface import Asset, AssetKind, ConflictPolicy, PlannedAction, ResolutionError, ResolutionPlan
from zuat.specs.native import (
    Agent,
    HookSource,
    Inspection,
    InspectionStatus,
    LifecycleResult,
    NativeConflictError,
    Scope,
    SkillSource,
)
from zuat.utils.assets import collect_files, fingerprint
from zuat.utils.mutation import atomic_write, mirror_files, remove_absent, remove_tree, replace_tree
from zuat.utils.ownership import OwnershipRecord, OwnershipStore
from zuat.utils.documents import remove_fragment_at_locator, replace_fragment_at_locator
from zuat.utils.contexts import contextual_locator, scope_path


def plugin_filename(native_ref: str) -> str:
    return f"plugin-{sha256(native_ref.encode()).hexdigest()[:16]}.json"


def asset_scope(path: Path) -> Scope:
    metadata = path.with_name(f"{path.name}.zuat.json")
    if not metadata.exists():
        return Scope.USER
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        return Scope(payload["scope"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ResolutionError(f"invalid asset metadata: {metadata}") from error


def asset_metadata(path: Path, scope: Scope) -> dict[str, object]:
    metadata = path.with_name(f"{path.name}.zuat.json")
    if not metadata.exists():
        return {"scope": scope.value}
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise ResolutionError(f"invalid asset metadata: {metadata}") from error
    if not isinstance(payload, dict):
        raise ResolutionError(f"invalid asset metadata: {metadata}")
    return payload


def observe_skills(
    *, agent: Agent, native_root: Path, registry_root: Path, scope: Scope, excluded_roots: tuple[Path, ...] = (), context: str | None = None
) -> tuple[list[Asset], list[str]]:
    relative = scope_path(scope.value, context) / "skills"
    desired = registry_root / relative
    assets: list[Asset] = []
    rejected: list[str] = []
    observed: set[str] = set()
    if native_root.is_dir() and not native_root.is_symlink():
        for candidate in sorted(native_root.iterdir(), key=lambda value: value.name):
            if candidate.name.startswith("."):
                continue
            if any(candidate.resolve().is_relative_to(root) for root in excluded_roots):
                continue
            try:
                skill = SkillSource.from_path(candidate)
                if agent not in skill.compatible_agents:
                    raise ResolutionError(f"skill is incompatible with {agent.value}")
                mirror_files(desired / skill.name, skill.files)
            except (ResolutionError, OSError) as error:
                rejected.append(f"skill {candidate.name}: {error}")
                continue
            observed.add(skill.name)
            assets.append(Asset(agent.value, AssetKind.SKILL, skill.name, Path(agent.value) / relative / skill.name, scope.value, {"fingerprint": skill.fingerprint, "native_locator": contextual_locator(scope.value, f"skills/{skill.name}", context)}))
    remove_absent(desired, observed)
    return assets, rejected


def observe_extensions(
    *,
    agent: Agent,
    native_root: Path,
    registry_root: Path,
    hook_loader: Callable[[Path], HookSource],
    scope: Scope,
    context: str | None = None,
) -> tuple[list[Asset], list[str]]:
    relative = scope_path(scope.value, context) / "hooks"
    desired = registry_root / relative
    assets: list[Asset] = []
    rejected: list[str] = []
    observed: set[str] = set()
    if native_root.is_dir() and not native_root.is_symlink():
        for candidate in sorted(native_root.iterdir(), key=lambda value: value.name):
            if candidate.name.startswith("."):
                continue
            try:
                hook = hook_loader(candidate)
                target = desired / candidate.name
                if candidate.is_dir():
                    mirror_files(target, hook.files)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write(target, hook.files[0].content)
            except (ResolutionError, OSError) as error:
                rejected.append(f"extension {candidate.name}: {error}")
                continue
            observed.add(candidate.name)
            assets.append(Asset(agent.value, AssetKind.HOOK, hook.name, Path(agent.value) / relative / candidate.name, scope.value, {"fingerprint": hook.fingerprint, "format": hook.format, "native_locator": contextual_locator(scope.value, f"extensions/{candidate.name}", context)}))
    remove_absent(desired, observed)
    return assets, rejected


def observe_shared_hooks(
    *,
    agent: Agent,
    registry_root: Path,
    read_document: Callable[[Path], dict[str, object]],
    native_path: Path,
    serialize_fragment: Callable[[object], bytes],
    suffix: str,
    hook_loader: Callable[[Path], HookSource],
    scope: Scope,
    context: str | None = None,
    store: OwnershipStore | None = None,
) -> tuple[list[Asset], list[str]]:
    relative = scope_path(scope.value, context) / "hooks"
    desired = registry_root / relative
    assets: list[Asset] = []
    rejected: list[str] = []
    observed: set[str] = set()
    try:
        document = read_document(native_path)
    except (ResolutionError, OSError, ValueError) as error:
        remove_absent(desired, observed)
        return assets, [f"hooks: {error}"]
    hooks = document.get("hooks")
    fragments: list[tuple[str, object, str]] = []
    if hooks is None:
        remove_absent(desired, observed)
        return assets, rejected
    if isinstance(hooks, dict):
        for event, entries in hooks.items():
            if not isinstance(event, str) or not isinstance(entries, list):
                rejected.append("hooks: native hooks mapping has an unsupported shape")
                continue
            slug = re.sub(r"[^A-Za-z0-9._-]+", "-", event).strip("-") or "event"
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    rejected.append(f"hooks: {event}/{index} is not an object")
                    continue
                fragments.append(
                    (f"{slug}-{index:03d}", {event: [entry]}, f"hooks/{event}/{index}")
                )
    elif isinstance(hooks, list):
        for index, entry in enumerate(hooks):
            if not isinstance(entry, dict):
                rejected.append(f"hooks: {index} is not an object")
                continue
            event = str(entry.get("event", "hook"))
            slug = re.sub(r"[^A-Za-z0-9._-]+", "-", event).strip("-") or "hook"
            fragments.append(
                (f"{slug}-{index:03d}", [entry], f"hooks/{index}")
            )
    else:
        rejected.append("hooks: native hooks value has an unsupported shape")
    if store:
        from zuat.utils.inspection import fragment_parts, fragment_fingerprint, selected_fragment
        groups = []
        claimed = set()
        for record in store.records("hook"):
            if record.scope != scope.value or Path(record.destination) != native_path.resolve():
                continue
            try:
                if len(fragment_parts(record.fragment)) <= 1:
                    continue
                actual = selected_fragment(document, record.fragment)
                if actual is None:
                    continue
                keys = {fragment_fingerprint(part) for part in fragment_parts(actual)}
                if claimed.intersection(keys):
                    raise ResolutionError("ambiguous overlapping owned hook groups")
                claimed.update(keys)
                groups.append((record.name, actual, record.native_locator or f"hooks/{record.name}"))
            except ResolutionError as error:
                rejected.append(str(error))
        fragments = [item for item in fragments if fragment_fingerprint(item[1]) not in claimed] + groups
    for name, fragment, native_locator in fragments:
        matches = [record for record in store.records("hook") if record.scope == scope.value
                   and Path(record.destination) == native_path.resolve() and record.fragment == fragment] if store else []
        if len(matches) == 1:
            name = matches[0].name
            native_locator = matches[0].native_locator or native_locator
        filename = f"{name}{suffix}"
        output = desired / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            atomic_write(output, serialize_fragment(fragment))
            source = hook_loader(output)
        except (ResolutionError, OSError, ValueError) as error:
            rejected.append(f"hook {native_locator}: {error}")
            continue
        observed.add(filename)
        assets.append(Asset(agent.value, AssetKind.HOOK, name, Path(agent.value) / relative / filename, scope.value, {"fingerprint": source.fingerprint, "format": source.format, "native_locator": contextual_locator(scope.value, native_locator, context)}))
    remove_absent(desired, observed)
    return assets, rejected


def desired_assets(
    *, agent: Agent, root: Path, hook_loader: Callable[[Path], HookSource], context: str | None = None
) -> list[Asset]:
    assets: list[Asset] = []
    for scope in Scope:
        scoped_root = root / scope.value
        if scope is Scope.PROJECT:
            for family in ("skills", "hooks"):
                if any(path.name != ".gitkeep" for path in (scoped_root / family).glob("*")):
                    raise ResolutionError("ambiguous context-free project profile; use a fresh registry")
            scoped_root = root / scope_path(scope.value, context) if context else root / "project/no-selected-context"
        skills = scoped_root / "skills"
        if skills.is_dir():
            for path in sorted(skills.iterdir(), key=lambda value: value.name):
                if path.name == ".gitkeep" or path.name.endswith(".zuat.json"):
                    continue
                source = SkillSource.from_path(path)
                if agent not in source.compatible_agents:
                    raise ResolutionError(f"skill {source.name} is incompatible with {agent.value}")
                metadata = asset_metadata(path, scope)
                assets.append(Asset(agent.value, AssetKind.SKILL, source.name, path, scope.value, {"fingerprint": source.fingerprint, "native_locator": str(metadata.get("native_locator", f"skills/{source.name}")), "targeted": bool(metadata.get("targeted", False))}))
        hooks = scoped_root / "hooks"
        if hooks.is_dir():
            for path in sorted(hooks.iterdir(), key=lambda value: value.name):
                if path.name == ".gitkeep" or path.name.endswith(".zuat.json"):
                    continue
                source = hook_loader(path)
                metadata = asset_metadata(path, scope)
                assets.append(Asset(agent.value, AssetKind.HOOK, source.name, path, scope.value, {"fingerprint": source.fingerprint, "native_locator": str(metadata.get("native_locator", f"hooks/{source.name}")), "targeted": bool(metadata.get("targeted", False))}))
        plugins = root / scope.value / "plugins"
        if plugins.is_dir():
            for path in sorted(plugins.glob("*.json")):
                if path.name.endswith(".zuat.json"):
                    continue
                from zuat.utils.plugin_pointers import read_pointer
                record = read_pointer(path)
                if record.ref.agent != agent or record.ref.scope != scope:
                    raise ResolutionError("plugin pointer belongs to another installation")
                metadata = asset_metadata(path, scope)
                assets.append(Asset(agent.value, AssetKind.PLUGIN, record.ref.native_ref, path, scope.value, {**record.to_dict(), "native_locator": metadata.get("native_locator", f"plugins/{record.ref.native_ref}")}))
    return assets


def build_plan(
    *, agent: Agent, root: Path, desired: Iterable[Asset], store: OwnershipStore, conflict_policy: ConflictPolicy, additional_records=()
) -> ResolutionPlan:
    selected = tuple(desired)
    keys = {(item.kind.value, item.name, item.scope) for item in selected}
    actions = [PlannedAction("install", item) for item in selected]
    for record in (*store.records(), *additional_records):
        if (record.kind, record.name, record.scope) not in keys:
            try:
                kind = AssetKind(record.kind)
            except ValueError:
                continue
            evidence = record.fragment if kind is AssetKind.PLUGIN and isinstance(record.fragment, dict) else {}
            actions.append(PlannedAction("remove", Asset(agent.value, kind, record.name, Path(record.destination), record.scope, evidence)))
    return ResolutionPlan(agent.value, root, tuple(actions), ConflictPolicy(conflict_policy))


def inspect_dedicated(source: SkillSource | HookSource, destination: Path, record: OwnershipRecord | None) -> Inspection:
    if destination.is_symlink():
        return Inspection(InspectionStatus.CONFLICT, destination)
    if not destination.exists():
        return Inspection(InspectionStatus.ABSENT, destination, source.fingerprint)
    try:
        actual = fingerprint(collect_files(destination))
    except (OSError, ResolutionError):
        return Inspection(InspectionStatus.CONFLICT, destination, source.fingerprint)
    if record is None:
        status = (
            InspectionStatus.ADOPTABLE
            if source.fingerprint == actual
            else InspectionStatus.UNMANAGED
        )
        return Inspection(status, destination, source.fingerprint, actual)
    if Path(record.destination) != destination.resolve() or record.fingerprint != actual:
        return Inspection(InspectionStatus.CONFLICT, destination, source.fingerprint, actual)
    status = InspectionStatus.CURRENT if source.fingerprint == actual else InspectionStatus.OUTDATED
    return Inspection(status, destination, source.fingerprint, actual)


def apply_dedicated(
    *, operation: str, source: SkillSource | HookSource | None, destination: Path, store: OwnershipStore, kind: str, name: str, scope: Scope, policy: ConflictPolicy
) -> LifecycleResult:
    record = store.load(kind, name, scope.value)
    if operation == "remove":
        if destination.exists():
            if record is None and policy is ConflictPolicy.ABORT:
                raise NativeConflictError(f"unmanaged {kind} cannot be removed: {destination}")
            actual = fingerprint(collect_files(destination))
            if (
                record is not None
                and actual != record.fingerprint
                and policy is ConflictPolicy.ABORT
            ):
                raise NativeConflictError(f"owned {kind} changed outside Zuat: {destination}")
            if destination.is_dir():
                remove_tree(destination)
            else:
                destination.unlink()
        store.remove(kind, name, scope.value)
        return LifecycleResult("remove", "removed", destination)
    assert source is not None
    before = inspect_dedicated(source, destination, record)
    if before.status is InspectionStatus.CURRENT:
        return LifecycleResult("install", "current", destination, before, before)
    if before.status is InspectionStatus.ADOPTABLE:
        store.save(OwnershipRecord(store.agent, kind, name, scope.value, str(destination.resolve()), source.fingerprint, getattr(source, "fragment", None)))
        return LifecycleResult("install", "adopted", destination, before, before)
    if before.status in {InspectionStatus.UNMANAGED, InspectionStatus.CONFLICT} and policy is ConflictPolicy.ABORT:
        raise NativeConflictError(f"{kind} destination is {before.status.value}: {destination}")
    if source.path.is_file() and not isinstance(source, SkillSource):
        atomic_write(destination, source.files[0].content)
    else:
        replace_tree(destination, source.files)
    after = inspect_dedicated(source, destination, OwnershipRecord(store.agent, kind, name, scope.value, str(destination.resolve()), source.fingerprint, getattr(source, "fragment", None)))
    if after.status is not InspectionStatus.CURRENT:
        raise NativeConflictError(f"postcondition verification failed: {destination}")
    store.save(OwnershipRecord(store.agent, kind, name, scope.value, str(destination.resolve()), source.fingerprint, getattr(source, "fragment", None)))
    status = "installed" if before.status is InspectionStatus.ABSENT else "updated"
    return LifecycleResult("install", status, destination, before, after)


def inspect_shared_hook(
    *,
    source: HookSource,
    destination: Path,
    store: OwnershipStore,
    read_document: Callable[[Path], dict[str, object]],
    contains: Callable[[dict[str, object], object], bool],
    scope: Scope,
) -> Inspection:
    document = read_document(destination)
    record = store.load("hook", source.name, scope.value)
    desired_present = contains(document, source.fragment)
    if record is None:
        return Inspection(InspectionStatus.ADOPTABLE if desired_present else InspectionStatus.ABSENT, destination, source.fingerprint)
    if Path(record.destination) != destination.resolve() or record.fragment is None:
        return Inspection(InspectionStatus.CONFLICT, destination, source.fingerprint)
    if not contains(document, record.fragment):
        return Inspection(InspectionStatus.CONFLICT, destination, source.fingerprint)
    return Inspection(InspectionStatus.CURRENT if desired_present and record.fragment == source.fragment else InspectionStatus.OUTDATED, destination, source.fingerprint)


def apply_shared_hook(
    *,
    operation: str,
    source: HookSource | None,
    destination: Path,
    store: OwnershipStore,
    name: str,
    scope: Scope,
    policy: ConflictPolicy,
    read_document: Callable[[Path], dict[str, object]],
    write_document: Callable[[dict[str, object]], bytes],
    contains: Callable[[dict[str, object], object], bool],
    add: Callable[[dict[str, object], object], dict[str, object]],
    remove: Callable[[dict[str, object], object], dict[str, object]],
    native_locator: str | None = None,
) -> LifecycleResult:
    document = read_document(destination)
    record = store.load("hook", name, scope.value)
    locator_parts = native_locator.split("/") if native_locator else []
    positional_locator = (
        native_locator
        if (
            len(locator_parts) in {2, 3}
            and locator_parts[0] == "hooks"
            and locator_parts[-1].isdigit()
        )
        else None
    )
    if operation == "remove":
        if record is None:
            if policy is ConflictPolicy.ABORT and destination.exists():
                raise NativeConflictError(f"unmanaged hook cannot be removed: {name}")
            if source is None or not contains(document, source.fragment):
                return LifecycleResult("remove", "absent", destination)
            updated = (
                remove_fragment_at_locator(document, native_locator)
                if native_locator
                else remove(document, source.fragment)
            )
            atomic_write(destination, write_document(updated))
            if contains(read_document(destination), source.fragment):
                raise NativeConflictError(f"hook removal verification failed: {name}")
            return LifecycleResult("remove", "removed", destination)
        if record.fragment is None or not contains(document, record.fragment):
            if policy is ConflictPolicy.ABORT or not native_locator:
                raise NativeConflictError(f"owned hook changed outside Zuat: {name}")
            updated = remove_fragment_at_locator(document, native_locator)
        else:
            updated = remove(document, record.fragment)
        atomic_write(destination, write_document(updated))
        if contains(read_document(destination), record.fragment):
            raise NativeConflictError(f"hook removal verification failed: {name}")
        store.remove("hook", name, scope.value)
        return LifecycleResult("remove", "removed", destination)
    assert source is not None
    before = inspect_shared_hook(source=source, destination=destination, store=store, read_document=read_document, contains=contains, scope=scope)
    positioned: dict[str, object] | None = None
    locator_matches = True
    if positional_locator:
        try:
            positioned = replace_fragment_at_locator(
                document, positional_locator, source.fragment
            )
            locator_matches = positioned == document
        except ResolutionError:
            locator_matches = False
    if before.status is InspectionStatus.CURRENT and locator_matches:
        return LifecycleResult("install", "current", destination, before, before)
    if before.status is InspectionStatus.ADOPTABLE and locator_matches:
        store.save(OwnershipRecord(store.agent, "hook", name, scope.value, str(destination.resolve()), source.fingerprint, source.fragment, native_locator))
        return LifecycleResult("install", "adopted", destination, before, before)
    if (
        before.status is InspectionStatus.CONFLICT or not locator_matches
    ) and policy is ConflictPolicy.ABORT:
        raise NativeConflictError(f"hook destination is conflicting: {name}")
    if positional_locator and not locator_matches:
        # A stable semantic locator may be temporarily absent or may contain a
        # neighboring fragment after external array edits. Replace it when it
        # exists; otherwise add the desired fragment without discarding the
        # rest of the shared document.
        working = positioned if positioned is not None else add(document, source.fragment)
    else:
        working = document
        if (
            record is not None
            and record.fragment is not None
            and contains(working, record.fragment)
        ):
            working = remove(working, record.fragment)
        working = add(working, source.fragment)
    atomic_write(destination, write_document(working))
    verified = read_document(destination)
    if not contains(verified, source.fragment):
        raise NativeConflictError(f"hook postcondition verification failed: {name}")
    if positional_locator:
        try:
            if replace_fragment_at_locator(
                verified, positional_locator, source.fragment
            ) != verified:
                raise NativeConflictError(
                    f"hook locator verification failed: {name}"
                )
        except ResolutionError as error:
            raise NativeConflictError(
                f"hook locator verification failed: {name}"
            ) from error
    store.save(OwnershipRecord(store.agent, "hook", name, scope.value, str(destination.resolve()), source.fingerprint, source.fragment, native_locator))
    status = "installed" if before.status in {InspectionStatus.ABSENT, InspectionStatus.UNMANAGED} else "updated"
    return LifecycleResult("install", status, destination, before, Inspection(InspectionStatus.CURRENT, destination, source.fingerprint))
