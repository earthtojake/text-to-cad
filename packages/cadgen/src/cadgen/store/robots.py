"""The ROBOT index: a robot description resolved for a player, derived from its bytes.

An input-addressed derivation like ``drawing`` (``STORE.md`` §2): the key is the
resolution's SCHEME, the description's path and content hash and, for an SRDF,
its paired URDF's hash; the entry points at the object holding the payload's
exact bytes and at the primitive meshes the payload draws (``meshes``), so a
sweep keeps them with it. The path is part of the key because the payload
names each link mesh by the absolute path it resolved beside the description.

The payload's shape and the reading of a description live in
``cadgen.robot_payload``; this module only knows how to name an entry and where
to put it. Every failure is best effort: losing the entry costs a re-read, never
an answer.
"""

from __future__ import annotations

import hashlib

from cadgen.store.index import read_entry, write_entry
from cadgen.store.objects import is_object_hash, put_object, read_verified_object
from cadgen.store.paths import StoreUnwritableError

__all__ = [
    "ROBOT_ENTRY_SCHEMA_VERSION",
    "robot_input_key",
    "read",
    "write",
]

INDEX_KIND = "robot"
ROBOT_ENTRY_SCHEMA_VERSION = 1


def robot_input_key(description_path: str, document_hash: str, paired_hash: str | None, *, scheme: str) -> str:
    """The index key for one description's bytes, at one path, under one scheme.

    The scheme is hashed IN, not stored beside the entry: a change in what the
    resolution emits lands on a different key, so old entries are never looked
    up again (the sweeper reclaims them) instead of being validated away one
    read at a time.
    """
    text = str(document_hash or "").strip().lower()
    if not is_object_hash(text):
        raise ValueError(f"not a document content hash: {document_hash!r}")
    paired = str(paired_hash or "").strip().lower()
    if paired and not is_object_hash(paired):
        raise ValueError(f"not a document content hash: {paired_hash!r}")
    salt = str(scheme or "").strip()
    if not salt:
        raise ValueError("a robot index key needs its resolution scheme")
    return hashlib.sha256(f"{salt}\0{description_path}\0{text}\0{paired}".encode("utf-8")).hexdigest()


def read(key: str) -> bytes | None:
    """The cached payload bytes, or ``None`` for a miss.

    ``read_verified_object`` is what makes a hit trustworthy: the bytes must
    still hash to the address the entry names, so a truncated or replaced
    object reads as a miss rather than as a payload.
    """
    entry = read_entry(INDEX_KIND, key)
    if not entry or entry.get("schemaVersion") != ROBOT_ENTRY_SCHEMA_VERSION:
        return None
    digest = entry.get("object")
    if not is_object_hash(digest):
        return None
    try:
        return read_verified_object(str(digest))
    except (OSError, ValueError):
        return None


def write(key: str, data: bytes, *, meshes: list[str]) -> None:
    """Publish the payload and point the entry at it and at its primitive meshes. Best effort."""
    if not data:
        return
    try:
        digest = put_object(bytes(data))
        write_entry(
            INDEX_KIND,
            key,
            {"schemaVersion": ROBOT_ENTRY_SCHEMA_VERSION, "object": digest,
             "meshes": sorted({str(mesh) for mesh in meshes if is_object_hash(mesh)})},
        )
    except (OSError, StoreUnwritableError):
        # An unwritable store is a slow viewer, not a broken one.
        pass
