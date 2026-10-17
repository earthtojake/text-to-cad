"""Transport-neutral access to the store's parts: their records, display meshes and
selector tables (``cadgen.store.parts``).

This module owns the bounded probe/body protocol and TESB framing used by both the
snapshot host and the Viewer, under one route family:

- ``POST <prefix>probe`` ``{"parts": [key, ...]}`` -> ``{"entries": {key: record}}``,
  the stored parts' records (a missing part is absent);
- ``POST <prefix>batch`` ``{"entries": [{"part", "object", "maxBytes"}, ...]}`` -> the
  parts' display meshes in one TESB container, a missing or changed one empty: the
  big-assembly path;
- ``GET <prefix><key>.glb`` and ``GET <prefix><key>.selectors.json``, each with
  ``?object=&maxBytes=``: one part's display mesh, one part's selector table.

Clients only read: cadgen writes every part. URI decoding and HTTP status codes stay
in the hosts, so store and snapshot code never import ``cadgen.viewer``.
"""

from __future__ import annotations

import json
import re
import struct
from collections.abc import Iterable

__all__ = [
    "TESS_CACHE_BATCH_MAGIC", "TESS_CACHE_BATCH_MAX_BYTES",
    "TESS_CACHE_BATCH_MAX_NAMES", "TESS_CACHE_BATCH_VERSION",
    "TESS_CACHE_METADATA_MAX_BYTES", "encode_tessellation_cache_batch",
    "parse_tess_cache_admission", "read_part_object", "read_tess_cache_batch",
    "read_tess_cache_probe", "tess_cache_name",
]

TESS_CACHE_BATCH_MAGIC = 0x42534554  # "TESB" little-endian
TESS_CACHE_BATCH_VERSION = 1
TESS_CACHE_BATCH_MAX_NAMES = 256
TESS_CACHE_BATCH_MAX_BYTES = 32 * 1024 * 1024
TESS_CACHE_METADATA_MAX_BYTES = 256 * 1024
# A route's file name: a part key and the object it names, by suffix.
_ROLES = {".glb": "glb", ".selectors.json": "selectors"}


def tess_cache_name(name: object) -> tuple[str, str] | None:
    """``(part key, role)`` of a route's file name (``<key>.glb``, ``<key>.selectors.json``);
    None for anything else."""
    from cadgen.store.parts import valid_key

    text = str(name or "")
    for suffix, role in _ROLES.items():
        if text.endswith(suffix) and valid_key(text[:-len(suffix)]):
            return text[:-len(suffix)], role
    return None


def parse_tess_cache_admission(digest, raw_limit) -> tuple[str, int]:
    """Validate an exact object digest and the caller's admitted byte bound."""
    from cadgen.store.meshes import MAX_SAFE_INTEGER
    if (type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or type(raw_limit) is not str or re.fullmatch(r"[0-9]{1,16}", raw_limit) is None):
        raise ValueError("cache read requires an exact object and maxBytes")
    limit = int(raw_limit)
    if not 0 < limit <= MAX_SAFE_INTEGER:
        raise ValueError("maxBytes must be a positive safe integer")
    return digest, limit


def read_part_object(name: object, *, expected_object: str, max_bytes: int) -> bytes | None:
    """The object a route's file name names, bound to the caller's admitted facts; None for
    a name that names none, or an object the store does not hold as named."""
    from cadgen.store.parts import read

    named = tess_cache_name(name)
    if named is None:
        return None
    try:
        return read(named[0], named[1], expected_object=expected_object, max_bytes=max_bytes)
    except (OSError, ValueError):
        return None


def encode_tessellation_cache_batch(entries: Iterable[bytes | None]) -> bytes:
    """Frame opaque entries (GLB bodies) as the browser codec's aligned TESB v1 container."""
    materialized = list(entries)
    out = bytearray(struct.pack(
        "<III", TESS_CACHE_BATCH_MAGIC, TESS_CACHE_BATCH_VERSION, len(materialized),
    ))
    for entry in materialized:
        length = len(entry) if entry else 0
        out += struct.pack("<I", length)
        if length:
            out += entry
            out += b"\0" * (-length % 4)
    return bytes(out)


def _request_items(body: bytes | None, field: str) -> list | None:
    if len(body or b"") > TESS_CACHE_METADATA_MAX_BYTES:
        return None
    try:
        parsed = json.loads(bytes(body or b"").decode("utf-8", errors="replace"))
    except (ValueError, RecursionError):
        return None
    items = parsed.get(field) if type(parsed) is dict and set(parsed) == {field} else None
    return items if type(items) is list and len(items) <= TESS_CACHE_BATCH_MAX_NAMES else None


def read_tess_cache_probe(body: bytes | None) -> dict | None:
    """Return the stored parts' records without loading a body."""
    from cadgen.store.parts import probe
    keys = _request_items(body, "parts")
    if keys is None:
        return None
    entries = {}
    for key in keys:
        record = probe(key) if type(key) is str else None
        if record is not None:
            entries[key] = record
    return {"entries": entries}


def read_tess_cache_batch(body: bytes | None) -> bytes | None:
    """Read admitted exact display meshes into a response capped at 32 MiB."""
    from cadgen.store.parts import read, valid_key

    requests = _request_items(body, "entries")
    if requests is None:
        return None
    entries: list[bytes | None] = []
    remaining = TESS_CACHE_BATCH_MAX_BYTES - 12 - 4 * len(requests)
    for request in requests:
        data = None
        if type(request) is dict and set(request) == {"part", "object", "maxBytes"}:
            key, digest, limit = request["part"], request["object"], request["maxBytes"]
            if (valid_key(key) and type(digest) is str
                    and type(limit) is int and limit > 0 and remaining >= 0):
                try:
                    data = read(key, "glb", expected_object=digest, max_bytes=min(limit, remaining))
                except (OSError, ValueError):
                    data = None
                if data and len(data) + (-len(data) % 4) > remaining:
                    data = None
        entries.append(data)
        if data:
            remaining -= len(data) + (-len(data) % 4)
    return encode_tessellation_cache_batch(entries)
