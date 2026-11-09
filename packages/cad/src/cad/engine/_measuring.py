"""What measures a manufacturing check in a process (``measuring``, re-exported by ``contract``): its code and the
libraries a check measures with. Of the standard library alone; nothing of it runs as ``cad.engine`` is imported --
a process takes it when it first asks or measures a check (``api.check``; a worker as it starts, ``worker.main``)."""

from __future__ import annotations

import sys
import threading
from typing import Any

__all__ = ["MEASURING", "measure", "measuring"]


# The libraries a manufacturing check measures with, by the distribution that carries each (the first of
# them installed): their versions name the measuring side with the library's code (``measuring``). A check the
# engine measures is a B-rep check -- build123d's, on OCP, a part's material read with bd_materials and its
# arrays numpy's; a mesh's check (trimesh's) is measured in its caller's own process, never asked of the engine
# (``api.check``), so its libraries name nothing here.
MEASURING: dict[str, tuple[str, ...]] = {
    "build123d": ("build123d",), "OCP": ("cadquery-ocp-novtk", "cadquery-ocp"), "bd_materials": ("bd_materials",),
    "numpy": ("numpy",)}
# What a code edited since this process loaded it is said as (``measuring``): no other process's.
EDITED = "+edited"

# Each package folder's code digest, by the stat of the source files it was taken of (``_code``): the same files
# at the same sizes and times are not read again.
_CODES: dict[str, tuple[tuple[tuple[str, int, int], ...], str]] = {}
_TAKEN: dict[str, Any] = {}
_LOCK = threading.Lock()


def measure(root: Any = None) -> dict[str, Any]:
    """What measures a manufacturing check in a process started now (``measuring`` is this process's own): the
    digest of this library's code (``code``: every source file of the cad package by its place in it -- a ``.py``,
    or the ``.pyc`` an install of bytecode alone holds in its place -- so a checkout's edited copy and the published
    one of one release are two; read again only when a file's size or time is not the one it was read at) and the
    version of each library a check measures with (``libraries``, ``MEASURING``; None for one not installed here).
    A process with no CAD kernel (``OCP`` not found: the ``cad`` command's environment) names no library at all:
    it measures nothing itself, and any process of its code measures for it (``measures_for``). Nothing is
    imported. ``root``: the package folder whose code is hashed, the cad package's by default."""
    return _measure(root)[0]


def _measure(root: Any = None) -> tuple[dict[str, Any], int]:
    """``measure``'s answer, and the latest time (ns) any source file it hashed was changed."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent if root is None else Path(root)
    code, newest = _code(root)
    libraries: dict[str, str | None] = {}
    try:
        kernel = importlib.util.find_spec("OCP") is not None
    except (ImportError, ValueError):
        kernel = False
    installed = _installed() if kernel else {}
    for name, distributions in MEASURING.items() if kernel else ():
        libraries[name] = _version(name, distributions, installed)
    return {"code": code, "libraries": libraries}, newest


def _code(root: Any) -> tuple[str, int]:
    """The digest of the source files under ``root`` (``measure``'s ``code``) and the latest time one was changed:
    each file stated first, and the digest taken again only when one's size or time is not the kept one's."""
    import hashlib
    import os

    top = os.fspath(root)
    files: list[tuple[str, str]] = []
    stats: list[tuple[str, int, int]] = []
    for folder, folders, names in os.walk(top):
        folders[:] = sorted(name for name in folders if name != "__pycache__")
        sources = set(names)
        inside = os.path.relpath(folder, top).replace(os.sep, "/")
        for name in sorted(names):
            if not (name.endswith(".py") or (name.endswith(".pyc") and name[:-1] not in sources)):
                continue
            path = os.path.join(folder, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            place = name if inside == "." else f"{inside}/{name}"
            files.append((place, path))
            stats.append((place, stat.st_size, stat.st_mtime_ns))
    key = tuple(stats)
    newest = max((changed for _place, _size, changed in stats), default=0)
    with _LOCK:
        kept = _CODES.get(top)
    if kept is not None and kept[0] == key:
        return kept[1], newest
    found = hashlib.blake2b(digest_size=16)
    for place, path in files:
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        found.update(place.encode("utf-8") + b"\0" + data + b"\0")
    digest = found.hexdigest()
    with _LOCK:
        _CODES[top] = (key, digest)  # stated before it was read: a file changed meanwhile is read again next
    return digest, newest


def _version(name: str, distributions: tuple[str, ...], installed: dict[str, str]) -> str | None:
    """The version of library ``name`` here: of the first of its ``distributions`` the folders' listings name;
    asked of ``importlib.metadata`` only where they name none and the module is there all the same (an install
    no ``.dist-info`` folder on the path says), None where it is not."""
    for distribution in distributions:
        said = installed.get(_normal(distribution))
        if said is not None:
            return said
    import importlib.util

    try:
        there = importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        there = False
    if not there:
        return None
    from importlib import metadata

    for distribution in distributions:
        try:
            return metadata.version(distribution)
        except metadata.PackageNotFoundError:
            continue
    return None


def _normal(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "_", name).lower()


def _installed() -> dict[str, str]:
    """Each distribution on the import path by its normalized name, and its version, as its ``.dist-info``
    folder's name says them -- the first folder on the path that holds one, as Python imports it -- read from the
    folders' listings alone (``importlib.metadata`` costs more than the rest of ``cad.engine``'s import). Two of
    one name in one folder (an upgrade a failed uninstall left behind): the one whose ``METADATA`` (else
    ``RECORD``) was written last; neither stated, ``importlib.metadata``'s for that name."""
    import os

    found: dict[str, str] = {}
    for entry in sys.path:
        try:
            names = os.listdir(entry or ".")
        except OSError:
            continue
        here: dict[str, list[tuple[str, str]]] = {}
        for name in names:
            if name.endswith(".dist-info") and "-" in name:
                distribution, _, said = name[:-len(".dist-info")].partition("-")
                here.setdefault(_normal(distribution), []).append((said, name))
        for distribution, versions in here.items():
            if distribution in found:
                continue
            if len(versions) == 1:
                found[distribution] = versions[0][0]
                continue
            newest = _newest(entry or ".", versions)
            if newest is not None:
                found[distribution] = newest
                continue
            from importlib import metadata

            try:
                found[distribution] = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                continue
    return found


def _newest(entry: str, versions: list[tuple[str, str]]) -> str | None:
    """Of several ``.dist-info`` folders of one distribution in ``entry``, the version of the one whose
    ``METADATA`` (else ``RECORD``) was written last; None where none of them states."""
    import os

    best: tuple[int, str] | None = None
    for said, name in versions:
        for inside in ("METADATA", "RECORD"):
            try:
                changed = os.stat(os.path.join(entry, name, inside)).st_mtime_ns
            except OSError:
                continue
            if best is None or changed > best[0]:
                best = (changed, said)
            break
    return None if best is None else best[1]


def measuring() -> dict[str, Any]:
    """What measures a manufacturing check in this process (``measure``), taken once, when a check is first asked
    (``api.check``) or as a worker starts (``worker.main``: before anything a check measures with loads), and kept
    for the process's life. It is the code this process loaded: a source file changed since the library began to
    load here (``cad._LOADED_NS``) makes it a code no other process has (``EDITED``), so no process measures for
    it and it measures its checks itself. The caller sends its own with each check (``api.check``), the process
    that measures it says its own with the result, a result is kept under the check, its release and this code and
    served to every caller the process that measured it measures for (``measures_for``), and a process unlike its
    caller measures nothing for it."""
    with _LOCK:
        taken = _TAKEN.get("measuring")
    if taken is not None:
        return taken
    found, newest = _measure()
    loaded = getattr(sys.modules.get("cad"), "_LOADED_NS", None)
    if isinstance(loaded, int) and newest > loaded:
        found = {**found, "code": found["code"] + EDITED}
    with _LOCK:
        return _TAKEN.setdefault("measuring", found)
