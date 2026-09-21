"""Content-addressed objects: a component's bytes or a tree's JSON.

An object is named by the sha256 of its bytes and sharded ``ab/cdef…`` like
git. Writing is idempotent and atomic (temp + rename), so a reader can never
observe a partial object. Explicit recovery can replace bytes that no longer
match their address; a valid existing object is left alone.
"""

from __future__ import annotations

import contextlib
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


def _object_matches(path: Path, digest: str) -> bool:
    """Check the existing bytes, without removing a failed or racing object."""
    observed = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                observed.update(chunk)
    except OSError:
        return False
    return observed.hexdigest() == digest


def _replace_object(tmp: Path, target: Path, digest: str, *, repair: bool) -> None:
    try:
        replace_atomic(tmp, target)
    except OSError:
        # Two repair writers may both observe damage before either publishes. On
        # Windows the loser can be denied replacing the winner's newly valid file.
        # Exact canonical bytes make that idempotent success; every other denial
        # remains a real error.
        if not repair or not _object_matches(target, digest):
            raise
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def put_object(data: bytes, *, repair: bool = False) -> str:
    """Store ``data``; return its hash. Idempotent and atomic."""
    digest = object_hash(data)
    target = object_path(digest)
    if target.is_file() and (not repair or _object_matches(target, digest)):
        return digest
    _mkdir(target.parent)
    tmp = target.with_name(f".{target.name}{temp_suffix()}")
    with open(tmp, "wb") as handle:
        handle.write(data)
    _replace_object(tmp, target, digest, repair=repair)
    return digest


def put_object_from_file(path: Path, *, repair: bool = False) -> str:
    """Store a file's bytes as an object (streamed hash, one copy)."""
    path = Path(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    hexdigest = digest.hexdigest()
    target = object_path(hexdigest)
    if target.is_file() and (not repair or _object_matches(target, hexdigest)):
        return hexdigest
    _mkdir(target.parent)
    tmp = target.with_name(f".{target.name}{temp_suffix()}")
    shutil.copyfile(path, tmp)
    if repair and not _object_matches(tmp, hexdigest):
        tmp.unlink(missing_ok=True)
        raise ValueError(f"object source changed while repairing {hexdigest}")
    _replace_object(tmp, target, hexdigest, repair=repair)
    return hexdigest


def read_object(digest: str) -> bytes:
    return object_path(digest).read_bytes()


def read_verified_object(digest: str) -> bytes:
    """Return one byte snapshot only when it matches the requested address."""
    data = read_object(digest)
    if object_hash(data) != str(digest).strip().lower():
        raise ValueError(f"object bytes do not match {digest}")
    return data


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
