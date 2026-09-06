"""Non-following path checks shared by private compiler writes."""

import stat
from pathlib import Path


def reject_links(path: Path) -> None:
    """Check every existing ancestor before mkdir/replace can follow a redirect."""
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked or reparse compiler path")
