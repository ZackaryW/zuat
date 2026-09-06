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


def selected_fragment(document, wanted):
    """Resolve an exact declaration first; never use incidental array position."""
    hooks = document.get("hooks", {} if isinstance(wanted, dict) else [])
    parts = fragment_parts(wanted)
    if len(parts) > 1:
        selected = [selected_fragment(document, part) for part in parts]
        keys = [fragment_fingerprint(part) for part in selected if part is not None]
        if len(keys) != len(set(keys)):
            raise ResolutionError("ambiguous overlapping hook declarations")
        observed = [
            part for part in fragment_parts(hooks) if fragment_fingerprint(part) in keys
        ]
        return (
            combine_fragments(observed, isinstance(wanted, dict)) if observed else None
        )
    if isinstance(wanted, dict):
        if len(wanted) != 1:
            raise ResolutionError("targeted hooks require one declaration")
        event, entries = next(iter(wanted.items()))
        if len(entries) != 1 or not isinstance(hooks, dict):
            raise ResolutionError(
                "targeted hooks require one declaration and valid native structure"
            )
        candidates = hooks.get(event, [])
        wrap = lambda value: {event: [value]}
        expected = entries[0]
    elif isinstance(wanted, list) and len(wanted) == 1 and isinstance(hooks, list):
        expected = wanted[0]
        if not isinstance(expected, dict) or any(
            not isinstance(item, dict) for item in hooks
        ):
            raise ResolutionError("malformed native hook declarations")
        candidates = [
            item for item in hooks if item.get("event") == expected.get("event")
        ]
        wrap = lambda value: [value]
    else:
        raise ResolutionError("targeted hooks require one declaration")
    if not isinstance(candidates, list) or any(
        not isinstance(item, dict) for item in candidates
    ):
        raise ResolutionError("malformed native hook declarations")
    exact = [item for item in candidates if item == expected]
    if len(exact) > 1:
        raise ResolutionError("ambiguous duplicate hook declarations")
    if exact:
        return wrap(exact[0])
    if not candidates:
        return None
    # A single event declaration is unambiguous even if its body was edited.
    # Multiple edited candidates do not grant authority to choose one.
    if len(candidates) == 1:
        return wrap(candidates[0])
    raise ResolutionError("ambiguous hook declaration identity")


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
        fragment = selected_fragment(
            document, record.fragment if record else source.fragment
        )
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
    if (fresh.observed_fingerprint, fresh.record) != (
        target.observed_fingerprint,
        target.record,
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
