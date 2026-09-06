"""Explicit local/Git acquisition without checkout filters, scripts or submodules."""

import os
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from git import Repo

from zuat.utils.bundles import capture
from zuat.utils.bundles.paths import reject_links


@contextmanager
def acquire(source, revision="HEAD"):
    """Git blobs are materialized directly, avoiding executable checkout hooks.

    git+file URLs support offline repositories with the same acquisition rules.
    Plain existing paths intentionally mean their current working-tree contents.
    """
    reference = str(source)
    candidate = Path(reference).expanduser()
    if "://" not in reference and candidate.is_dir():
        reject_links(candidate.absolute())
        yield candidate.resolve(), "local", str(candidate.resolve()), None
        return
    remote = reference.removeprefix("git+")
    parsed = urlsplit(remote)
    if (
        parsed.scheme not in {"https", "file"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("unsafe Git source")
    if parsed.scheme == "https" and not parsed.hostname:
        raise ValueError("invalid Git host")
    if parsed.scheme == "file" and (
        not reference.startswith("git+file:") or parsed.netloc
    ):
        raise ValueError("only explicit local Git file sources are supported")
    if (
        not isinstance(revision, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,255}", revision)
        or ".." in revision
    ):
        raise ValueError("unsafe Git revision")
    with TemporaryDirectory(prefix="zuat-source-") as directory:
        workspace = Path(directory)
        checkout = workspace / "source"
        checkout.mkdir()
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        environment.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
        )

        def run(*args):
            subprocess.run(
                [
                    "git",
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "-c",
                    "protocol.ext.allow=never",
                    *args,
                ],
                env=environment,
                capture_output=True,
                check=True,
                timeout=60,
            )

        repo_path = workspace / "objects"
        run("init", "--bare", "--template=", str(repo_path))
        run(
            "-C",
            str(repo_path),
            "fetch",
            "--depth=1",
            "--no-tags",
            "--",
            remote,
            revision,
        )
        with Repo(repo_path) as repo:
            commit = repo.commit("FETCH_HEAD")
            count = total = 0
            seen = set()
            for obj in commit.tree.traverse():
                count += 1
                if count > capture.MAX_FILES * 2:
                    raise ValueError("oversized Git tree")
                relative = Path(obj.path)
                key = relative.as_posix().casefold()
                if (
                    key in seen
                    or "\\" in obj.path
                    or PureWindowsPath(obj.path).is_reserved()
                    or relative.is_absolute()
                    or any(
                        part.casefold() in {"..", ".git"}
                        or ":" in part
                        or part.endswith((".", " "))
                        for part in relative.parts
                    )
                ):
                    raise ValueError("unsafe Git path")
                seen.add(key)
                if obj.type == "tree":
                    continue
                if obj.type != "blob" or obj.mode not in {0o100644, 0o100755}:
                    raise ValueError("links or submodules are unsupported")
                total += obj.size
                if total > capture.MAX_BYTES:
                    raise ValueError("oversized Git source")
                destination = checkout / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(obj.data_stream.read())
            yield checkout, "git", remote, commit.hexsha
