"""Where the store lives — ONE resolution rule.

1. ``$CADGEN_CACHE_DIR`` when set — the explicit override.
2. ``$XDG_CACHE_HOME/cadgen`` on POSIX / ``%LOCALAPPDATA%\\cadgen`` on Windows when set.
3. ``~/.cache/cadgen`` otherwise.

Only cadgen opens the store; every client reaches it through a host's routes.
"""

from __future__ import annotations

import os
from pathlib import Path

# "document" is the ARTIFACT side (sha256 of a file's bytes → its tree); every
# other kind is the code/dependency side. STORE.md §2, the law.
INDEX_KINDS = ("model", "document", "output", "component", "surface", "bounds", "mesh", "drawing", "section")

# Kinds an older cadgen wrote and this one never reads: the sweeper removes
# them, with every object only they named (STORE.md §8). A folder under index/
# in neither list is not this cadgen's to judge -- a newer cadgen's, or no
# cadgen's at all -- and nothing here touches it.
RETIRED_KINDS = ("op",)

# The kinds eviction may drop (STORE.md §8): derivations that a build or a
# reader recomputes on a miss. Records, document entries and output entries
# are never evicted.
DERIVED_KINDS = ("component", "surface", "bounds", "mesh", "drawing", "section")

def store_root() -> Path:
    override = os.environ.get("CADGEN_CACHE_DIR", "").strip()
    if override:
        # Absolutized ONCE, against the cwd of the process that first reads it,
        # and written back so every later reader -- this process after a chdir,
        # a worker it spawns -- sees the same folder. A relative value is otherwise
        # a different store from every directory.
        root = Path(override).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
            os.environ["CADGEN_CACHE_DIR"] = str(root)
        return root
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "cadgen"
    else:
        xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "").strip()
        if xdg_cache_home:
            return Path(xdg_cache_home) / "cadgen"
    return Path.home() / ".cache" / "cadgen"


class StoreUnwritableError(RuntimeError):
    """The store's folder cannot be written. One sentence, no frames."""


def unwritable(exc: OSError, target: Path | str) -> StoreUnwritableError:
    root = store_root()
    return StoreUnwritableError(
        f"the store at {root} is not writable ({exc.strerror or type(exc).__name__} writing "
        f"{Path(target).name}); point CADGEN_CACHE_DIR at a folder this user can write"
    )


def objects_dir() -> Path:
    return store_root() / "objects"


def index_dir(kind: str) -> Path:
    if kind not in INDEX_KINDS:
        raise ValueError(f"unknown index kind {kind!r}; one of {INDEX_KINDS}")
    return store_root() / "index" / kind
