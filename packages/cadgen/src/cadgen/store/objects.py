"""Content-addressed objects: a component's bytes or a tree's JSON.

An object is named by the sha256 of its bytes and sharded ``ab/cdef…`` like
git. Writing is idempotent (an existing object is never rewritten) and atomic
(temp + rename), so a reader can never observe a partial object.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Iterator

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen.store.paths import objects_dir


def object_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_object_hash(value: object) -> bool:
    digest = str(value or "").strip().lower()
    return len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


def object_path(digest: str) -> Path:
    digest = str(digest).strip().lower()
    if not is_object_hash(digest):
        raise ValueError(f"not an object hash: {digest!r}")
    return objects_dir() / digest[:2] / digest[2:]


def has_object(digest: str) -> bool:
    try:
        return object_path(digest).is_file()
    except ValueError:
        return False


def _mkdir(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        from cadgen.store.paths import unwritable

        raise unwritable(exc, folder) from None


def put_object(data: bytes) -> str:
    """Store ``data``; return its hash. Idempotent and atomic."""
    digest = object_hash(data)
    target = object_path(digest)
    if target.is_file():
        return digest
    _mkdir(target.parent)
    tmp = target.with_name(f".{target.name}{temp_suffix()}")
    with open(tmp, "wb") as handle:
        handle.write(data)
    replace_atomic(tmp, target)
    return digest


def put_object_from_file(path: Path) -> str:
    """Store a file's bytes as an object (streamed hash, one copy)."""
    path = Path(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    hexdigest = digest.hexdigest()
    target = object_path(hexdigest)
    if target.is_file():
        return hexdigest
    _mkdir(target.parent)
    tmp = target.with_name(f".{target.name}{temp_suffix()}")
    shutil.copyfile(path, tmp)
    replace_atomic(tmp, target)
    return hexdigest


def read_object(digest: str) -> bytes:
    return object_path(digest).read_bytes()


def iter_objects() -> Iterator[tuple[str, Path]]:
    root = objects_dir()
    if not root.is_dir():
        return
    for shard in sorted(root.iterdir()):
        if not shard.is_dir() or len(shard.name) != 2:
            continue
        for entry in sorted(shard.iterdir()):
            if entry.is_file() and not entry.name.startswith("."):
                yield shard.name + entry.name, entry
