"""Opaque installation context keys; runtime paths never become journal values."""

import hashlib
import os
from pathlib import Path


def project_context(root: Path | None) -> str | None:
    if root is None:
        return None
    return hashlib.sha256(
        os.path.normcase(str(Path(root).resolve())).encode()
    ).hexdigest()
