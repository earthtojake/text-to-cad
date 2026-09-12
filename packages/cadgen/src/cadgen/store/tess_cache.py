"""Shared storage for opaque component-tessellation cache bytes.

The browser codec owns the entry payload and TESB batch format.  Python only
maps a validated cache key to the store's ``mesh`` index and frames already
loaded entry bytes.  HTTP path decoding and response statuses belong to the
hosts that call this module.
"""

from __future__ import annotations

import os
import re
import struct
from collections.abc import Iterable

from cadgen.store.index import read_entry, write_entry
from cadgen.store.objects import put_object, read_object
from cadgen.store.paths import index_dir

__all__ = [
    "TESS_CACHE_BATCH_MAGIC",
    "TESS_CACHE_BATCH_MAX_NAMES",
    "TESS_CACHE_BATCH_VERSION",
    "encode_tessellation_cache_batch",
    "is_tessellation_cache_key",
    "read_tessellation_cache",
    "tessellation_cache_dir",
    "tessellation_cache_enabled",
    "write_tessellation_cache",
]

TESS_CACHE_BATCH_MAGIC = 0x42534554  # "TESB" little-endian
TESS_CACHE_BATCH_VERSION = 1
TESS_CACHE_BATCH_MAX_NAMES = 4096

_TESS_CACHE_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*")


def tessellation_cache_enabled() -> bool:
    """Whether cache reads and writes are enabled; evaluated for every call."""
    return os.environ.get("CADGEN_MESH_CACHE") != "0"


def tessellation_cache_dir() -> str:
    """The mesh index directory; entries point at content-addressed objects."""
    return str(index_dir("mesh"))


def is_tessellation_cache_key(value: object) -> bool:
    """Return whether ``value`` is safe as one mesh-index filename.

    Store callers pass keys without the transport's ``.tess`` suffix.  The
    pattern is the containment boundary because this index is outside every
    document root.
    """
    return (
        isinstance(value, str)
        and _TESS_CACHE_KEY_PATTERN.fullmatch(value) is not None
        and ".." not in value
    )


def _validated_key(key: str) -> str:
    if not is_tessellation_cache_key(key):
        raise ValueError(f"invalid tessellation cache key: {key!r}")
    return key


def read_tessellation_cache(key: str) -> bytes | None:
    """Read opaque bytes for a validated key; corruption and I/O errors miss."""
    key = _validated_key(key)
    if not tessellation_cache_enabled():
        return None
    try:
        entry = read_entry("mesh", key)
        digest = str((entry or {}).get("object") or "")
        data = read_object(digest) if digest else None
        return data if data else None
    except (OSError, ValueError):
        return None


def write_tessellation_cache(key: str, data: bytes) -> None:
    """Best-effort write of opaque bytes for a validated key.

    Empty writes and disabled-cache writes are accepted and dropped.  A full
    disk or permissions failure cannot fail the render that produced the bytes.
    """
    key = _validated_key(key)
    if not data or not tessellation_cache_enabled():
        return
    try:
        write_entry("mesh", key, {"object": put_object(bytes(data))})
    except OSError:
        pass


def encode_tessellation_cache_batch(entries: Iterable[bytes | None]) -> bytes:
    """Frame opaque entries as the browser codec's TESB v1 container."""
    materialized = list(entries)
    out = bytearray(
        struct.pack(
            "<III",
            TESS_CACHE_BATCH_MAGIC,
            TESS_CACHE_BATCH_VERSION,
            len(materialized),
        )
    )
    for entry in materialized:
        length = len(entry) if entry else 0
        out += struct.pack("<I", length)
        if length:
            out += entry
            out += b"\0" * (-length % 4)
    return bytes(out)
