"""The viewer server's side of the shared component-tessellation cache.

The same mesh index (``index/mesh`` -> objects, ``STORE.md``) the snapshot host
serves, exposed to the client on ``/__tess_cache/`` — GET one entry, POST one
write-back, POST ``/batch`` for the TESB container (one round trip for a whole
assembly's hit set).

Entries are OPAQUE here: this module stores and frames bytes. The one codec
lives in ``packages/cadgen-js/src/lib/surf/tessellationCache.js``, which is also
the batch format's home, and the framing below is pinned against that decoder.

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
    "TESS_CACHE_ROUTE_PREFIX",
    "read_tess_cache_batch",
    "read_tess_cache_entry",
    "tess_cache_key_from_route_path",
    "tessellation_cache_dir",
    "write_tess_cache_entry",
]

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"

# Mirror of the snapshot host's pattern. ``fullmatch`` rather than a ``$``
# anchor: Python's ``$`` also matches before a trailing newline, so
# ``"a.tess\n"`` would pass where JavaScript's ``$`` refuses it.
_TESS_CACHE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*\.tess")

TESS_CACHE_BATCH_MAGIC = 0x42534554  # "TESB" little-endian
TESS_CACHE_BATCH_VERSION = 1
TESS_CACHE_BATCH_MAX_NAMES = 4096

_TESS_SUFFIX = ".tess"


def _tessellation_cache_enabled() -> bool:
    """Read per call: the suites flip this after the app is constructed."""
    return os.environ.get("CADGEN_MESH_CACHE") != "0"


def tessellation_cache_dir() -> str:
    """The mesh index (``index/mesh``); entries point at objects."""
    from cadgen.store.paths import index_dir

    return str(index_dir("mesh"))


def _read_cached_tessellation_bytes(key: str) -> bytes | None:
    if not _tessellation_cache_enabled():
        return None
    try:
        from cadgen.store.index import read_entry
        from cadgen.store.objects import read_object

        entry = read_entry("mesh", key)
        digest = str((entry or {}).get("object") or "")
        return read_object(digest) if digest else None
    except (OSError, ValueError):
        return None


def _write_cached_tessellation_bytes(key: str, data: bytes) -> None:
    """Best-effort: a full disk or a permissions problem must not fail callers.
    The bytes become an object; the entry maps the key to it."""
    if not _tessellation_cache_enabled():
        return
    try:
        from cadgen.store.index import write_entry
        from cadgen.store.objects import put_object

        write_entry("mesh", key, {"object": put_object(data)})
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


def read_tess_cache_entry(pathname) -> tuple[int, bytes | None]:
    """``(status, body)``: 403 for a refused name, 404 for a miss, 200 for a hit."""
    key = tess_cache_key_from_route_path(pathname)
    if key is None:
        return 403, None
    data = _read_cached_tessellation_bytes(key)
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
        _write_cached_tessellation_bytes(key, body)
    return 204


def read_tess_cache_batch(body: bytes | None) -> bytes | None:
    """The TESB container for a JSON ``{"names": [...]}`` request.

    Refused names, non-strings and read failures are per-entry MISSES (zero
    length), never errors — one bad key in an assembly's hit set must not cost
    the whole round trip. ``None`` means the REQUEST was malformed, which the
    route answers 400.

    ``errors="replace"``, matching ``Buffer.from(body).toString("utf8")``. That
    is the same per-entry-miss rule applied to the bytes: a request carrying one
    undecodable name still names its other components, and Node answered every
    one of them. Strict decoding turned the whole batch into a 400, so a single
    bad byte cost an assembly its entire tessellation round trip. The
    substituted U+FFFD lands inside a JSON string, which parses, and the name it
    forms then misses in the store like any other unknown key.
    """
    try:
        parsed = json.loads(bytes(body or b"").decode("utf-8", errors="replace"))
    except ValueError:
        return None
    names = parsed.get("names") if isinstance(parsed, dict) else None
    if not isinstance(names, list) or len(names) > TESS_CACHE_BATCH_MAX_NAMES:
        return None

    entries: list[bytes | None] = []
    for name in names:
        if not isinstance(name, str):
            entries.append(None)
            continue
        key = tess_cache_key_from_route_path(f"{TESS_CACHE_ROUTE_PREFIX}{name}")
        entries.append(None if key is None else _read_cached_tessellation_bytes(key))

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
