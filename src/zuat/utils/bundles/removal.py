"""Bounded filesystem removal; callers establish domain ownership beforehand."""

import os
import shutil
from pathlib import Path

from zuat.utils.bundles.capture import MAX_FILES, regular
from zuat.utils.bundles.paths import reject_links


def remove_trees(boundary: Path, targets: tuple[Path, ...]):
    """Validate every subtree before deleting any, never following reparse points.

    This is explicit deletion, not a glob sweep. Missing trees permit retry after
    a partial I/O failure; the owning registry must remain until all are absent.
    """
    reject_links(boundary)
    boundary = boundary.resolve()
    selected = []
    for target in targets:
        reject_links(target)
        resolved = target.resolve()
        if resolved == boundary or not resolved.is_relative_to(boundary):
            raise ValueError("cleanup target escapes compiler boundary")
        if not resolved.exists():
            continue
        regular(resolved, directory=True)
        entries = 0
        for current, directories, names in os.walk(
            resolved,
            followlinks=False,
            onerror=lambda error: (_ for _ in ()).throw(error),
        ):
            regular(Path(current), directory=True)
            entries += len(directories) + len(names)
            if entries > MAX_FILES * 20:
                raise ValueError("cleanup tree exceeds bounds")
            for name in directories:
                regular(Path(current) / name, directory=True)
            for name in names:
                regular(Path(current) / name)
        selected.append(resolved)
    for target in selected:
        reject_links(target)
        shutil.rmtree(target)
