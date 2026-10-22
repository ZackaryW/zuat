"""Targeted, non-authorizing source/baseline comparison mechanics."""

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from zuat.specs.interface import Asset, AssetKind, ConflictPolicy, ResolutionError
from zuat.specs.native import Scope, SkillSource, UnsupportedNativeOperation
from zuat.utils.assets import collect_files, fingerprint
from zuat.utils.contexts import contextual_locator, native_locator
from zuat.utils.lifecycle import apply_dedicated
from zuat.utils.mutation import atomic_write, mirror_files
from zuat.utils.ownership import OwnershipRecord


@dataclass(frozen=True)
class TargetInspection:
    asset: Asset
    source: object
    destination: Path
    record: object
    classification: str
    observed_fingerprint: str | None
    fragment: object = None
    diagnostics: tuple[str, ...] = ()


def fragment_fingerprint(fragment):
    return sha256(
        json.dumps(fragment, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fragment_parts(fragment):
    if isinstance(fragment, dict) and all(
        isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries)
        for entries in fragment.values()
    ):
        return [
            {event: [entry]} for event, entries in fragment.items() for entry in entries
        ]
    if isinstance(fragment, list) and all(
        isinstance(entry, dict) for entry in fragment
    ):
        return [[entry] for entry in fragment]
    raise ResolutionError("malformed native hook declarations")


def combine_fragments(parts, mapping):
    if mapping:
        result = {}
        for part in parts:
            for event, entries in part.items():
                result.setdefault(event, []).extend(entries)
        return result
    return [entry for part in parts for entry in part]


@dataclass(frozen=True)
class GroupSelection:
    """Pure complete-group evidence; positions are transient document offsets."""

    status: str
    fragment: object = None
    positions: tuple[int, ...] = ()


def exact_group(document, wanted):
    """Select mapping/list declarations one-to-one, preserving native order.

    An empty event is absent; differing same-event candidates are ambiguous.
    Partial matches never identify an entire group. Inputs are never mutated.
    """
    mapping = isinstance(wanted, dict)
    hooks = document.get("hooks", {} if mapping else [])
    parts = fragment_parts(wanted)
    if not parts or isinstance(hooks, dict) != mapping:
        raise ResolutionError("malformed native hook declarations")
    keys = [fragment_fingerprint(part) for part in parts]
    if len(keys) != len(set(keys)):
        raise ResolutionError("ambiguous duplicate requested hook declarations")
    native = fragment_parts(hooks)
    positions = []
    for part in parts:
        matches = [i for i, candidate in enumerate(native) if candidate == part]
        if len(matches) > 1 or any(i in positions for i in matches):
            return GroupSelection("ambiguous")
        positions.extend(matches)
    positions = tuple(sorted(positions))
    selected = combine_fragments([native[i] for i in positions], mapping)
    if len(positions) == len(parts):
        return GroupSelection("complete", selected, positions)
    if positions:
        return GroupSelection("partial", selected, positions)
    events = {_part_event(part) for part in parts}
    if any(_part_event(part) in events for part in native):
        return GroupSelection("ambiguous")
    return GroupSelection("absent")


def _part_event(part):
    return next(iter(part)) if isinstance(part, dict) else part[0].get("event")


def selected_fragment(document, wanted):
    """Resolve complete groups; allow only a sole candidate for edited members."""
    exact = exact_group(document, wanted)
    if exact.status == "complete":
        return exact.fragment
    if exact.status == "absent":
        return None
    mapping = isinstance(wanted, dict)
    native = fragment_parts(document.get("hooks", {} if mapping else []))
    positions = []
    for part in fragment_parts(wanted):
        matches = [i for i, candidate in enumerate(native) if candidate == part]
        if not matches:
            matches = [i for i, candidate in enumerate(native)
                       if _part_event(candidate) == _part_event(part)]
        if len(matches) != 1 or matches[0] in positions:
            raise ResolutionError("ambiguous or incomplete hook declaration group")
        positions.extend(matches)
    return combine_fragments([native[i] for i in sorted(positions)], mapping)


def resolve_hook_group(document, desired, record, records, destination, scope):
    """Reconcile exact content with receipt identity, without granting authority."""
    source = exact_group(document, desired)
    if record is None:
        if source.status not in {"complete", "absent"}:
            raise ResolutionError("ambiguous or incomplete unowned hook group")
        selected = source.fragment
    else:
        baseline = exact_group(document, record.fragment)
        native = fragment_parts(document.get("hooks", {} if isinstance(desired, dict) else []))
        surviving = {i for i, part in enumerate(native) if part in fragment_parts(record.fragment)}
        if source.status == "complete" and not surviving.issubset(source.positions):
            raise ResolutionError("competing baseline and source hook groups")
        if baseline.status == "complete":
            source_members = {i for i, part in enumerate(native) if part in fragment_parts(desired)}
            if not source_members.issubset(baseline.positions):
                raise ResolutionError("competing baseline and source hook groups")
            selected = baseline.fragment
        elif source.status == "complete":
            selected = source.fragment
        else:
            selected = selected_fragment(document, record.fragment)
    if selected is not None:
        members = fragment_parts(selected)
        for other in records:
            if other == record or other.scope != scope or Path(other.destination) != destination.resolve():
                continue
            if other.fragment is not None and any(part in members for part in fragment_parts(other.fragment)):
                raise ResolutionError("hook group overlaps another ownership claim")
            if other.fragment is not None and exact_group(document, other.fragment).status != "complete":
                events = {_part_event(part) for part in fragment_parts(other.fragment)}
                if any(_part_event(part) in events for part in members):
                    raise ResolutionError("hook group has an unresolved competing ownership claim")
    return selected


def resolve_source(support, source_path, kind, scope, *, name=None, locator=None):
    kind = AssetKind(kind)
    scope = Scope(scope)
    if kind not in {AssetKind.SKILL, AssetKind.HOOK} or scope not in support.scopes:
        raise UnsupportedNativeOperation("unsupported independent asset kind or scope")
    source = (
        SkillSource.from_path(source_path)
        if kind is AssetKind.SKILL
        else support.hook_loader(source_path)
    )
    if support.agent not in source.compatible_agents:
        raise UnsupportedNativeOperation("source is incompatible with selected agent")
    if name is not None and name != source.name:
        raise ResolutionError("source identity does not match requested name")
    name = source.name
    plural = (
        "skills"
        if kind is AssetKind.SKILL
        else "hooks"
        if support.shared_hooks
        else "extensions"
    )
    suffix_name = name if plural != "extensions" else source.path.name
    canonical = contextual_locator(
        scope.value, f"{plural}/{suffix_name}", support.context
    )
    if locator is not None and locator != canonical:
        raise ResolutionError("source identity does not match requested locator")
    asset = Asset(
        support.agent.value,
        kind,
        name,
        source.path,
        scope.value,
        {"native_locator": canonical},
    )
    return asset, source


def inspect_target(support, source_path, kind, scope, *, name=None, locator=None):
    asset, source = resolve_source(support, source_path, kind, scope, name=name)
    kind, scope, name = asset.kind, Scope(asset.scope), asset.name
    destination = support._destination(asset, scope)
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ResolutionError("target path contains a symbolic link")
    base_store = support.bind(support.state_root or support.home)
    store = support.ordinary_store(base_store, scope)
    record = store.load(kind.value, name, scope.value)
    if record is not None and (
        Path(record.destination) != destination.resolve()
        or not isinstance(record.fingerprint, str)
        or len(record.fingerprint) != 64
        or any(value not in "0123456789abcdef" for value in record.fingerprint)
    ):
        raise ResolutionError("invalid ownership destination or baseline")
    if record is not None and kind is AssetKind.HOOK and record.native_locator:
        asset = replace(
            asset,
            evidence={
                "native_locator": contextual_locator(
                    scope.value, record.native_locator, support.context
                )
            },
        )
    if locator is not None and locator != asset.evidence["native_locator"]:
        raise ResolutionError("source identity does not match requested locator")
    # Owned independent receipts establish provider eligibility even offline.
    if record is None:
        adapter = support.plugins(base_store)
        try:
            plugins = adapter.discover()
        except (ResolutionError, OSError, ValueError) as error:
            raise ResolutionError(
                "independent provider cannot be established"
            ) from error
        if getattr(adapter, "discovery_diagnostics", ()):
            raise ResolutionError("independent provider cannot be established")
        roots = tuple(
            item.runtime_root for item in plugins if item.runtime_root
        ) + tuple(getattr(adapter, "unresolved_roots", ()))
        if any(destination.resolve().is_relative_to(root.resolve()) for root in roots):
            raise UnsupportedNativeOperation(
                "plugin contributions require the plugin lifecycle"
            )
    fragment = None
    if kind is AssetKind.HOOK and support.shared_hooks:
        if record is not None and (
            record.fragment is None
            or fragment_fingerprint(record.fragment) != record.fingerprint
        ):
            raise ResolutionError("invalid ownership fragment baseline")
        document = support.read_document(destination)
        try:
            fragment = resolve_hook_group(
                document, source.fragment, record, store.records("hook"), destination, scope.value
            )
        except ResolutionError as error:
            return TargetInspection(asset, source, destination, record, "indeterminate", None,
                                    diagnostics=(str(error),))
        actual = fragment_fingerprint(fragment) if fragment is not None else None
    else:
        actual = (
            fingerprint(collect_files(destination)) if destination.exists() else None
        )
    if actual is None:
        classification = "absent"
    elif record is None:
        classification = "unowned"
    elif actual != record.fingerprint:
        classification = "conflict"
    else:
        classification = "current" if actual == source.fingerprint else "outdated"
    return TargetInspection(
        asset, source, destination, record, classification, actual, fragment
    )


def capture_target(support, target, output):
    if target.asset.kind is AssetKind.HOOK and support.shared_hooks:
        atomic_write(output, support.serialize_fragment(target.fragment))
    elif target.destination.is_dir():
        mirror_files(output, collect_files(target.destination))
    else:
        atomic_write(output, target.destination.read_bytes())


def replace_target(support, target):
    fresh = inspect_target(
        support,
        target.source.path,
        target.asset.kind,
        target.asset.scope,
        name=target.asset.name,
    )
    if (fresh.observed_fingerprint, fresh.record, fresh.source.fingerprint) != (
        target.observed_fingerprint,
        target.record,
        target.source.fingerprint,
    ):
        raise ResolutionError("target changed during update preflight")
    scope = Scope(target.asset.scope)
    store = support.ordinary_store(
        support.bind(support.state_root or support.home), scope
    )
    if target.asset.kind is AssetKind.HOOK and support.shared_hooks:
        document = support.read_document(target.destination)
        selected = selected_fragment(document, target.fragment)
        if selected != target.fragment:
            raise ResolutionError("target changed before hook replacement")
        if selected != target.source.fragment:
            updated = support.add(
                support.remove(document, selected), target.source.fragment
            )
            atomic_write(target.destination, support.write_document(updated))
        if (
            selected_fragment(
                support.read_document(target.destination), target.source.fragment
            )
            != target.source.fragment
        ):
            raise ResolutionError("hook postcondition verification failed")
        store.save(
            OwnershipRecord(
                support.agent.value,
                "hook",
                target.asset.name,
                scope.value,
                str(target.destination.resolve()),
                target.source.fingerprint,
                target.source.fragment,
                native_locator(target.asset.evidence["native_locator"]),
            )
        )
    else:
        apply_dedicated(
            operation="install",
            source=target.source,
            destination=target.destination,
            store=store,
            kind=target.asset.kind.value,
            name=target.asset.name,
            scope=scope,
            policy=ConflictPolicy.REPLACE,
        )


def restore_receipt(support, asset, ownership):
    scope = Scope(asset.scope)
    store = support.ordinary_store(
        support.bind(support.state_root or support.home), scope
    )
    if ownership is None:
        store.remove(asset.kind.value, asset.name, asset.scope)
    else:
        store.save(
            OwnershipRecord(
                **ownership,
                destination=str(support._destination(asset, scope).resolve()),
            )
        )
