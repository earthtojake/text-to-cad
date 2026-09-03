from __future__ import annotations

import hashlib
from pathlib import Path

from cadgen._internal.atomic_replace import open_with_ladder


def step_file_hash(step_path: Path) -> str:
    """sha256 of a STEP file, streamed.

    Opened through the sharing-violation ladder: every export hashes the file it
    has just written and closed, which is the moment a Windows scanner is most
    likely to be holding it.
    """
    digest = hashlib.sha256()
    with open_with_ladder(step_path.expanduser().resolve(), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
