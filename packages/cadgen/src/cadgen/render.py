from __future__ import annotations

import hashlib
import os
from pathlib import Path


def relative_to_cwd(path: Path) -> str:
    # Display/label + CLI-payload helper (the payload packagePath/stepPath are overwritten by the
    # viewer; the persisted descriptor's model-folder-relative paths come from relative_to_file,
    # not this). Anchored on the live cwd, not a frozen import-time root.
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def relative_to_directory(path: Path, base_dir: Path) -> str:
    return os.path.relpath(
        path.expanduser().resolve(),
        start=base_dir.expanduser().resolve(),
    ).replace(os.sep, "/")


def relative_to_file(path: Path, owner_path: Path) -> str:
    return relative_to_directory(path, owner_path.expanduser().resolve().parent)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
