"""Read-only lookup of the installed skill an agent selects for an invocation.

Deliberately independent of ``zuat.pub.service`` and the Git registry: lookup
must work with no registry present and must never create one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zuat.pub.models import SUPPORTED_AGENTS

OUTCOMES = ("located", "missing", "unresolved", "unsupported", "invalid")


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    """One installed copy of the requested skill and the native tier that found it."""

    tier: str
    path: Path


@dataclass(frozen=True, slots=True)
class SkillLocation:
    """Outcome of a lookup; location fields are set only when ``outcome == "located"``."""

    outcome: str
    agent: str
    name: str
    root: Path | None = None
    entrypoint: Path | None = None
    scope: str | None = None
    provider: str | None = None
    provenance: str | None = None
    candidates: tuple[SkillCandidate, ...] = ()
    diagnostics: tuple[str, ...] = ()


def _unsupported(agent: str, name: str, message: str) -> SkillLocation:
    return SkillLocation("unsupported", agent, name, diagnostics=(message,))


def locate_skill(
    agent: str,
    name: str,
    *,
    cwd: str | Path,
    home: str | Path | None = None,
    selected: str | Path | None = None,
) -> SkillLocation:
    """Locate the installed skill ``agent`` selects for ``cwd`` without any writes.

    ``selected`` is the installed path the host reported loading; it is validated
    against the agent's candidates and never replaced by another copy.
    """
    if agent not in SUPPORTED_AGENTS:
        return _unsupported(agent, name, f"unsupported agent: {agent}")
    if ":" in name:
        return _unsupported(
            agent,
            name,
            f"plugin-qualified skill names are unsupported: {name}",
        )
    # Imported here so importing zuat.pub never loads agent adapters.
    from zuat.specs.registry import resolver_for
    from zuat.utils.skill_lookup import select_skill

    resolver = resolver_for(agent, home=home)
    search = resolver.skill_search(Path(cwd))
    selection = select_skill(search, name, agent=agent, selected=selected)
    candidates = tuple(
        SkillCandidate(candidate.tier, candidate.path)
        for candidate in selection.candidates
    )
    chosen = selection.selected
    if selection.outcome != "located" or chosen is None:
        return SkillLocation(
            selection.outcome,
            agent,
            name,
            candidates=candidates,
            diagnostics=selection.diagnostics,
        )
    return SkillLocation(
        "located",
        agent,
        name,
        root=chosen.root,
        entrypoint=chosen.root / "SKILL.md",
        scope=chosen.scope,
        provider="global",
        provenance=selection.provenance,
        candidates=candidates,
        diagnostics=selection.diagnostics,
    )
