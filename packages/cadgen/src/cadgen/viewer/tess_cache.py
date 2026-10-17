"""HTTP path framing for the store's parts (read-only to clients, ``cadgen.store.tess_cache``)."""

from __future__ import annotations

from cadgen.store.tess_cache import (
    TESS_CACHE_BATCH_MAGIC, TESS_CACHE_BATCH_MAX_BYTES,
    TESS_CACHE_BATCH_MAX_NAMES, TESS_CACHE_BATCH_VERSION,
    TESS_CACHE_METADATA_MAX_BYTES, parse_tess_cache_admission,
    read_part_object, read_tess_cache_batch, read_tess_cache_probe, tess_cache_name,
)
from .encoding import UriError, strict_decode_uri_component

__all__ = [
    "TESS_CACHE_BATCH_MAGIC", "TESS_CACHE_BATCH_MAX_BYTES",
    "TESS_CACHE_BATCH_MAX_NAMES", "TESS_CACHE_BATCH_PATH",
    "TESS_CACHE_BATCH_VERSION", "TESS_CACHE_METADATA_MAX_BYTES",
    "TESS_CACHE_PROBE_PATH", "TESS_CACHE_ROUTE_PREFIX",
    "parse_tess_cache_admission", "read_tess_cache_batch",
    "read_tess_cache_entry", "read_tess_cache_probe", "tess_cache_name_from_route_path",
]

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"
TESS_CACHE_PROBE_PATH = "/__tess_cache/probe"


def tess_cache_name_from_route_path(pathname) -> str | None:
    """The route's file name (``<part key>.glb``, ``<part key>.selectors.json``); None for
    a path that names no part's object."""
    try:
        name = strict_decode_uri_component(str(pathname or "")[len(TESS_CACHE_ROUTE_PREFIX):])
    except UriError:
        return None
    return name if tess_cache_name(name) is not None else None


def read_tess_cache_entry(pathname, *, expected_object, max_bytes) -> tuple[int, bytes | None]:
    name = tess_cache_name_from_route_path(pathname)
    if name is None:
        return 403, None
    data = read_part_object(name, expected_object=expected_object, max_bytes=max_bytes)
    return (200, data) if data else (404, None)
