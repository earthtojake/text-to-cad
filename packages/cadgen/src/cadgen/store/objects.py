"""Content-addressed objects: a component's bytes or a tree's JSON.

An object is named by the sha256 of its bytes and sharded ``ab/cdef…`` like
git. Writing is idempotent and atomic (temp + rename), so a reader can never
observe a partial object. Explicit recovery can replace bytes that no longer
match their address; a valid existing object is never rewritten.

A write that finds its bytes already present is a REUSE, and a reuse claims
the object: its mtime becomes now, less two ticks of its filesystem's clock
(:func:`claim_object`). The sweeper keeps anything claimed within its grace
window and deletes only by rename, then recheck (:func:`delete_unclaimed`), so
an object a publish has claimed is never deleted under it (STORE.md §8).

This process also remembers the file identity -- device, inode, size, mtime,
ctime -- under which it last hashed each object's bytes to their address
(:func:`verified_stamp`), once that identity is settled: read far enough past
the write it observed that a later write must stamp a different mtime
(:func:`_stamp_is_settled`, STORE.md §10). A claim is the one write this
process makes to an object it has verified, so a claim carries the identity
forward instead of invalidating it (STORE.md §8).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import threading
import time
from collections import OrderedDict
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


@contextlib.contextmanager
def _writing(target: Path) -> Iterator[None]:
    """A write the store's folder refuses is :class:`StoreUnwritableError`, wherever it is
    refused: a read-only store whose shard folder already exists refuses the temp file,
    not the folder."""
    try:
        yield
    except PermissionError as exc:
        from cadgen.store.paths import unwritable

        raise unwritable(exc, target) from None


def _mkdir(folder: Path) -> None:
    with _writing(folder):
        folder.mkdir(parents=True, exist_ok=True)


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


# --- file identity ------------------------------------------------------------

_STAMP_MTIME_NS = 4
# A clock that ticks every T ns can only stamp multiples of T, so an observed
# stamp's trailing zeros bound the resolution that produced it from below.
# Coarsest first: a stamp is attributed to the coarsest clock that could have
# produced it, because over-estimating the tick costs one cache miss while
# under-estimating certifies a read a later write can still reproduce. FAT's
# 2 s write time divides by 1 s, so it needs an entry of its own -- read as a
# 1 s clock it would admit a rewrite in the back half of its own tick.
_TIMESTAMP_TICKS_NS = (2_000_000_000, 1_000_000_000)
# Nanosecond digits do not prove a nanosecond clock. Linux before 6.13 stamps a
# write with the time its timer interrupt last recorded (every 10 ms at 100 Hz)
# and Windows with a ~15.6 ms one, each keeping all the digits of that time, so
# no stamp settles before the slower of them has ticked twice.
_TIMESTAMP_FLOOR_NS = 2 * 15_625_000


def _stamp(key: str, path: Path) -> tuple:
    """A file's fingerprint: ``key``, then its device, inode, size, mtime (at
    ``_STAMP_MTIME_NS``) and ctime. Raises OSError when there is no file."""
    stat = path.stat()
    return (key, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _timestamp_resolution_ns(mtime_ns: int) -> int:
    """How coarsely the filesystem that produced ``mtime_ns`` may stamp a write."""
    for tick in _TIMESTAMP_TICKS_NS:
        if mtime_ns % tick == 0:
            return tick
    return _TIMESTAMP_FLOOR_NS


def _stamp_is_settled(stamp: tuple) -> bool:
    """True when a write made from here on cannot reproduce ``stamp``.

    The read happened at least one timestamp tick after the write it observed,
    so any later write lands in a tick the fingerprint does not already hold.
    Every clock leaves a short window -- a few interrupt ticks, or a whole
    coarse tick, or longer when the clock ran backwards -- in which the bytes
    may still change silently, and nothing read in it is remembered.
    """
    mtime_ns = stamp[_STAMP_MTIME_NS]
    return time.time_ns() - mtime_ns >= _timestamp_resolution_ns(mtime_ns)


# The settled identity under which this process last verified each object's
# bytes against its address, by path. A reader that finds an object still at
# this identity holds the bytes it hashed (STORE.md §10); the tree captures
# (``cadgen.store.trees``) read through it and fill it. Bounded, oldest first:
# a forgotten identity costs one read.
_VERIFIED_CAPACITY = 1 << 16
_VERIFIED: OrderedDict[str, tuple] = OrderedDict()
_VERIFIED_LOCK = threading.Lock()


def verified_stamp(path: str) -> tuple | None:
    """The settled fingerprint (:func:`_stamp`) this process verified ``path``
    under, or None."""
    return _VERIFIED.get(path)


def remember_verified(stamp: tuple) -> None:
    """Keep ``stamp`` -- taken on both sides of a read whose bytes hashed to the
    object's address -- as the identity ``path`` is verified under. A stamp that
    is not settled yet is not kept: a write landing in its tick would be invisible."""
    if not _stamp_is_settled(stamp):
        return
    with _VERIFIED_LOCK:
        _VERIFIED[stamp[0]] = stamp
        _VERIFIED.move_to_end(stamp[0])
        while len(_VERIFIED) > _VERIFIED_CAPACITY:
            _VERIFIED.popitem(last=False)


def forget_verified(path: str) -> None:
    with _VERIFIED_LOCK:
        _VERIFIED.pop(path, None)


def _reset_verified() -> None:
    with _VERIFIED_LOCK:
        _VERIFIED.clear()


def _claim(path: Path) -> bool:
    """Stamp ``path`` as claimed now. False only when the file is gone.

    The mtime written is two ticks of the file's clock in the past (the clock
    its previous stamp shows, :func:`_timestamp_resolution_ns`): still within
    any grace window a sweep may use, and a stamp set in a tick that has
    already ended is settled as it is set, so the identity this process
    verified the object under (:func:`verified_stamp`) is carried over the
    claim instead of lost. It is carried only when the stamp before the claim
    is the verified one -- nothing wrote the file since the verified read -- and
    the stamp after it is the claim's own, on the same device, inode and size;
    otherwise the identity is forgotten and the next reader hashes the bytes.

    Windows refuses the timestamp write while another process holds the file
    open (a sharing violation, WinError 32), so that one wait gets the same
    bounded ladder the renames use. POSIX lets only a file's owner set an
    explicit time, but anyone who may write the file set it to now: in a store
    several users share, an object another user owns is claimed with a stamp
    of now, which is not settled as it is set, so its identity is forgotten.
    Any other refusal (a read-only store, a file this user may not write)
    leaves the object as it is: claiming is never a new way for a write to fail
    where finding the bytes used to succeed.
    """
    key = str(path)
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            before = os.stat(path)
            resolution = _timestamp_resolution_ns(before.st_mtime_ns)
            now_ns = time.time_ns()
            # A whole microsecond: every filesystem that keeps fractions of a
            # second stores one exactly (NTFS counts in 100 ns).
            mtime_ns = (now_ns - 2 * resolution) // 1000 * 1000
            os.utime(path, ns=(now_ns, mtime_ns))
            after = os.stat(path)
        except FileNotFoundError:
            forget_verified(key)
            return False
        except OSError as error:
            if getattr(error, "winerror", None) == WINDOWS_SHARING_VIOLATION and delay is not None:
                time.sleep(delay)
                continue
            # The stamp is as it was, or unknown: keep nothing the next reader
            # could not confirm.
            forget_verified(key)
            if isinstance(error, PermissionError) and os.name != "nt":
                # Another user's object: setting it to now needs only write access.
                try:
                    os.utime(path)
                    return True
                except OSError:
                    pass
            return path.is_file()
        _carry_verified(key, before, after, mtime_ns, resolution)
        return True
    forget_verified(key)
    return path.is_file()


def _carry_verified(key: str, before: os.stat_result, after: os.stat_result, mtime_ns: int, resolution: int) -> None:
    """Carry ``key``'s verified identity over the claim that just stamped it,
    or forget it (see :func:`_claim`)."""
    with _VERIFIED_LOCK:
        known = _VERIFIED.get(key)
        if known is None:
            return
        same_before = known == (key, before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        # A filesystem that stores a coarser time than it was given truncates the
        # claim's stamp to its own tick.
        own_stamp = after.st_mtime_ns in (mtime_ns, mtime_ns - mtime_ns % resolution)
        same_file = (after.st_dev, after.st_ino, after.st_size) == (before.st_dev, before.st_ino, before.st_size)
        carried = (key, after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if same_before and own_stamp and same_file and _stamp_is_settled(carried):
            _VERIFIED[key] = carried
            _VERIFIED.move_to_end(key)
        else:
            _VERIFIED.pop(key, None)


def claim_object(digest: str) -> bool:
    """Claim an existing object for whatever is about to reference it.

    True: the object is there and stamped as claimed now (:func:`_claim`), or
    the store refused the timestamp and it is still there. False: it is gone --
    a sweep took it first -- and the caller writes its bytes again, or fails
    when it holds none.
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
    with _writing(target):
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
    with _writing(target):  # the source was just read whole: a refusal here is the store's
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
