"""Host-registered artifact resolution and journal-backed selection policy."""

import hashlib
import json
from dataclasses import replace

from zuat.gitcore import OperationKind, OperationOutcome
from zuat.pub.artifact_models import (
    ArtifactExtension,
    ArtifactStatus,
    PluginArtifactContext,
)
from zuat.pub.models import OperationResult, OperationStatus
from zuat.specs.interface import ResolutionError
from zuat.utils.runtime_paths import contained_path
from zuat.utils.contexts import project_context


_registered: dict[str, ArtifactExtension] = {}


def register_extension(extension):
    if (
        extension.identifier in _registered
        and _registered[extension.identifier] != extension
    ):
        raise ValueError("artifact extension is already registered")
    _registered[extension.identifier] = extension


class ArtifactOperations:
    def __init__(self, service):
        self.service = service
        self.extensions: dict[str, ArtifactExtension] = dict(_registered)

    def register(self, extension: ArtifactExtension):
        if (
            extension.identifier in self.extensions
            and self.extensions[extension.identifier] != extension
        ):
            raise ValueError("artifact extension is already registered")
        self.extensions[extension.identifier] = extension

    def _key(self, ref, identifier):
        context = (
            project_context(self.service.project_root)
            if ref.scope in {"project", "local"}
            else None
        )
        if (ref.scope in {"project", "local"} and context is None) or (
            ref.context is not None and ref.context != context
        ):
            raise ValueError(
                "artifact policy requires the selected installation context"
            )
        return hashlib.sha256(
            json.dumps(
                [ref.agent.value, ref.native_ref, ref.scope.value, context, identifier]
            ).encode()
        ).hexdigest()

    def _policy(self, ref, identifier):
        key = self._key(ref, identifier)
        for event in reversed(self.service.registry.history()):
            if (
                event.kind is OperationKind.ARTIFACT_POLICY
                and event.metadata.get("policy_key") == key
            ):
                return str(event.metadata["policy"])
        return "inherit"

    def status(self, ref, identifier, *, revision=None):
        result = ArtifactStatus(ref, identifier)
        if identifier not in self.extensions:
            return replace(result, reason="unknown-extension")
        try:
            policy = self._policy(ref, identifier)
        except ValueError:
            return replace(result, reason="installation-context-unavailable")
        result = replace(result, policy=policy)
        try:
            adapter = self.service._resolver(ref.agent.value).plugin_adapter()
            record = next(
                (
                    item
                    for item in adapter.discover()
                    if item.ref.native_ref == ref.native_ref
                    and item.ref.scope == ref.scope
                    and item.installed
                ),
                None,
            )
        except (ResolutionError, OSError, ValueError):
            return replace(result, reason="discovery-unavailable")
        if record is None:
            return replace(result, reason="plugin-unavailable")
        result = replace(result, revision=record.revision)
        if revision is not None and revision != record.revision:
            return replace(result, reason="stale-revision")
        if record.activation == "inactive":
            return replace(result, reason="native-disabled")
        if policy == "disabled":
            return replace(result, reason="policy-disabled")
        if record.runtime_root is None:
            return replace(result, reason="runtime-root-unavailable")
        context = PluginArtifactContext(
            record.ref, record.revision, record.runtime_root
        )
        try:
            paths = tuple(
                contained_path(context.runtime_root, path)
                for path in self.extensions[identifier].locate(context)
            )
        except (OSError, ValueError, TypeError):
            return replace(result, reason="unsafe-artifact-path")
        return replace(
            result,
            effective=bool(paths),
            reason="eligible" if paths else "artifact-unavailable",
            paths=paths,
        )

    def resolve(self, agent, identifier):
        if identifier not in self.extensions:
            raise ValueError("unknown artifact extension")
        adapter = self.service._resolver(agent).plugin_adapter()
        statuses = tuple(
            self.status(record.ref, identifier) for record in adapter.discover()
        )
        return tuple(status for status in statuses if status.effective)

    def set_policy(self, ref, identifier, policy):
        if identifier not in self.extensions or policy not in {
            "inherit",
            "enabled",
            "disabled",
        }:
            return self.service._failed(
                "artifact-policy", "unknown extension or invalid policy"
            )
        try:
            key = self._key(ref, identifier)
        except ValueError:
            return self.service._failed(
                "artifact-policy",
                "artifact policy requires the selected installation context",
            )
        with self.service.registry.operation():
            event = self.service.registry.append_event(
                OperationKind.ARTIFACT_POLICY,
                OperationOutcome.SUCCESS,
                profile=self.service.registry.projected_state().selected_profile,
                metadata={
                    "policy_key": key,
                    "policy": policy,
                    "artifact_id": identifier,
                    "plugin_ref": ref.to_dict(),
                },
            )
        return OperationResult(
            "artifact-policy", OperationStatus.SUCCESS, operation_id=event.operation_id
        )
