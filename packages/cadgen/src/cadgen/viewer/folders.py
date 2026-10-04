"""The explorer's two reads: one folder's entries, and the CAD files nested under a folder.

A view browses from its file's folder, one folder at a time, so nothing walks a tree to show it:
``list_folder`` is one directory read. Filtering walks the folder it starts from, bounded so that no
folder -- a home, a whole disk -- can hold a request up or wear the server down: it stops at a
number of matches, a depth and a deadline, says when it stopped early, skips hidden and build
folders, and never walks a folder twice (a link back into one is how a walk would never end).

Paths are absolute in and out, with ``/`` separators on every platform.
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Callable

from .content_types import extension_of
from .natural_sort import collation_key
from .scanner import SOURCE_EXTENSIONS, VIEWER_SKIPPED_DIRECTORIES, is_hidden_name

# A folder this full lists its first entries and says so.
LIST_LIMIT = 2000
SEARCH_LIMIT = 200
SEARCH_SECONDS = 1.5
SEARCH_DEPTH = 24


def _slashed(path: str) -> str:
    return path.replace(os.sep, "/") if os.sep != "/" else path


def absolute_folder(path: object) -> str:
    """``path`` as an absolute folder, or ``ValueError`` (``FileNotFoundError`` when it is not one)."""
    if not isinstance(path, str) or not path or not os.path.isabs(os.path.expanduser(path)):
        raise ValueError("a folder is named by its absolute path")
    folder = os.path.normpath(os.path.expanduser(path))
    if not os.path.isdir(folder):
        raise FileNotFoundError(path)
    return folder


def _skipped(name: str) -> bool:
    return is_hidden_name(name) or name in VIEWER_SKIPPED_DIRECTORIES


def _listed(name: str) -> bool:
    return not is_hidden_name(name) and extension_of(name) in SOURCE_EXTENSIONS


def _entries(folder: str):
    """``(name, kind)`` for each subfolder worth walking and each CAD file in ``folder``, unsorted."""
    with os.scandir(folder) as found:
        for entry in found:
            try:
                if entry.is_dir():
                    if not _skipped(entry.name):
                        yield entry.name, "directory"
                elif entry.is_file() and _listed(entry.name):
                    yield entry.name, "file"
            except OSError:  # a broken link or an entry that went away while it was read
                continue


def list_folder(path: object) -> dict:
    """``{path, entries: [{name, kind}], truncated}``: subfolders first, then CAD files, in natural order."""
    folder = absolute_folder(path)
    entries = sorted(_entries(folder), key=lambda item: (item[1] != "directory", collation_key(item[0])))
    return {"path": _slashed(folder), "entries": [{"name": name, "kind": kind} for name, kind in entries[:LIST_LIMIT]],
            "truncated": len(entries) > LIST_LIMIT}


def search_folder(path: object, query: object, *, limit: int = SEARCH_LIMIT, seconds: float = SEARCH_SECONDS,
                  depth: int = SEARCH_DEPTH, clock: Callable[[], float] = time.monotonic) -> dict:
    """``{path, results, truncated}``: the CAD files under ``path`` whose path below it contains ``query``.

    Shallower files first (the walk is breadth-first), each folder's in natural order. ``truncated``
    says the walk stopped before it was done: at ``limit`` matches, past ``depth`` or past ``seconds``.
    """
    folder = absolute_folder(path)
    needle = str(query or "").strip().casefold()
    deadline = clock() + seconds
    results: list[str] = []
    truncated = False
    walked: set[str] = set()
    queue = deque([(folder, 0)])
    while queue:
        current, level = queue.popleft()
        if clock() > deadline:
            truncated = True
            break
        try:
            real = os.path.realpath(current)
            if real in walked:
                continue
            walked.add(real)
            entries = sorted(_entries(current), key=lambda item: (item[1] != "directory", collation_key(item[0])))
        except OSError:  # a folder that cannot be read is passed over, as a person would
            continue
        for name, kind in entries:
            child = os.path.join(current, name)
            if kind == "directory":
                if level + 1 <= depth:
                    queue.append((child, level + 1))
                else:
                    truncated = True
                continue
            if needle in _slashed(os.path.relpath(child, folder)).casefold():
                results.append(_slashed(child))
                if len(results) >= limit:
                    return {"path": _slashed(folder), "results": results, "truncated": True}
    return {"path": _slashed(folder), "results": results, "truncated": truncated}
