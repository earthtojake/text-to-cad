"""The viewer server's side of the shared component-tessellation cache.

The same mesh index (``index/mesh`` -> objects, ``STORE.md``) the snapshot host
serves, exposed to the client on ``/__tess_cache/`` — GET one entry, POST one
write-back, POST ``/batch`` for the TESB container (one round trip for a whole
assembly's hit set).

The shared v4 identity is validated by ``cadgen.store.meshes``. Metadata probes
precede admitted, exact-object body reads; batching never downloads an entire
assembly without a byte bound. The TESB framing is shared with cadgen-js.

The entry I/O here is the route's framing over ``cadgen.store``: a key names an
index entry, the entry names the object holding the bytes.

THE NAME PATTERN IS THE WHOLE DEFENCE. This cache lives OUTSIDE every served
root — containment cannot help here, because there is no root to be inside of.
So a name is validated before anything touches disk, and a malformed
percent-escape is a refusal rather than a lookup under a mangled name.
"""

from __future__ import annotations

import json
import os
import re
import struct

from .encoding import UriError, strict_decode_uri_component

__all__ = [
    "TESS_CACHE_BATCH_MAGIC",
    "TESS_CACHE_BATCH_MAX_NAMES",
    "TESS_CACHE_BATCH_PATH",
    "TESS_CACHE_BATCH_VERSION",
    "TESS_CACHE_BATCH_MAX_BYTES",
    "TESS_CACHE_PROBE_PATH",
    "TESS_CACHE_ROUTE_PREFIX",
    "read_tess_cache_batch",
    "read_tess_cache_entry",
    "read_tess_cache_probe",
    "tess_cache_key_from_route_path",
    "tessellation_cache_dir",
    "write_tess_cache_entry",
]

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"
TESS_CACHE_PROBE_PATH = "/__tess_cache/probe"

# Mirror of the snapshot host's pattern. ``fullmatch`` rather than a ``$``
# anchor: Python's ``$`` also matches before a trailing newline, so
# ``"a.tess\n"`` would pass where JavaScript's ``$`` refuses it.
_TESS_CACHE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*\.tess")

TESS_CACHE_BATCH_MAGIC = 0x42534554  # "TESB" little-endian
TESS_CACHE_BATCH_VERSION = 1
TESS_CACHE_BATCH_MAX_NAMES = 256
TESS_CACHE_BATCH_MAX_BYTES = 32 * 1024 * 1024
TESS_CACHE_METADATA_MAX_BYTES = 256 * 1024

_TESS_SUFFIX = ".tess"


def parse_tess_cache_admission(digest, raw_limit) -> tuple[str, int]:
    """HTTP reads require the probed object and an explicit admitted size."""
    from cadgen.store.meshes import MAX_SAFE_INTEGER
    if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest) or type(raw_limit) is not str or not re.fullmatch(r"[0-9]{1,16}", raw_limit):
        raise ValueError("cache read requires an exact object and maxBytes")
    limit = int(raw_limit)
    if not 0 < limit <= MAX_SAFE_INTEGER:
        raise ValueError("maxBytes must be a positive safe integer")
    return digest, limit


def _tessellation_cache_enabled() -> bool:
    """Read per call: the suites flip this after the app is constructed."""
    return os.environ.get("CADGEN_MESH_CACHE") != "0"


def tessellation_cache_dir() -> str:
    """The mesh index (``index/mesh``); entries point at objects."""
    from cadgen.store.paths import index_dir

    return str(index_dir("mesh"))


def _read_cached_tessellation_bytes(key: str, *, expected_object=None, max_bytes=None) -> bytes | None:
    if not _tessellation_cache_enabled():
        return None
    try:
        from cadgen.store.meshes import read

        return read(key, expected_object=expected_object, max_bytes=max_bytes)
    except (OSError, ValueError):
        return None


def _write_cached_tessellation_bytes(key: str, data: bytes) -> None:
    """Best-effort: a full disk or a permissions problem must not fail callers.
    The bytes become an object; the entry maps the key to it."""
    if not _tessellation_cache_enabled():
        return
    try:
        from cadgen.store.meshes import write

        write(key, data)
    except OSError:
        pass


def tess_cache_key_from_route_path(pathname) -> str | None:
    """The cache key for a route path, or ``None`` to refuse it."""
    try:
        name = strict_decode_uri_component(str(pathname or "")[len(TESS_CACHE_ROUTE_PREFIX) :])
    except UriError:
        # Malformed percent-encoding is a refusal, not a crash — and never a
        # lookup under the raw, undecoded text.
        return None
    if not _TESS_CACHE_NAME_PATTERN.fullmatch(name) or ".." in name:
        return None
    return name[: -len(_TESS_SUFFIX)]


def read_tess_cache_entry(pathname, *, expected_object=None, max_bytes=None) -> tuple[int, bytes | None]:
    """``(status, body)``: 403 for a refused name, 404 for a miss, 200 for a hit."""
    key = tess_cache_key_from_route_path(pathname)
    if key is None:
        return 403, None
    data = _read_cached_tessellation_bytes(key, expected_object=expected_object, max_bytes=max_bytes)
    return (200, data) if data else (404, None)


def write_tess_cache_entry(pathname, body: bytes | None) -> int:
    """403 for a refused name, else 204.

    Accepted-and-dropped when the cache is disabled or the body is empty: this
    is a best-effort write-back and the client must never fail on one.
    """
    key = tess_cache_key_from_route_path(pathname)
    if key is None:
        return 403
    if body:
        from cadgen.store.meshes import MeshConflictError

        try:
            _write_cached_tessellation_bytes(key, body)
        except MeshConflictError:
            return 409
        except (ValueError, TypeError, KeyError, OverflowError, struct.error):
            return 400
    return 204


def _request_items(body: bytes | None, field: str) -> list | None:
    # Index facts are small. Refuse oversized metadata requests before JSON
    # parsing; a caller splits an assembly into bounded probe/body batches.
    if len(body or b"") > TESS_CACHE_METADATA_MAX_BYTES:
        return None
    try:
        parsed = json.loads(bytes(body or b"").decode("utf-8", errors="replace"))
    except (ValueError, RecursionError):
        return None
    items = parsed.get(field) if type(parsed) is dict and set(parsed) == {field} else None
    return items if type(items) is list and len(items) <= TESS_CACHE_BATCH_MAX_NAMES else None


def read_tess_cache_probe(body: bytes | None) -> dict | None:
    """V4 metadata hits keyed by input, without loading any TESS/SURF body."""
    from cadgen.store.meshes import probe

    inputs = _request_items(body, "tessellationInputs")
    if inputs is None:
        return None
    entries = {}
    for key in inputs:
        row = probe(key) if type(key) is str else None
        if row is not None:
            entries[key] = row
    return {"entries": entries}


def read_tess_cache_batch(body: bytes | None) -> bytes | None:
    """Frame already-admitted exact-object reads in an unchanged TESB container.

    Requests contain ``entries: [{tessellationInput, object, maxBytes}]``.
    Refused/changed/missing objects are per-entry misses. Total response bytes,
    including framing, cannot exceed 32 MiB; larger single hits use bounded GET.
    """
    requests = _request_items(body, "entries")
    if requests is None:
        return None
    entries: list[bytes | None] = []
    remaining = TESS_CACHE_BATCH_MAX_BYTES - 12 - 4 * len(requests)
    for request in requests:
        data = None
        if type(request) is dict and set(request) == {"tessellationInput", "object", "maxBytes"}:
            key, digest, limit = request["tessellationInput"], request["object"], request["maxBytes"]
            if type(key) is str and type(digest) is str and type(limit) is int and limit > 0:
                data = _read_cached_tessellation_bytes(key, expected_object=digest, max_bytes=min(limit, remaining))
                if data and len(data) + (-len(data) % 4) > remaining:
                    data = None
        entries.append(data)
        if data:
            remaining -= len(data) + (-len(data) % 4)

    # Little-endian, 4-byte aligned payloads so each entry decodes zero-copy on
    # the client. Padding is emitted only for a non-empty entry.
    out = bytearray()
    out += struct.pack("<III", TESS_CACHE_BATCH_MAGIC, TESS_CACHE_BATCH_VERSION, len(entries))
    for entry in entries:
        length = len(entry) if entry else 0
        out += struct.pack("<I", length)
        if length:
            out += entry
            out += b"\0" * (-length % 4)
    return bytes(out)
