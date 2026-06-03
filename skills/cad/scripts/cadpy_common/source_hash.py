from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PythonSourceHash:
    digest: str


def python_source_hash(script_path: Path) -> PythonSourceHash:
    """Hash the generator script content."""
    return PythonSourceHash(digest=_sha256_file(script_path.expanduser().resolve()))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
