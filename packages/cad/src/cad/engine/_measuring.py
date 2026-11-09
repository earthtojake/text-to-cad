"""What measures a manufacturing check in a process (``measuring``, re-exported by ``contract``): its code and the
libraries a check measures with. Of the standard library alone, so ``cad.engine`` takes it as it is imported with
nothing else of its own loaded."""

from __future__ import annotations

import functools
import sys
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


def measure(root: Any = None) -> dict[str, Any]:
    """What measures a manufacturing check in this process now (``measuring`` keeps the first): the digest of
    this library's code (``code``: every source file of the cad package by its place in it -- a ``.py``, or the
    ``.pyc`` an install of bytecode alone holds in its place -- so a checkout's edited copy and the published one
    of one release are two) and the version of each library a check measures with (``libraries``,
    ``MEASURING``; None for one not installed here). A process with no CAD kernel (``OCP`` not found: the
    ``cad`` command's environment) names no library at all: it measures nothing itself, and any process of its
    code measures for it (``measures_for``). Nothing is imported. ``root``: the package folder whose code is
    hashed, the cad package's by default."""
    import hashlib
    import importlib.util
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent if root is None else Path(root)
    found = hashlib.blake2b(digest_size=16)
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if name != "__pycache__")
        sources = set(files)
        for name in sorted(files):
            if not (name.endswith(".py") or (name.endswith(".pyc") and name[:-1] not in sources)):
                continue
            path = Path(folder) / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            found.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0" + data + b"\0")
    libraries: dict[str, str | None] = {}
    try:
        kernel = importlib.util.find_spec("OCP") is not None
    except (ImportError, ValueError):
        kernel = False
    installed = _installed() if kernel else {}
    for name, distributions in MEASURING.items() if kernel else ():
        libraries[name] = None
        for distribution in distributions:
            said = installed.get(_normal(distribution))
            if said is None:
                from importlib import metadata

                try:
                    said = metadata.version(distribution)  # one the folders' names do not say: asked the long way
                except metadata.PackageNotFoundError:
                    continue
            libraries[name] = said
            break
    return {"code": found.hexdigest(), "libraries": libraries}


def _normal(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "_", name).lower()


def _installed() -> dict[str, str]:
    """Each distribution on the import path by its normalized name, and its version, as its ``.dist-info``
    folder's name says them -- the first on the path, as Python imports it -- read from the folders' listings
    alone (``importlib.metadata`` costs more than the rest of ``cad.engine``'s import)."""
    import os

    found: dict[str, str] = {}
    for entry in sys.path:
        try:
            names = os.listdir(entry or ".")
        except OSError:
            continue
        for name in names:
            if name.endswith(".dist-info") and "-" in name:
                distribution, _, said = name[:-len(".dist-info")].partition("-")
                found.setdefault(_normal(distribution), said)
    return found


@functools.lru_cache(maxsize=1)
def measuring() -> dict[str, Any]:
    """What measures a manufacturing check in this process (``measure``), as its code was when it was loaded:
    taken as ``cad.engine`` is first imported, before anything a check measures with is, and kept for the
    process's life (a worker takes it again, at once, as it starts: ``worker.main``). The caller sends its own
    with each check (``api.check``), the process that measures it says its own with the result, a result is
    kept under the check, its release and this code and served to every caller the process that measured it
    measures for (``measures_for``), and a process unlike its caller measures nothing for it."""
    return measure()
