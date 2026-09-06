"""Bridge historical evidence to resolver-readable profiles.

Temporary inverse projections describe the native content to recover. Publishing
the managed profile is a separate step after verification: actual local content
and the last owned baseline can differ, especially after forced replacement.
Plugin revisions always remain pointers, never copied plugin source trees."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from zuat.gitcore import (
    AssetEvidence,
    Authority,
    RegistryError,
)
from zuat.specs.interface import (
    Asset,
    AssetKind,
    ConflictPolicy,
    ResolutionPlan,
)
from zuat.utils.payloads import (
    copy_asset,
    write_asset_metadata,
)

if TYPE_CHECKING:
    from zuat.pub.service import Zuat


class AssetProjections:
    """Shared inverse projection mechanics; transaction ownership stays with callers."""

    def __init__(self, service: Zuat) -> None:
        self.service = service

    def archive_current_evidence(self, evidence: Sequence[AssetEvidence]) -> None:
        """Preserve conflicting observed bytes before a forced inverse overwrites them.

        The observation projection must already be refreshed under the caller's
        operation lock; desired profile content is not a substitute for this state.
        """
        service = self.service
        for item in evidence:
            if not item.present or not item.fingerprint:
                continue
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(f"asset has no normalized payload: {item.ref.id}")
            service.registry.archive_asset(
                item.ref,
                normalized,
                service.registry.observation_root / Path(normalized),
                item.fingerprint,
            )

    def restore_plans(
        self, temporary_profile: Path, desired: Sequence[AssetEvidence]
    ) -> tuple[ResolutionPlan, ...]:
        """Restrict resolver plans to the selected recovery targets.

        A full profile also contains neighbors and other contexts. Restoring one
        asset must not accidentally reconcile them; native preflight still owns
        path safety and authority validation for each selected action.
        """
        service = self.service
        selected_keys: dict[str, set[tuple[str, str, str]]] = {}
        for item in desired:
            selected_keys.setdefault(item.ref.agent, set()).add(
                (item.ref.kind, item.ref.scope, item.ref.locator)
            )
        complete = tuple(
            service._resolver(agent).plan(
                temporary_profile,
                conflict_policy=ConflictPolicy.REPLACE,
            )
            for agent in selected_keys
        )
        return tuple(
            ResolutionPlan(
                plan.agent,
                plan.root,
                tuple(
                    action
                    for action in plan.actions
                    if action.operation == "install"
                    and (
                        action.asset.kind.value,
                        action.asset.scope,
                        str(action.asset.evidence.get("native_locator")),
                    )
                    in selected_keys[plan.agent]
                ),
                plan.conflict_policy,
            )
            for plan in complete
        )

    def write_inverse_profile(
        self, root: Path, desired: Sequence[AssetEvidence]
    ) -> None:
        """Build temporary native input from actual historical content or pointers.

        This does not publish desired state. Ownership-bearing sidecars request
        semantic targeted replacement, so moved shared-hook declarations can be
        restored without treating an old array position as their identity.
        """
        service = self.service
        for item in desired:
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(f"asset has no normalized payload: {item.ref.id}")
            target = root / Path(normalized)
            if item.present:
                if item.ref.kind == "plugin":
                    from zuat.utils.plugin_pointers import (
                        evidence_pointer,
                        write_pointer,
                    )

                    write_pointer(target, evidence_pointer(item.evidence))
                    write_asset_metadata(target, item.ref)
                    continue
                payload = service.registry.asset_payload(item.ref, item.fingerprint)
                if not payload.exists():
                    raise RegistryError(
                        f"archived payload is unavailable: {item.ref.id}"
                    )
                copy_asset(payload, target)
                write_asset_metadata(
                    target, item.ref, targeted="ownership" in item.evidence
                )
            else:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
                target.with_name(f"{target.name}.zuat.json").unlink(missing_ok=True)

    def project_inverse_profile(
        self, profile: str, desired: Sequence[AssetEvidence]
    ) -> None:
        """Publish managed state only after native restoration has been verified.

        Restore receipt and owned baseline separately from recovered bytes: forced
        updates can start from unowned or locally modified content. Adopting those
        bytes as the baseline would silently grant authority during rollback.
        """
        service = self.service
        profile_ids = set(service.registry.projected_state().profile(profile).assets)
        for item in desired:
            normalized = item.evidence.get("normalized_path")
            if not isinstance(normalized, str):
                raise RegistryError(f"asset has no normalized payload: {item.ref.id}")
            if "ownership" in item.evidence:
                asset = Asset(
                    item.ref.agent,
                    AssetKind(item.ref.kind),
                    str(item.evidence["asset_name"]),
                    Path(normalized),
                    item.ref.scope,
                )
                service._resolver(item.ref.agent).restore_asset_ownership(
                    asset, item.evidence["ownership"]
                )
                baseline = item.evidence.get("owned_profile_fingerprint")
                if baseline:
                    service.registry.store_profile_asset(
                        profile,
                        item.ref,
                        normalized,
                        service.registry.asset_payload(item.ref, baseline),
                        baseline,
                    )
                elif item.ref.id in profile_ids:
                    service.registry.remove_profile_asset(profile, item.ref, normalized)
                continue
            if item.present and item.authority is Authority.AUTHORITATIVE:
                if item.ref.kind == "plugin":
                    from zuat.utils.plugin_pointers import evidence_pointer

                    service.registry.store_profile_pointer(
                        profile, item.ref, normalized, evidence_pointer(item.evidence)
                    )
                    continue
                payload = service.registry.asset_payload(item.ref, item.fingerprint)
                assert item.fingerprint is not None
                service.registry.store_profile_asset(
                    profile, item.ref, normalized, payload, item.fingerprint
                )
            elif item.ref.id in profile_ids:
                service.registry.remove_profile_asset(profile, item.ref, normalized)

    def profile_fingerprint(self, ref, path: Path) -> str:
        """Use agent-native semantics so profile and observed fingerprints agree.

        Shared hook documents are semantic fragments, not generic file hashes.
        """
        service = self.service
        value = service._resolver(ref.agent).fingerprint(path, AssetKind(ref.kind))
        return value if ":" in value else f"sha256:{value}"
