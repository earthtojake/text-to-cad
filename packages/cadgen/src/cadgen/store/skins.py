"""The SKIN index: the bending tubes of a document, bound as a CAD view plays them.

An input-addressed derivation like ``mesh`` and ``drawing`` (``STORE.md`` §2):
the key hashes the payload's scheme, the document's content hash, the digest of
the sidecar animation that bends its tubes, and the stored mesh entries the skins
bind, and the entry points at the object holding the payload's exact bytes. A
changed clip, mesh or binding rule lands on another key, and the sweeper reclaims
the old one.

The payload itself is ``cadgen._internal.tube_skin_payload``'s; this module only
names it and puts it away. Every failure is best effort: losing the entry costs a
re-derivation, never an answer.
"""

from __future__ import annotations

import hashlib

from cadgen.store.index import read_entry, write_entry
from cadgen.store.objects import is_object_hash, put_object, read_verified_object
from cadgen.store.paths import StoreUnwritableError

__all__ = ["SKIN_ENTRY_SCHEMA_VERSION", "read", "skin_input_key", "write"]

INDEX_KIND = "skin"
SKIN_ENTRY_SCHEMA_VERSION = 1


def skin_input_key(*, scheme: str, document_hash: str, animation_digest: str, mesh_keys: list[str]) -> str:
    """The index key for one document's tube skins under one scheme."""
    document = str(document_hash or "").strip().lower()
    if not is_object_hash(document):
        raise ValueError(f"not a document content hash: {document_hash!r}")
    if not str(scheme or "").strip():
        raise ValueError("a skin index key needs its payload scheme")
    parts = [str(scheme).strip(), document, str(animation_digest), *sorted(str(key) for key in mesh_keys)]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def read(key: str) -> bytes | None:
    """The cached payload bytes, or ``None`` for a miss (a missing, stale or damaged
    entry or object alike)."""
    entry = read_entry(INDEX_KIND, key)
    if not entry or entry.get("schemaVersion") != SKIN_ENTRY_SCHEMA_VERSION:
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
        write_entry(INDEX_KIND, key, {"schemaVersion": SKIN_ENTRY_SCHEMA_VERSION, "object": digest})
    except (OSError, StoreUnwritableError):
        pass
