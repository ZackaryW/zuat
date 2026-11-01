"""Derived, disposable answers folded from the private operation journal.

The journal stays the only source of truth. This index lets a fresh registry
handle answer sequence, lookup, observation and policy queries without decoding
operation documents; any doubt about it is resolved by rebuilding from the journal.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from zuat.gitcore.models import AssetEvidence, JournalEvent, OperationKind

INDEX_VERSION = 1
OBSERVATION_KINDS = frozenset({OperationKind.OBSERVE, OperationKind.OBSERVE_DELTA})


def apply_observation(
    retained: Mapping[str, AssetEvidence],
    after: Iterable[AssetEvidence],
    *,
    agents: Iterable[str],
    completeness: str,
    context: str | None,
) -> dict[str, AssetEvidence]:
    """Apply one full observation; only complete ones retire unseen evidence."""
    from zuat.utils.contexts import evidence_context
    after = tuple(after)
    result = dict(retained)
    if completeness == "complete":
        selected = set(agents) or {item.ref.agent for item in after}
        result = {
            asset_id: item
            for asset_id, item in result.items()
            if item.ref.agent not in selected or evidence_context(item) not in {None, context}
        }
    result.update({item.ref.id: item for item in after})
    return result


@dataclass
class JournalIndex:
    sequence: int = 0
    document: str | None = None
    operations: dict[str, str] = field(default_factory=dict)
    observation_identity: str | None = None
    observation: dict[str, AssetEvidence] = field(default_factory=dict)
    policies: dict[str, str] = field(default_factory=dict)

    def fold(self, event: JournalEvent, document: str) -> None:
        if event.kind is OperationKind.OBSERVE:
            self.observation = apply_observation(
                self.observation,
                event.after,
                agents=(str(agent) for agent in event.metadata.get("observation_agents", [])),
                completeness=event.completeness,
                context=event.metadata.get("observation_context"),
            )
        elif event.kind is OperationKind.OBSERVE_DELTA:
            for asset_id in event.metadata.get("observation_removed", []):
                self.observation.pop(str(asset_id), None)
            self.observation.update({item.ref.id: item for item in event.after})
        elif event.kind is OperationKind.ARTIFACT_POLICY and "policy_key" in event.metadata:
            self.policies[str(event.metadata["policy_key"])] = str(event.metadata["policy"])
        if event.kind in OBSERVATION_KINDS:
            identity = event.metadata.get("observation_identity")
            self.observation_identity = str(identity) if identity is not None else None
        self.operations[event.operation_id] = document
        self.sequence, self.document = event.sequence, document

    def to_dict(self) -> dict[str, object]:
        return {
            "version": INDEX_VERSION,
            "sequence": self.sequence,
            "document": self.document,
            "operations": dict(self.operations),
            "observation_identity": self.observation_identity,
            "observation": [self.observation[key].to_dict() for key in sorted(self.observation)],
            "policies": dict(self.policies),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, object], decode: Callable[[object], AssetEvidence]
    ) -> JournalIndex:
        """Raise ValueError/TypeError/KeyError for any document this version did not write."""
        if value.get("version") != INDEX_VERSION:
            raise ValueError("unsupported journal index version")
        observation = tuple(decode(item) for item in value["observation"])
        identity = value["observation_identity"]
        document = value["document"]
        return cls(
            sequence=int(value["sequence"]),
            document=str(document) if document is not None else None,
            operations={str(k): str(v) for k, v in dict(value["operations"]).items()},
            observation_identity=str(identity) if identity is not None else None,
            observation={item.ref.id: item for item in observation},
            policies={str(k): str(v) for k, v in dict(value["policies"]).items()},
        )


__all__ = ["INDEX_VERSION", "OBSERVATION_KINDS", "JournalIndex", "apply_observation"]
