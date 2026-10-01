"""Content-addressed objects: a component's bytes or a tree's JSON.

An object is named by the sha256 of its bytes and sharded ``ab/cdef…`` like
git. Writing is idempotent and atomic (temp + rename), so a reader can never
observe a partial object. Explicit recovery can replace bytes that no longer
match their address; a valid existing object is never rewritten.

A write that finds its bytes already present is a REUSE, and a reuse claims
the object: its mtime becomes now (:func:`claim_object`). The sweeper keeps
anything claimed within its grace window and deletes only by rename, then
recheck (:func:`delete_unclaimed`), so an object a publish has claimed is
never deleted under it (STORE.md §8).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Iterator

from cadgen._internal.atomic_replace import (
    RETRY_DELAYS_SECONDS,
    WINDOWS_SHARING_VIOLATION,
    move_atomic,
    replace_atomic,
    temp_suffix,
)
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


def _claim(path: Path) -> bool:
    """Set ``path``'s mtime to now. False only when the file is gone.

    Windows refuses the timestamp write while another process holds the file
    open (a sharing violation, WinError 32), so that one wait gets the same
    bounded ladder the renames use. Any other refusal (a read-only store,
    another owner's file) leaves the object as it is: claiming is never a new
    way for a write to fail where finding the bytes used to succeed.
    """
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            os.utime(path)
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            if getattr(error, "winerror", None) == WINDOWS_SHARING_VIOLATION and delay is not None:
                time.sleep(delay)
                continue
            return path.is_file()
    return path.is_file()


def claim_object(digest: str) -> bool:
    """Claim an existing object for whatever is about to reference it.

    True: the object is there and its mtime is now (or the store refused the
    timestamp, and it is still there). False: it is gone -- a sweep took it
    first -- and the caller writes its bytes again, or fails when it holds none.
    """
    try:
        return _claim(object_path(digest))
    except ValueError:
        return False


SWEPT = ".swept"


def swept_address(path: Path) -> Path | None:
    """The object path a sweep's held file (:func:`delete_unclaimed`) came from;
    None for any other file."""
    name = path.name
    if not name.startswith(".") or SWEPT + "." not in name:
        return None
    return path.with_name(name[1:name.index(SWEPT + ".")])


def delete_unclaimed(path: Path, cutoff: float) -> int:
    """Delete one object nothing reaches unless it was claimed after ``cutoff``.

    Returns the bytes freed, 0 when the object stays. The check and the delete
    cannot be one step, so the object is first renamed out of reach and its
    mtime read again from the renamed file: a writer that claimed it before
    the rename shows in that mtime, and the object goes back; a writer that
    comes after the rename finds it gone and writes it again. Either way no
    claim is lost. A rename refused because the file is in use (Windows) just
    leaves the object for a later sweep. A pass that dies holding an object
    leaves it under :func:`swept_address`'s name, and the next one puts a
    claimed one back.
    """
    try:
        if path.stat().st_mtime > cutoff:
            return 0
    except OSError:
        return 0
    held = path.with_name(f".{path.name}{SWEPT}{temp_suffix()}")
    try:
        move_atomic(path, held)
    except OSError:
        return 0
    try:
        stat = held.stat()
    except OSError:
        return 0
    if stat.st_mtime > cutoff:
        try:
            move_atomic(held, path)
        except OSError:
            # A writer has published the same bytes at the address since.
            with contextlib.suppress(OSError):
                held.unlink()
        return 0
    try:
        held.unlink()
    except OSError:
        return 0
    return stat.st_size


def put_object(data: bytes, *, repair: bool = False) -> str:
    """Store ``data``; return its hash. Idempotent and atomic.

    Bytes already present are claimed (:func:`claim_object`) instead of
    rewritten; bytes a sweep removed between the check and the claim are
    written again.
    """
    digest = object_hash(data)
    target = object_path(digest)
    if target.is_file() and (not repair or _object_matches(target, digest)) and _claim(target):
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
    if target.is_file() and (not repair or _object_matches(target, hexdigest)) and _claim(target):
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
