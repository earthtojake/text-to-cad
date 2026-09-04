"""Where the store lives — ONE resolution rule, honored by both languages.

1. ``$CADGEN_CACHE_DIR`` when set — the explicit override.
2. ``$XDG_CACHE_HOME/cadgen`` on POSIX / ``%LOCALAPPDATA%\\cadgen`` on Windows when set.
3. ``~/.cache/cadgen`` otherwise.

The JS mirror is ``cadgenCacheRootDir`` in
``packages/cadgen-js/src/lib/surf/tessellationCacheFs.mjs``;
``tests/python/global/test_cache_root_sync.py`` pins the two together.
"""

from __future__ import annotations

import os
from pathlib import Path

# Mirror of TESSELLATION_VERSION in packages/cadgen-js/src/lib/surf/tessellate.js
# (sync-tested). It is part of the MESH index key, not a store salt.
MESH_TESSELLATION_VERSION = 1

# "document" is the ARTIFACT side (sha256 of a file's bytes → its tree); every
# other kind is the code/dependency side. STORE.md §2, the law.
INDEX_KINDS = ("model", "document", "output", "component", "op", "mesh")


def store_root() -> Path:
    override = os.environ.get("CADGEN_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "cadgen"
    else:
        xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "").strip()
        if xdg_cache_home:
            return Path(xdg_cache_home) / "cadgen"
    return Path.home() / ".cache" / "cadgen"


def objects_dir() -> Path:
    return store_root() / "objects"


def index_dir(kind: str) -> Path:
    if kind not in INDEX_KINDS:
        raise ValueError(f"unknown index kind {kind!r}; one of {INDEX_KINDS}")
    return store_root() / "index" / kind

