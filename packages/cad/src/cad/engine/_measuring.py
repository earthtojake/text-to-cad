"""What measures a manufacturing check in a process (``measuring``, re-exported by ``contract``): its code and the
libraries a check measures with. Of the standard library alone; nothing of it runs as ``cad.engine`` is imported --
a process takes it when it first asks or measures a check (``api.check``; a worker as it starts, ``worker.main``).

Its code is said twice. ``code`` is the digest of the whole library, every source file of it: a process measures a
check for a caller of the same ``code`` alone (``contract.measures_for``). ``dfm`` is, for each process a B-rep
check measures for, the digest of the files that measure it alone (``DFM``: the files every process's measurement
runs and the process's own), so what a measurement was taken with is named by the code that took it, and an edit
anywhere else -- the server, a document type, another process -- leaves it the same. What those files import of
the library and are not hashed is their boundary (``BOUNDARY``): the reader (``cad.engine.document``, whose parts,
names and placements a measurement is of) and the plain data and refusals of the type side."""

from __future__ import annotations

import sys
import threading
from typing import Any

__all__ = ["BOUNDARY", "DFM", "DFM_COMMON", "MEASURING", "measure", "measuring"]


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

#: The source files every process's B-rep measurement runs, by their place in the cad package: the check's own
#: steps (``_dfm_check``: the parts' integrity, the units' doubt), the parts read for it and their measures
#: (``_dfm_brep``, ``_geometry`` and the kernel's validity check it asks), and the type side the measurement reads
#: (the options it is handed, ``kept``; the materials, the declared processes and the rules' helpers).
DFM_COMMON: tuple[str, ...] = (
    "build123d/_dfm_check.py", "build123d/_dfm_brep.py", "build123d/_geometry.py", "engine/kernel/checks.py",
    "_internal/dfm/__init__.py", "_internal/dfm/_common.py", "_internal/dfm/kept.py", "_internal/dfm/materials.py",
    "_internal/dfm/processes.py", "_internal/dfm/rules.py")
#: Each process's own: its measurement (``cad.build123d._dfm_<process>``), the plain geometry it measures with,
#: and its type side's module, whose helpers it calls (a tool list read, a K-factor, a wall's minimum). A process's
#: digest is of ``DFM_COMMON`` and these (``measure``'s ``dfm``).
DFM: dict[str, tuple[str, ...]] = {
    "cnc": ("build123d/_dfm_cnc.py", "build123d/_dfm_cnc_holes.py", "build123d/_dfm_cnc_model.py",
            "build123d/_dfm_cnc_turning.py", "_internal/dfm/cnc.py",
            # its holes are read by quiddity where it is available: what takes its records (and names the one
            # release of it whose records are taken, so the digest says which quiddity read), the integration
            # that asks it, and the STEP each part is handed over as
            "build123d/_dfm_cnc_recognised.py", "quiddity/__init__.py", "quiddity/_features.py",
            "quiddity/_frames.py", "quiddity/_process.py", "quiddity/_recogniser.py", "engine/export/step.py"),
    "sheet": ("build123d/_dfm_sheet.py", "_internal/sheet_plane.py", "_internal/dfm/sheet.py"),
    "molding": ("build123d/_dfm_molding.py", "_internal/molding_geometry.py", "_internal/dfm/molding.py"),
    "printing": ("build123d/_dfm_printing.py", "_internal/meshops_printing.py", "_internal/dfm/printing.py"),
}
#: What the files of ``DFM`` import of the library and no digest holds: the reader, whose parts, names, placements
#: and materials a measurement is of (said by what it read, not by its code), and the plain data, refusals and
#: option resolving of the type side, which change no figure. And, of cnc's recogniser: where its process runs
#: (the engine's places and its door, by which the environment that holds quiddity is found: where quiddity
#: answers, never what), and what a document's STEP is written with that one shape's bytes are not (its tree and
#: its styles).
BOUNDARY: tuple[str, ...] = ("cad.engine.document", "cad.engine.refs", "cad.results", "cad._internal.refused",
                             "cad._internal.manufacturing",
                             "cad.engine.places", "cad.engine.client", "cad.engine.export.tree",
                             "cad.engine.step_style")

# Each digest, by the stat of the source files it was taken of (``_digest``): the same files at the same sizes and
# times are not read again. The whole package's by its folder, each process's by its folder and its name.
_CODES: dict[str, tuple[tuple[tuple[str, int, int], ...], str]] = {}
_TAKEN: dict[str, Any] = {}
_LOCK = threading.Lock()


def measure(root: Any = None) -> dict[str, Any]:
    """What measures a manufacturing check in a process started now (``measuring`` is this process's own): the
    digest of this library's code (``code``: every source file of the cad package by its place in it -- a ``.py``,
    or the ``.pyc`` an install of bytecode alone holds in its place -- so a checkout's edited copy and the published
    one of one release are two; read again only when a file's size or time is not the one it was read at), the
    digest of each process's measuring files alike (``dfm``: ``{process: digest}``, of its files in ``DFM`` alone)
    and the version of each library a check measures with (``libraries``, ``MEASURING``; None for one not installed
    here). A process with no CAD kernel (``OCP`` not found: the ``cad`` command's environment) names no library at
    all: it measures nothing itself, and any process of its code measures for it (``measures_for``). Nothing is
    imported. ``root``: the package folder whose code is hashed, the cad package's by default."""
    return _measure(root)[0]


def _measure(root: Any = None) -> tuple[dict[str, Any], int, dict[str, int]]:
    """``measure``'s answer, the latest time (ns) any source file it hashed was changed, and the latest time each
    process's measuring files were."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent if root is None else Path(root)
    code, newest = _code(root)
    dfm: dict[str, str] = {}
    changed: dict[str, int] = {}
    for process in DFM:
        dfm[process], changed[process] = _measuring_code(root, process)
    libraries: dict[str, str | None] = {}
    try:
        kernel = importlib.util.find_spec("OCP") is not None
    except (ImportError, ValueError):
        kernel = False
    installed = _installed() if kernel else {}
    for name, distributions in MEASURING.items() if kernel else ():
        libraries[name] = _version(name, distributions, installed)
    return {"code": code, "dfm": dfm, "libraries": libraries}, newest, changed


def _code(root: Any) -> tuple[str, int]:
    """The digest of the source files under ``root`` (``measure``'s ``code``) and the latest time one was changed:
    each file stated first, and the digest taken again only when one's size or time is not the kept one's."""
    import os

    top = os.fspath(root)
    files: list[tuple[str, str]] = []
    for folder, folders, names in os.walk(top):
        folders[:] = sorted(name for name in folders if name != "__pycache__")
        sources = set(names)
        inside = os.path.relpath(folder, top).replace(os.sep, "/")
        for name in sorted(names):
            if not (name.endswith(".py") or (name.endswith(".pyc") and name[:-1] not in sources)):
                continue
            files.append((name if inside == "." else f"{inside}/{name}", os.path.join(folder, name)))
    return _digest(top, files)


def _measuring_code(root: Any, process: str) -> tuple[str, int]:
    """The digest of ``process``'s measuring files under ``root`` (``DFM_COMMON`` and ``DFM[process]``: each a
    ``.py``, else the ``.pyc`` an install of bytecode alone holds in its place, as ``_code`` reads them) and the
    latest time one was changed."""
    import os

    top = os.fspath(root)
    files: list[tuple[str, str]] = []
    for place in (*DFM_COMMON, *DFM[process]):
        path = os.path.join(top, *place.split("/"))
        if not os.path.exists(path) and os.path.exists(path + "c"):
            place, path = place + "c", path + "c"
        files.append((place, path))
    return _digest(f"{top}\0{process}", files)


def _digest(memo: str, files: list[tuple[str, str]]) -> tuple[str, int]:
    """The digest of ``files`` (each its place, by which it is hashed, and its path) and the latest time one was
    changed: each stated first, and the digest, kept under ``memo``, taken again only when one's size or time is
    not the kept one's. A file not there is left out."""
    import hashlib
    import os

    stated: list[tuple[str, str]] = []
    stats: list[tuple[str, int, int]] = []
    for place, path in files:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        stated.append((place, path))
        stats.append((place, stat.st_size, stat.st_mtime_ns))
    key = tuple(stats)
    newest = max((changed for _place, _size, changed in stats), default=0)
    with _LOCK:
        kept = _CODES.get(memo)
    if kept is not None and kept[0] == key:
        return kept[1], newest
    found = hashlib.blake2b(digest_size=16)
    for place, path in stated:
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        found.update(place.encode("utf-8") + b"\0" + data + b"\0")
    digest = found.hexdigest()
    with _LOCK:
        _CODES[memo] = (key, digest)  # stated before it was read: a file changed meanwhile is read again next
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
    it and it measures its checks itself -- and makes each process's measuring code whose files it is one of
    (``dfm``) no other's alike, the others' standing. The caller sends its own with each check (``api.check``), the
    process that measures it says its own with the result, a result is kept under the check, its release and this
    code and served to every caller the process that measured it measures for (``measures_for``), and a process
    unlike its caller measures nothing for it."""
    with _LOCK:
        taken = _TAKEN.get("measuring")
    if taken is not None:
        return taken
    found, newest, changed = _measure()
    loaded = getattr(sys.modules.get("cad"), "_LOADED_NS", None)
    if isinstance(loaded, int):
        found = {**found, "code": found["code"] + (EDITED if newest > loaded else ""),
                 "dfm": {process: digest + (EDITED if changed[process] > loaded else "")
                         for process, digest in found["dfm"].items()}}
    with _LOCK:
        return _TAKEN.setdefault("measuring", found)
