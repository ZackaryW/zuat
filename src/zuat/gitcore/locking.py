"""Process-lifetime registry exclusion, including abrupt process termination."""

import os
from contextlib import contextmanager
from pathlib import Path

from zuat.gitcore.errors import RegistryLockedError


@contextmanager
def registry_lock(path: Path):
    # Keep the file: unlinking an advisory lock allows another process to lock
    # a different inode while an existing waiter still holds the original one.
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RegistryLockedError(f"registry is locked: {path}") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
