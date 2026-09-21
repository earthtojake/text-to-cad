"""The DRAWING index: a 2D render payload derived from a document's bytes.

An input-addressed derivation like ``op``, ``mesh`` and ``surface``
(``STORE.md`` §2): the key is the extraction's SCHEME plus the document's
content hash, and the entry points at the object holding the payload's exact
bytes. Nothing here reads a record, a path or a model — the same DXF bytes
anywhere on disk hit the same entry.

The payload's shape and the drawing of it live in ``cadgen.drawing_payload``;
this module only knows how to name it and where to put it. Every failure is
best effort: losing the entry costs a re-render, never an answer.
"""

from __future__ import annotations

import hashlib

from cadgen.store.index import read_entry, write_entry
from cadgen.store.objects import is_object_hash, put_object, read_verified_object
from cadgen.store.paths import StoreUnwritableError

__all__ = [
    "DRAWING_ENTRY_SCHEMA_VERSION",
    "drawing_input_key",
    "read",
    "write",
]

INDEX_KIND = "drawing"
DRAWING_ENTRY_SCHEMA_VERSION = 1


def drawing_input_key(document_hash: str, *, scheme: str) -> str:
    """The index key for one document's bytes under one extraction scheme.

    The scheme is hashed IN, not stored beside the entry: an upgrade that
    changes what the extraction emits lands on a different key, so old entries
    are simply never looked up again (and the sweeper reclaims them) instead of
    being validated away one read at a time.
    """
    text = str(document_hash or "").strip().lower()
    if not is_object_hash(text):
        raise ValueError(f"not a document content hash: {document_hash!r}")
    salt = str(scheme or "").strip()
    if not salt:
        raise ValueError("a drawing index key needs its extraction scheme")
    return hashlib.sha256(f"{salt}\0{text}".encode("utf-8")).hexdigest()


def read(key: str) -> bytes | None:
    """The cached payload bytes, or ``None`` for a miss.

    ``read_verified_object`` is what makes a hit trustworthy: the bytes must
    still hash to the address the entry names, so a truncated or replaced
    object reads as a miss rather than as a payload.
    """
    entry = read_entry(INDEX_KIND, key)
    if not entry or entry.get("schemaVersion") != DRAWING_ENTRY_SCHEMA_VERSION:
        return None
    digest = entry.get("object")
    if not is_object_hash(digest):
        return None
    try:
        return read_verified_object(str(digest))
    except (OSError, ValueError):
        return None


def write(key: str, data: bytes) -> None:
    """Publish the payload and point the entry at it. Best effort."""
    if not data:
        return
    try:
        digest = put_object(bytes(data))
        write_entry(
            INDEX_KIND,
            key,
            {"schemaVersion": DRAWING_ENTRY_SCHEMA_VERSION, "object": digest},
        )
    except (OSError, StoreUnwritableError):
        # An unwritable store is a slow viewer, not a broken one.
        pass
