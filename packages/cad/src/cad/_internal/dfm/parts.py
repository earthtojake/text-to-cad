"""What is kept of one part's measurement: by the part as it stands and what measured it, whatever document it is
in, so a check of an assembly one part of which was edited measures that part alone.

**What is kept, and for which processes.** A CNC check's and a sheet check's result of one part (``dfm-cnc``,
``dfm-sheet``: what the part adds to its document's report, before the document is put together), and the
recogniser's features of one part (``features``: ``cad.quiddity``'s answer, read by the CNC check's holes). Each
process measures a part in a frame of its own and on its own, so a part's result is the same in any document that
holds it standing so: the document's report is put together from its parts' results by code that reads no kernel.
Molding and printing keep nothing per part: a mold's time and ray budgets are the document's, and a print's parts
stand on one plate and in one build volume, among each other.

**By what.** A part's geometry (``key``: its prototype's geometry key) and the rest of what its result is made of,
as plain data (``rest``): how it stands (``standing``: the exact matrix its document places it by, the shift of
an occurrence from the first, the token of the mesh it was read with, which solid of the part it is), for a
measurement its name and its refs' owner, the options the process's measurement reads, whatever of the document
still reaches the part (the caller says it), and what measured it -- the digest of that process's measuring code
(``cad.engine._measuring``'s ``dfm``), the libraries' versions and the version of a report's shape
(``kept.MEASURE_VERSION``). A CNC part's result holds the refinements of its walls and gaps its reports asked so
far, each added as it is made. A part placed otherwise, renamed or under
another owner is another entry; the same part standing the same way, named the same, in another document is the
same entry. A result is never moved from one placement to another: a moved point is rounded, so a moved result
is not the one measured there.

**What is not kept.** A result its process could make otherwise next time (``unrepeatable``: a failure for want
of memory, by any of its names, or a table that says of itself ``repeatable: false``, wherever either lies -- a
process says so of a part that went on past a failure for want of memory it caught, ``_common.passed_over``), a
part no document gave (a live shape's has no geometry key), and anything measured by code edited since its
process loaded it (``_measuring.EDITED``: a code no other process has), or edited on disk since then: the code is
asked again as each result is written (``_measuring.current``), since a process imports a process's modules only
as it first measures one.

**The recogniser.** A CNC part's result and a part's features are kept only where quiddity's answer is one the part
would give again: available, from the one release whose records are taken, or unavailable for a reason of the
part's own. So a report put together from kept results is the one a fresh measurement makes with the recogniser
available, and stays so while it is not (its environment not made, or another release installed): the kept answer
is the better reading, never a stale one.

**On disk**, in the cache folder (``places.cache_dir``):

    parts/<kind>/<xx>/<geometry key>-<digest of the rest>.json    {"format", "kind", "geometry", "rest", "result"}

each written whole by the process that measured it, as soon as the part is measured (a file beside it, then
renamed over it: ``<name>.<pid>.<random>.tmp``), so a check stopped at its limits keeps the parts it finished. A
read sets the file's time again. An entry that does not read as what its name says -- not JSON, another format,
another kind's, geometry's or rest's -- is removed, never served, and so is one whose result its process cannot
put a report together from (``forget``): the part is measured afresh, and no check fails for what was kept. A folder
that takes no write keeps nothing, and says nothing: it is a cache. The engine holds the folder to its bounds, least recently used first, and sweeps the
half-written files a stopped process left (``cad_server.engine.parts``); ``cad cache clean`` removes it. No
kernel: the standard library, and the library's own plain modules (the options' and the measuring code's digests,
the words for a failure for want of memory, the one rename every writer lands a file with).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from cad._internal.atomic_replace import replace_atomic
from cad._internal.dfm._common import out_of_memory

__all__ = ["CNC", "FEATURES", "FOLDER", "FORMAT", "KINDS", "SHEET", "Kept", "standing", "unrepeatable"]

#: The folder of the cache folder the parts are kept in, and the kinds of what is kept, each a folder of it.
FOLDER = "parts"
SHEET, CNC, FEATURES = "dfm-sheet", "dfm-cnc", "features"
KINDS = (SHEET, CNC, FEATURES)
#: The processes whose parts are kept, by the kind each is kept as.
PROCESSES = {"sheet": SHEET, "cnc": CNC}
#: The format of an entry's file: another is a file that does not read.
FORMAT = 1

_GEOMETRY = re.compile(r"[0-9a-f]{16,64}")


def standing(part: Any) -> dict[str, Any] | None:
    """How a part of a document stands, as plain data: the exact matrix its occurrence is placed by (``matrix``),
    the shift of an occurrence from its part's first (``shift``, ``_dfm_brep.every_occurrence``; None for the first),
    the token of the triangulation it was read with (``mesh``) and, of a part measured solid by solid, which solid of
    how many it is (``solid``). None for a part no document gave (a live shape's: no geometry key, no matrix)."""
    key, matrix = getattr(part, "key", ""), getattr(part, "matrix", ())
    if not isinstance(key, str) or not _GEOMETRY.fullmatch(key) or not matrix:
        return None
    shift = getattr(part, "shift", ())
    solid = getattr(part, "solid", ())
    return {"matrix": [float(value) for value in matrix], "shift": [float(value) for value in shift] if shift else None,
            "mesh": str(getattr(part, "mesh", "") or ""), "solid": [int(value) for value in solid] if solid else None}


def unrepeatable(value: Any) -> bool:
    """Whether a result, or what it holds, could come out otherwise the next time from the same part, options and
    code: a table whose ``error`` is a failure for want of memory, by any of its names (``_common.out_of_memory``),
    or one that says of itself ``"repeatable": False``, wherever either lies. A table that says true, or nothing,
    is repeatable."""
    if isinstance(value, dict):
        error = value.get("error")
        return ((isinstance(error, str) and out_of_memory(error)) or value.get("repeatable") is False
                or any(unrepeatable(item) for item in value.values()))
    return isinstance(value, list) and any(unrepeatable(item) for item in value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_plain)


def _plain(value: Any) -> Any:
    """What JSON has no word for, as a measurement's plain data says it: numpy's numbers and arrays as Python's
    (``tolist``), read without importing numpy; anything else is no plain data."""
    if type(value).__module__ == "numpy" and callable(getattr(value, "tolist", None)):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is no plain data")


class Kept:
    """The parts kept in a cache folder's ``parts/`` (the module), measured by ``code`` with ``libraries``:
    ``get`` a part's result, ``keep`` one, ``settled`` a result as it reads back from disk. ``counts``: by kind,
    the results found (``reused``), the ones not found (``measured``: each a part measured, or asked of the
    recogniser, here) and the ones written (``kept``) -- what a test reads of what a check measured."""

    def __init__(self, folder: Path | str | None, code: str, libraries: dict[str, Any] | None = None,
                 process: str | None = None) -> None:
        self.folder = None if folder is None else Path(folder)
        self.code, self.libraries, self.process = str(code), dict(libraries or {}), process
        self.counts: dict[str, dict[str, int]] = {kind: {"reused": 0, "measured": 0, "kept": 0} for kind in KINDS}

    @classmethod
    def of(cls, process: str) -> "Kept | None":
        """The parts kept for ``process`` in this process's cache folder, found by the code that measures it here
        (``_measuring.measuring``); None for a process none of whose parts are kept (``PROCESSES``), or code edited
        since this process loaded it."""
        from cad.engine import places
        from cad.engine._measuring import EDITED, measuring

        if process not in PROCESSES:
            return None
        found = measuring()
        code = (found.get("dfm") or {}).get(process)
        if not isinstance(code, str) or not code or code.endswith(EDITED):
            return None
        return cls(places.cache_dir() / FOLDER, code, found.get("libraries") or {}, process)

    def _rest(self, kind: str, rest: dict[str, Any]) -> str:
        from cad._internal.dfm.kept import MEASURE_VERSION

        return _canonical({"format": FORMAT, "kind": kind, **rest, "v": MEASURE_VERSION, "code": self.code,
                           "libraries": self.libraries})

    def _path(self, kind: str, geometry: str, rest: str) -> Path:
        assert self.folder is not None
        digest = hashlib.blake2b(rest.encode("utf-8"), digest_size=10).hexdigest()
        return self.folder / kind / geometry[:2] / f"{geometry}-{digest}.json"

    def counted(self, kind: str, found: bool) -> None:
        """One part of ``kind`` found kept (``reused``), or not (``measured``)."""
        self.counts[kind]["reused" if found else "measured"] += 1

    def get(self, kind: str, geometry: Any, rest: dict[str, Any], *, count: bool = True) -> Any:
        """The result kept of a part of geometry key ``geometry`` and ``rest`` (the module's **By what**), or None:
        none kept, one that does not read (removed), or no folder. ``count`` False: not counted (``counted``), for
        a caller that may look again."""
        found = self._got(kind, geometry, rest)
        if count:
            self.counted(kind, found is not None)
        return found

    def _got(self, kind: str, geometry: Any, rest: dict[str, Any]) -> Any:
        if self.folder is None or not isinstance(geometry, str) or not _GEOMETRY.fullmatch(geometry):
            return None
        said = self._rest(kind, rest)
        path = self._path(kind, geometry, said)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        try:
            found = json.loads(data.decode("utf-8"))
            good = (isinstance(found, dict) and found.get("format") == FORMAT and found.get("kind") == kind
                    and found.get("geometry") == geometry and _canonical(found.get("rest")) == said
                    and "result" in found)
        except (UnicodeDecodeError, ValueError, TypeError):
            good = False
        if not good:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        try:
            os.utime(path)  # the most recently used, by its time on disk
        except OSError:
            pass
        return found["result"]

    def forget(self, kind: str, geometry: Any, rest: dict[str, Any]) -> None:
        """The result kept of a part of geometry key ``geometry`` and ``rest`` removed: one its process could not
        put a report together from."""
        if self.folder is None or not isinstance(geometry, str) or not _GEOMETRY.fullmatch(geometry):
            return
        try:
            self._path(kind, geometry, self._rest(kind, rest)).unlink()
        except OSError:
            pass

    def keep(self, kind: str, geometry: Any, rest: dict[str, Any], result: Any) -> None:
        """``result`` kept as the one of a part of geometry key ``geometry`` and ``rest``, written whole; nothing
        where it is ``unrepeatable``, is no plain data, the folder takes no write, or the process's measuring code
        on disk is no longer the code it was found by (``_measuring.current``)."""
        if self.folder is None or not isinstance(geometry, str) or not _GEOMETRY.fullmatch(geometry) \
                or unrepeatable(result):
            return
        if self.process is not None:
            from cad.engine._measuring import current

            if current(self.process) != self.code:
                return
        said = self._rest(kind, rest)
        try:
            body = json.dumps({"format": FORMAT, "kind": kind, "geometry": geometry, "rest": json.loads(said),
                               "result": result}, separators=(",", ":"), default=_plain).encode("utf-8")
        except (TypeError, ValueError):
            return
        path = self._path(kind, geometry, said)
        staged = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(body)
            replace_atomic(staged, path)
        except OSError:
            try:
                staged.unlink()
            except OSError:
                pass
            return
        self.counts[kind]["kept"] += 1

    @staticmethod
    def settled(result: Any) -> Any:
        """``result`` as it reads back from its file -- its tuples lists, numpy's numbers Python's -- so a part
        measured now and one read from disk put a document together alike; ``result`` itself where it is no plain
        data (and so is never kept)."""
        try:
            return json.loads(json.dumps(result, separators=(",", ":"), default=_plain))
        except (TypeError, ValueError):
            return result
