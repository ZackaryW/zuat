"""Compile and register atomically; no native installation is inferred here."""

import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from git.exc import GitError
from yaml import YAMLError

from zuat.pub.bundles.models import (
    BundleBuildError,
    BundleOutputError,
    BundleStoreError,
)
from zuat.pub.bundles.store import _plain_path
from zuat.utils.bundles.capture import fingerprint, identity, skills, tree
from zuat.utils.bundles.source import acquire


def build(service, source, *, name=None, revision="HEAD"):
    store = service._bundles
    with store.locked():
        state = store.read()
        try:
            with acquire(source, revision) as (root, kind, binding, commit):
                if (
                    root.is_relative_to(store.root)
                    or store.root.is_relative_to(root)
                    or root.is_relative_to(store.tracking)
                    or store.tracking.is_relative_to(root)
                ):
                    raise ValueError("source must be separate from stores")
                selected_name = identity(
                    name if name is not None else Path(binding.rstrip("/")).stem
                )
                bundle_id = (
                    selected_name
                    + "-"
                    + hashlib.sha256(f"{kind}\0{binding}".encode()).hexdigest()[:16]
                )
                previous = state["bundles"].get(bundle_id)
                if any(
                    item["name"] == selected_name and item["bundle_id"] != bundle_id
                    for item in state["bundles"].values()
                ):
                    raise ValueError("bundle name already bound to another source")
                captured = skills(tree(root))
                payload = captured.files
                adapters = {
                    agent: service._resolver(agent).bundle_adapter()
                    for agent in ("codex", "claude", "pi")
                }
                inputs = {
                    "name": selected_name,
                    "contracts": {a: b.contract for a, b in adapters.items()},
                }
                digest = fingerprint(
                    {
                        **payload,
                        "_renderer_inputs": json.dumps(inputs, sort_keys=True).encode(),
                    }
                )
                if previous and any(
                    item["build_revision"] == digest for item in previous["builds"]
                ):
                    # Content-addressed reuse retains the first build's provenance;
                    # a new ref resolving to identical inputs is not a new build.
                    for agent in adapters:
                        resolve(service, bundle_id, build_revision=digest, agent=agent)
                    return next(
                        item
                        for item in store.get(bundle_id).builds
                        if item.build_revision == digest
                    )
                version = "0.0.0-zuat." + digest
                destination = store.root / "builds" / bundle_id / digest
                _plain_path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError("unregistered build output exists")
                with TemporaryDirectory(prefix=".build-", dir=store.root) as staging:
                    staged = Path(staging) / "output"
                    hashes = {}
                    for agent, adapter in adapters.items():
                        output = {**payload, **adapter.render(selected_name, version)}
                        hashes[agent] = fingerprint(output)
                        for relative, data in output.items():
                            path = staged / agent / relative
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(data)
                    staged.replace(destination)
                record = previous or {
                    "bundle_id": bundle_id,
                    "name": selected_name,
                    "source": binding,
                    "source_kind": kind,
                    "builds": [],
                    "targets": [],
                }
                record["builds"].append(
                    {
                        "build_revision": digest,
                        "version": version,
                        "agents": list(adapters),
                        "source_commit": commit,
                        "source_revision": revision if kind == "git" else None,
                        "digests": hashes,
                        "sources": captured.sources,
                    }
                )
                state["bundles"][bundle_id] = record
                store.write(state)
                return store.get(bundle_id).builds[-1]
        except BundleOutputError:
            raise
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            subprocess.SubprocessError,
            GitError,
            YAMLError,
            BundleStoreError,
        ):
            # Native/process/source error payloads can contain credentials or bodies.
            raise BundleBuildError(
                "bundle source could not be safely compiled"
            ) from None


def resolve(service, bundle_id, *, build_revision=None, agent):
    """Validate the selected immutable output; do not repair or choose another build."""
    store = service._bundles
    record = store.get(bundle_id)
    selected = (
        next((b for b in record.builds if b.build_revision == build_revision), None)
        if build_revision
        else (record.builds[-1] if record.builds else None)
    )
    if selected is None or agent not in selected.agents:
        raise BundleOutputError("selected build or agent output is unavailable")
    output = store.root / "builds" / bundle_id / selected.build_revision / agent
    try:
        _plain_path(output)
        metadata = next(
            b
            for b in store.read()["bundles"][bundle_id]["builds"]
            if b["build_revision"] == selected.build_revision
        )
        if fingerprint(tree(output, skip=frozenset())) != metadata["digests"][agent]:
            raise ValueError("output digest mismatch")
        return output
    except (OSError, ValueError, KeyError, TypeError, BundleStoreError):
        raise BundleOutputError(
            "selected build output is missing or modified"
        ) from None
