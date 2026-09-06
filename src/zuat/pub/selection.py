"""Selection guards shared by public orchestration, without native mutation."""

from __future__ import annotations

from collections.abc import Sequence

from zuat.gitcore import (
    AssetEvidence,
)
from zuat.pub.models import (
    SUPPORTED_AGENTS,
    AssetSelector,
)
from zuat.specs.interface import (
    ResolutionError,
)


def select_present(
    assets: Sequence[AssetEvidence], selector: AssetSelector
) -> tuple[AssetEvidence, ...]:
    """Reject ambiguous names and bundled contributions before bulk mutation.

    Plugin contributions have their own provider lifecycle; ordinary helpers
    must not turn a convenient selector into independent ownership of them.
    """
    selected = tuple(item for item in assets if item.present and selector.matches(item))
    if selector.name and len(selected) > 1:
        raise ResolutionError("ambiguous asset name; select its provider")
    if any(item.evidence.get("provider") == "plugin" for item in selected):
        raise ResolutionError(
            "bundled plugin contributions cannot be independently mutated"
        )
    return selected


def validate_agents(agents: tuple[str, ...]) -> tuple[str, ...]:
    """Validate selection before resolver construction while preserving caller order."""
    unknown = set(agents).difference(SUPPORTED_AGENTS)
    if unknown:
        raise ResolutionError(f"unsupported agents: {', '.join(sorted(unknown))}")
    if len(set(agents)) != len(agents):
        raise ResolutionError("agents must not be repeated")
    return agents
