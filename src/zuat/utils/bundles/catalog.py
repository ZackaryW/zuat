"""Neutral bounded catalog projection; agent modules supply native schema/commands."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from zuat.utils.bundles.capture import fingerprint, tree
from zuat.utils.bundles.paths import reject_links
from zuat.utils.mutation import atomic_write


def catalog_name(bundle_id):
    """Namespaced by the whole bundle, including distinct names for one source."""
    return "zuat-" + hashlib.sha256(bundle_id.encode()).hexdigest()[:20]


def project(root, output, manifest_path, document):
    """Retain validated generations and atomically change the managed catalog only."""
    reject_links(root)
    reject_links(root / manifest_path)
    root.mkdir(parents=True, exist_ok=True)
    payload = tree(output, skip=frozenset())
    destination = root / "plugins" / output.parent.name
    reject_links(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if fingerprint(tree(destination, skip=frozenset())) != fingerprint(payload):
            raise ValueError("modified catalog projection")
    else:
        with TemporaryDirectory(prefix=".catalog-", dir=root) as temporary:
            staged = Path(temporary) / "plugin"
            for relative, data in payload.items():
                path = staged / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            staged.replace(destination)
    atomic_write(root / manifest_path, json.dumps(document, sort_keys=True).encode())


def ensure_native_home(native):
    """Create an explicitly selected home without writing native configuration."""
    # Codex requires an explicitly selected config home to exist even for list.
    # Creating its directory is not emulating or editing native manager state.
    config = native.home / native.config_directory
    reject_links(config)
    config.mkdir(parents=True, exist_ok=True)


def ensure_catalog(native, root, name, *, list_args, add_args, decode):
    """Check identity and source, not a name-only guess at catalog ownership."""
    ensure_native_home(native)
    result = native._run(list_args)
    if result.returncode != 0:
        raise ValueError("catalog discovery unavailable")
    selected = [item for item in decode(result.stdout) if item[0] == name]
    if selected:
        if (
            len(selected) != 1
            or selected[0][1] is None
            or Path(selected[0][1]).resolve() != root.resolve()
        ):
            raise ValueError("catalog identity conflict")
        return
    result = native._run(add_args)
    if result.returncode != 0:
        raise ValueError("catalog registration failed")
    verified = native._run(list_args)
    if verified.returncode != 0:
        raise ValueError("catalog verification failed")
    selected = [item for item in decode(verified.stdout) if item[0] == name]
    if (
        len(selected) != 1
        or selected[0][1] is None
        or Path(selected[0][1]).resolve() != root.resolve()
    ):
        raise ValueError("catalog source could not be verified")
