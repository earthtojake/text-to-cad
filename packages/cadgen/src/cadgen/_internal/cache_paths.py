"""The store root, spelled for the modules that predate ``cadgen.store``.

ONE resolution rule lives in :mod:`cadgen.store.paths`; this module re-exports
it so the viewer's mesh routes keep one spelling of
where the store is. Everything under
the root is best-effort: deleting any entry — or the whole root — costs a
rebuild, never correctness.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.store.paths import store_root

__all__ = ["cache_root"]


def cache_root() -> Path:
    return store_root()
