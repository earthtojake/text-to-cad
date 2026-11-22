"""The parts' kept measurements in the cache folder (``cad._internal.dfm.parts``), held to their bounds by the daemon.

A part's result is written and read by the process that measures it, never by the daemon, which imports no kernel:
the daemon only lists the folder, ``parts/<kind>/<xx>/<name>.json`` (never through a link: one there is passed
over, and what it leads to is never removed), and holds it to ``ENTRIES`` files and
``BYTES`` of them together, the least recently used first, by their time on disk, which a read sets again
(``bound``). It sweeps the half-written files a stopped process left there (``<name>.json.<pid>.<random>.tmp``)
once they are ``STALE_SECONDS`` old: a process writes one in an instant, so an older one has no writer left, and a
younger one may be being written now. Nothing keeps a list between two listings: what the processes wrote since is
on disk alone. The folder is listed after every check that held a checks process (``soon``, in a thread of its
own, one listing at a time), so the bounds hold after the checks that could have passed them.

The bounds: a part's result holds every item it measured, not the few a report lists, so one is a few kilobytes
to a megabyte (a part of thousands of faces); 16384 entries are a few hundred assemblies' parts in a few option
sets each, and 512 MB twice what the whole documents' measurements are held to (``measurements``), since a
document's report is put together from its parts' results and both may be kept.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

__all__ = ["BYTES", "ENTRIES", "STALE_SECONDS", "Parts"]

ENTRIES = 16384
BYTES = 512 * 2**20
STALE_SECONDS = 3600.0


class Parts:
    """The parts' folder of the cache folder ``folder()`` gives (the engine's registry, whose ``cache`` is it, or a
    folder alone; None: none), held to ``entries`` files and ``budget`` bytes (the module)."""

    def __init__(self, folder: Callable[[], Any] | None, *, entries: int = ENTRIES, budget: int = BYTES) -> None:
        self.folder, self.entries, self.budget = folder, entries, budget
        self.lock = threading.Lock()
        self.listing = False
        self.again = False
        self.held: tuple[int, int] | None = None  # the entries and their bytes at the last listing

    def _root(self) -> Path | None:
        from cad._internal.dfm.parts import FOLDER

        found = self.folder() if self.folder is not None else None
        if hasattr(found, "cache"):
            found = found.cache  # the registry's cache folder
        if found is not None and not isinstance(found, (str, os.PathLike)):
            found = found.root  # a ``registry.Folder``
        return None if found is None else Path(found) / FOLDER

    def soon(self) -> None:
        """``bound`` in a thread of its own, now -- or once more after the listing under way, where one is."""
        with self.lock:
            if self.listing:
                self.again = True
                return
            self.listing = True
        threading.Thread(target=self._listings, name="cad-parts-bounds", daemon=True).start()

    def _listings(self) -> None:
        while True:
            try:
                self.bound()
            except Exception:  # noqa: BLE001 - a cache that cannot be listed is held next time
                pass
            with self.lock:
                if not self.again:
                    self.listing = False
                    return
                self.again = False

    def bound(self, now: float | None = None) -> tuple[int, int]:
        """The folder listed: its stale half-written files removed, then its least recently used entries until it
        holds ``entries`` and ``budget`` at most. What it holds then, entries and bytes."""
        root = self._root()
        if root is None:
            return 0, 0
        now = time.time() if now is None else now
        found: list[tuple[float, int, str]] = []
        if os.path.islink(root):
            return 0, 0  # a link is never followed: what it leads to is no part of the cache's
        for kind in _folders(root):
            for folder in _folders(kind.path):
                for entry in _entries(folder.path):
                    name = entry.name
                    if entry.is_symlink():
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if name.endswith(".tmp") and ".json." in name:
                        if now - stat.st_mtime > STALE_SECONDS:
                            _remove(entry.path)
                        continue
                    if name.endswith(".json") and entry.is_file(follow_symlinks=False):
                        found.append((stat.st_mtime, stat.st_size, entry.path))
        count, size = len(found), sum(entry[1] for entry in found)
        if count > self.entries or size > self.budget:
            found.sort()
            for _when, bytes_, path in found:
                if count <= self.entries and size <= self.budget:
                    break
                if _remove(path):
                    count -= 1
                    size -= bytes_
                    try:
                        os.rmdir(os.path.dirname(path))  # its folder, gone with its last entry
                    except OSError:
                        pass
        self.held = (count, size)
        return count, size


def _folders(folder: str | Path) -> list[os.DirEntry]:
    """The folders in ``folder`` that are folders themselves, never a link to one."""
    return [entry for entry in _entries(folder) if entry.is_dir(follow_symlinks=False)]


def _entries(folder: Any) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as found:
            return sorted(found, key=lambda entry: entry.name)
    except OSError:
        return []


def _remove(path: str) -> bool:
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return True  # gone already: counted as gone
    except OSError:
        return False
