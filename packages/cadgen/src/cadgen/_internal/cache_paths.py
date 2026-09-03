"""The store root, spelled for the modules that predate ``cadgen.store``.

ONE resolution rule lives in :mod:`cadgen.store.paths`; this module re-exports
it so the op memo, the viewer's tessellation cache and the (phase-1, still
present) lock layer keep one spelling of where the store is. Everything under
the root is best-effort: deleting any entry — or the whole root — costs a
rebuild, never correctness.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.store.paths import MESH_TESSELLATION_VERSION, locks_dir, store_root

__all__ = ["MESH_TESSELLATION_VERSION", "cache_root", "locks_dir"]


def cache_root() -> Path:
    return store_root()
