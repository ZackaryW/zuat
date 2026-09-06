"""Host-registered artifact resolution and journal-backed selection policy."""

import hashlib
import json
from dataclasses import replace

from zuat.gitcore import OperationKind, OperationOutcome
from zuat.pub.artifact_models import (
    ArtifactStatus,
    PluginArtifactContext,
)
from zuat.pub.models import OperationResult, OperationStatus
from zuat.pub.results import failed
from zuat.pub.extensions import ZuatExtension, _register, _registrations
from zuat.specs.interface import ResolutionError
from zuat.utils.contexts import project_context
from zuat.utils.runtime_paths import contained_path

class ArtifactOperations:
    """Resolve runtime artifacts while journaling only host selection policy.

    Paths and locator callables remain runtime values, not plugin source payloads
    or durable assertions that a native installation is active.
    """

    def __init__(self, service):
        self.service = service
        self.extensions = _registrations()

    def register(self, extension: ZuatExtension):
        """Register a locator on this service; reject conflicting code for one ID."""
        _register(self.extensions, extension)

    def _key(self, ref, identifier):
        """Bind policy to installation context rather than a plugin name alone.

        The same plugin can be installed in two projects; one project's host policy
        must not enable or disable artifacts in the other.
        """
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
        """Replay the latest policy event instead of maintaining a second policy store."""
        key = self._key(ref, identifier)
        for event in reversed(self.service.registry.history()):
            if (
                event.kind is OperationKind.ARTIFACT_POLICY
                and event.metadata.get("policy_key") == key
            ):
                return str(event.metadata["policy"])
        return "inherit"

    def status(self, ref, identifier, *, revision=None):
        """Gate host artifact eligibility on current native installation evidence.

        An enabled host policy cannot override native disablement or a stale revision.
        Resolve paths only after these checks, and enforce runtime-root containment.
        """
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
        except Exception:
            # Host locators are arbitrary code; expose neither their exceptions
            # nor possible credentials as durable policy or native evidence.
            return replace(result, reason="artifact-locator-failed")
        return replace(
            result,
            effective=bool(paths),
            reason="eligible" if paths else "artifact-unavailable",
            paths=paths,
        )

    def resolve(self, agent, identifier):
        """Return effective artifacts only; discovery alone does not imply eligibility."""
        if identifier not in self.extensions:
            raise ValueError("unknown artifact extension")
        adapter = self.service._resolver(agent).plugin_adapter()
        statuses = tuple(
            self.status(record.ref, identifier) for record in adapter.discover()
        )
        return tuple(status for status in statuses if status.effective)

    def set_policy(self, ref, identifier, policy):
        """Append host policy without claiming a native enable/disable operation.

        Only context-bound identifiers and policy are durable; locator code and
        resolved plugin paths remain outside the journal.
        """
        if identifier not in self.extensions or policy not in {
            "inherit",
            "enabled",
            "disabled",
        }:
            return failed("artifact-policy", "unknown extension or invalid policy")
        try:
            key = self._key(ref, identifier)
        except ValueError:
            return failed(
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
