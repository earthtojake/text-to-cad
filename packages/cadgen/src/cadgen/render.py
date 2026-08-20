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
    """A path recorded relative to ``base_dir``, always with forward slashes.

    This is the helper every PERSISTED path goes through, which is what makes a ``__cadgen__``
    package movable: a descriptor records where a file sits relative to the model folder, not
    where it sat on the machine that wrote it. Posix separators for the same reason -- a
    package written on Windows is read on macOS.

    On Windows ``relpath`` raises for two different drives, where no relative path exists.
    Recording the absolute path is then the only option, and it is honest: a reference across
    volumes does not travel with the folder either. The alternative was a ValueError escaping
    as a failed build."""
    resolved = path.expanduser().resolve()
    try:
        return os.path.relpath(resolved, start=base_dir.expanduser().resolve()).replace(os.sep, "/")
    except ValueError:
        return resolved.as_posix()


def relative_to_file(path: Path, owner_path: Path) -> str:
    return relative_to_directory(path, owner_path.expanduser().resolve().parent)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
