from __future__ import annotations

import hashlib
from pathlib import Path


def step_file_hash(step_path: Path) -> str:
    digest = hashlib.sha256()
    with step_path.expanduser().resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
