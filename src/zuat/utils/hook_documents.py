"""Shared hook document shapes; each resolver selects the shape its agent uses."""

from __future__ import annotations

import re

from zuat.specs.interface import ResolutionError
from zuat.utils.documents import remove_fragment_at_locator, replace_fragment_at_locator


def _slug(value: str, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or fallback


class FragmentHookDocument:
    """Event fragments under a ``hooks`` mapping of arrays, or a ``hooks`` list.

    Ownership is a complete group of declarations matched by content; array
    positions are transient evidence only.
    """

    def group(self, document, desired, record, records, destination, scope):
        from zuat.utils.inspection import resolve_hook_group

        return resolve_hook_group(document, desired, record, records, destination, scope)

    def select(self, document, wanted):
        from zuat.utils.inspection import selected_fragment

        return selected_fragment(document, wanted)

    def entries(self, document) -> tuple[list[tuple[str, object, str]], list[str]]:
        """Split native declarations into one observable fragment per entry."""
        hooks = document.get("hooks")
        entries: list[tuple[str, object, str]] = []
        rejected: list[str] = []
        if hooks is None:
            return entries, rejected
        if isinstance(hooks, dict):
            for event, values in hooks.items():
                if not isinstance(event, str) or not isinstance(values, list):
                    rejected.append("hooks: native hooks mapping has an unsupported shape")
                    continue
                slug = _slug(event, "event")
                for index, entry in enumerate(values):
                    if not isinstance(entry, dict):
                        rejected.append(f"hooks: {event}/{index} is not an object")
                        continue
                    entries.append((f"{slug}-{index:03d}", {event: [entry]}, f"hooks/{event}/{index}"))
        elif isinstance(hooks, list):
            for index, entry in enumerate(hooks):
                if not isinstance(entry, dict):
                    rejected.append(f"hooks: {index} is not an object")
                    continue
                slug = _slug(str(entry.get("event", "hook")), "hook")
                entries.append((f"{slug}-{index:03d}", [entry], f"hooks/{index}"))
        else:
            rejected.append("hooks: native hooks value has an unsupported shape")
        return entries, rejected

    def claim_owned(self, document, records):
        """Regroup multi-declaration owned fragments so observation keeps their identity."""
        from zuat.utils.inspection import fragment_fingerprint, fragment_parts, selected_fragment

        groups = []
        claimed: set[str] = set()
        rejected: list[str] = []
        for record in records:
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
        return groups, claimed, rejected

    def positional(self, locator: str | None) -> str | None:
        parts = locator.split("/") if locator else []
        if len(parts) in {2, 3} and parts[0] == "hooks" and parts[-1].isdigit():
            return locator
        return None

    def remove_at(self, document, locator):
        return remove_fragment_at_locator(document, locator)

    def replace_at(self, document, locator, fragment):
        return replace_fragment_at_locator(document, locator, fragment)
