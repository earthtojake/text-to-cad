"""HTTP path framing for the store's component meshes (read-only to clients)."""

from __future__ import annotations

import re

from cadgen.store.tess_cache import (
    TESS_CACHE_BATCH_MAGIC, TESS_CACHE_BATCH_MAX_BYTES,
    TESS_CACHE_BATCH_MAX_NAMES, TESS_CACHE_BATCH_VERSION,
    TESS_CACHE_METADATA_MAX_BYTES, parse_tess_cache_admission,
    read_tess_cache_batch, read_tess_cache_probe, read_tessellation_cache,
    tessellation_cache_dir,
)
from .encoding import UriError, strict_decode_uri_component

__all__ = [
    "TESS_CACHE_BATCH_MAGIC", "TESS_CACHE_BATCH_MAX_BYTES",
    "TESS_CACHE_BATCH_MAX_NAMES", "TESS_CACHE_BATCH_PATH",
    "TESS_CACHE_BATCH_VERSION", "TESS_CACHE_METADATA_MAX_BYTES",
    "TESS_CACHE_PROBE_PATH", "TESS_CACHE_ROUTE_PREFIX",
    "parse_tess_cache_admission", "read_tess_cache_batch",
    "read_tess_cache_entry", "read_tess_cache_probe",
    "tess_cache_key_from_route_path", "tessellation_cache_dir",
]

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"
TESS_CACHE_PROBE_PATH = "/__tess_cache/probe"
_TESS_CACHE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*\.glb")
_MESH_SUFFIX = ".glb"


def tess_cache_key_from_route_path(pathname) -> str | None:
    try:
        name = strict_decode_uri_component(
            str(pathname or "")[len(TESS_CACHE_ROUTE_PREFIX):],
        )
    except UriError:
        return None
    if not _TESS_CACHE_NAME_PATTERN.fullmatch(name) or ".." in name:
        return None
    return name[:-len(_MESH_SUFFIX)]


def read_tess_cache_entry(
    pathname, *, expected_object=None, max_bytes=None,
) -> tuple[int, bytes | None]:
    key = tess_cache_key_from_route_path(pathname)
    if key is None:
        return 403, None
    try:
        data = read_tessellation_cache(
            key, expected_object=expected_object, max_bytes=max_bytes,
        )
    except ValueError:
        data = None
    return (200, data) if data else (404, None)
