"""``GET /api/v1/documents/kicad_pcb/<id>/plot``, ``.../models`` and ``.../drc``: a KiCad board drawn as geometry per layer,
and KiCad's design rule check of it, each kept by the board's bytes.
``GET /api/v1/documents/kicad_sch/<id>/plot``: a KiCad schematic, its hierarchy read from its files, every
sheet a page of layers (:mod:`cad.engine.formats.kicad.schematic_plot`), read again on each request; with
``?sheet=/Power/`` that sheet's page alone, and with ``index=0`` without the hierarchy's index (the viewer
reads the sheet on screen, the index with the first). The hierarchy is parsed once per revision of its
files (``SchematicAnswers``): kept with the stamp of every file and folder it read (``mtime_ns``, size,
inode), so an edit to any sheet, a sheet file added or a project file beside the root reads it anew,
and each page answered is kept beside it.

The board is the document's file, by its absolute path (``http_app`` resolves the id): a path that is not
absolute, or not a ``.kicad_pcb``, is 400, a missing file 404. A file that is not a readable board is 400
with the reason (``PlotError``).

* ``plot``: the payload (``cad.engine.formats.kicad.poured.payload``) with the pours KiCad refills on a
  copy (``cad_server._internal.boards.refill``: kicode, in the environment of ``cad[kicad]``); without
  KiCad, or when the refill fails, the board as saved, the payload's ``pours`` saying so.
* ``models``: the board's 3D models table (``BoardAnswers.models``): each model its footprints name, the STEP on
  this computer it is (by a document id the engine's STEP routes serve its mesh by: the table carries no path and
  the page asks for none; the STEP's own document, as every document, names its file in its structure and its
  catalog entry) or why it has none -- read by the rules of ``cad.engine.formats.kicad.models3d`` (the board's folder, KiCad's 3D
  library, ``CAD_KICAD_3DMODELS``; STEP alone), afresh on every request (``stat`` alone), so a model file
  added, edited or removed is the next answer's.
* ``drc``: ``cad kicad_pcb drc --json``'s ``CheckResult`` as data (``boards.drc``): ``ok``, ``path``,
  ``findings`` (each a severity, a code, a message and a location) and ``measurements.drc``, every finding
  as KiCad reported it -- ``check`` (violation, unconnected, parity), ``severity``, ``type``,
  ``description``, ``at`` ([x, y] mm in KiCad's frame, y down) and ``items``, each ``{uuid, description,
  pos}`` and, where the board's index names its uuid, ``ref`` (``#R1``, ``#R1.2``, ``#track:<uuid>``...).

Each is made off the request, one per board key at a time (every request for that key joins it): a request
waits on it as long as ``hold_seconds``, then answers 202 ``{"state": "plotting"|"checking", "retryMs"}``
and is asked again; KiCad and the plot never run on a request's thread. The last ``HELD`` answers are kept
in memory by key, the plot's codings with it (``compressed``); the refilled plot and the DRC are kept on
disk by the same key (``boards``). The key is the board's bytes, its project's and rules' and the plotting
code's (``poured.key``), worked out again whenever the file's ``mtime_ns``, size or inode differs, so a
changed file is a new key and nothing stale is answered. Each 200 carries ``etag: "<key>"``; a request
naming it (``If-None-Match``) is answered 304. The answers stay ``cache-control: no-store``, as every
answer of the engine's is (``response``): the browser keeps no board on disk under the page's origin, and
a reload is answered from the engine's memory or disk instead.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from cad.engine.formats.kicad import PLOT_SUFFIXES

from .backend import absolute_path
from .scanner import node_basename

__all__ = ["HOLD_SECONDS", "HELD", "BoardAnswers", "PLOT_SUFFIXES", "SchematicAnswers", "resolve_plot_path",
           "schematic_payload_response"]

# How long a request waits on a board's plot or DRC before it answers 202.
HOLD_SECONDS = 2.0
# Answers kept in memory, by key and product: a large board's plot is tens of megabytes.
HELD = 6


def resolve_plot_path(file_ref) -> str | None:
    """The absolute ``.kicad_pcb`` this ref names, or ``None`` for a 404.

    Raises ``ValueError`` for a ref this route will not take.
    """
    if not file_ref:
        raise ValueError("a plot is read from the absolute path of a .kicad_pcb or a .kicad_sch")
    candidate = absolute_path(file_ref)
    if not candidate.lower().endswith(PLOT_SUFFIXES):
        raise ValueError(f"a plot is a KiCad board's or schematic's; {node_basename(candidate)} is neither")
    return candidate if os.path.isfile(candidate) else None


def _stamp(path) -> tuple[int, int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size, stat.st_ino


class SchematicAnswers:
    """The schematic hierarchies read, by the file asked for: each its index (``read_schematic_index``'s
    answer), the stamps of what it was read from (every sheet file, each one's folder, the file asked
    for and its folder: a sheet file added, a ``.kicad_pro`` beside the root, an edit anywhere changes
    one) and the pages answered from it (by sheet and ``index``). The last ``HELD`` are kept; a stamp
    that differs reads the hierarchy again."""

    def __init__(self, held: int = HELD):
        self.held = held
        self.lock = threading.Lock()
        self.kept: OrderedDict[str, dict] = OrderedDict()

    @staticmethod
    def _sources(candidate: str, index) -> tuple[str, ...]:
        files = {str(path) for path in index.trees} | {candidate}
        return tuple(sorted(files | {os.path.dirname(path) for path in files}))

    def _entry(self, candidate: str) -> dict:
        with self.lock:
            entry = self.kept.get(candidate)
            if entry is not None:
                self.kept.move_to_end(candidate)
        if entry is not None and entry["stamps"] is not None and all(_stamp(path) == stamp for path, stamp in entry["stamps"]):
            return entry
        from cad.engine.formats.kicad.schematic import read_schematic_index

        started = time.time_ns()
        read = read_schematic_index(candidate)
        stamps = tuple((path, _stamp(path)) for path in self._sources(candidate, read[0]))
        # A file written while it was read may hold what was not read: such a read answers this request
        # and is read again on the next (no stamps), never kept as the file's.
        if any(stamp is None or stamp[0] >= started for _path, stamp in stamps):
            stamps = None
        entry = {"stamps": stamps, "read": read, "pages": OrderedDict(), "lock": threading.Lock()}
        with self.lock:
            self.kept[candidate] = entry
            self.kept.move_to_end(candidate)
            while len(self.kept) > self.held:
                self.kept.popitem(last=False)
        return entry

    def payload(self, candidate: str, sheet: str | None, index: bool) -> bytes:
        """The payload's bytes for ``sheet`` (``None``: every sheet) with or without the index."""
        from cad.engine.formats.kicad.schematic_plot import schematic_payload_bytes

        entry = self._entry(candidate)
        key = (sheet, index)
        with entry["lock"]:
            body = entry["pages"].get(key)
            if body is None:
                body = schematic_payload_bytes(candidate, sheets=None if sheet is None else [sheet], index=index,
                                               read=entry["read"])
                entry["pages"][key] = body
                # A schematic's every page, with and without the index, is a few megabytes at most.
                while len(entry["pages"]) > 64:
                    entry["pages"].popitem(last=False)
        return body


SCHEMATICS = SchematicAnswers()


def schematic_payload_response(file_ref, *, sheet: str | None = None, index: bool = True,
                               answers: SchematicAnswers | None = None) -> tuple[int, bytes | dict]:
    """``(status, body)``: a schematic's plot payload's bytes at 200, or a JSON error dict. ``sheet`` (a
    sheet's path, ``/`` the root) plots that sheet's page alone, and ``index`` False leaves the index out;
    a sheet the hierarchy does not have is a 400 naming those it has. The hierarchy is read once per
    revision of its files (``SchematicAnswers``)."""
    candidate = resolve_plot_path(file_ref)
    if candidate is None:
        return 404, {"error": "Not found"}
    if not candidate.lower().endswith(".kicad_sch"):
        raise ValueError(f"a schematic's plot is a .kicad_sch's; {node_basename(candidate)} is not one")
    return 200, (answers or SCHEMATICS).payload(candidate, sheet, index)


class _Work:
    __slots__ = ("done", "status", "body", "refilled")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.status = 500
        self.body: Any = {"error": "the board's work stopped before it finished"}
        self.refilled = False


def _refs(found: dict[str, Any], board: Path) -> dict[str, Any]:
    """The DRC's items, each with the board reference it names (``ref``), where the board's index has one."""
    try:
        from cad import kicad_pcb

        index = kicad_pcb.read(board)
    except (OSError, ValueError):
        return found
    import re

    # A board's own items (a track, a via, a zone, a text, a graphic) by the uuid its file saved them with.
    names: dict[str, str] = {}
    for kind in ("tracks", "vias", "zones", "texts", "shapes", "dimensions"):
        for item in getattr(index, kind, ()) or ():
            ident, selector = getattr(item, "id", None), getattr(item, "selector", None)
            if ident and selector:
                names.setdefault(str(ident).lower().rsplit("/", 1)[-1], selector)
    parts = {part.ref for part in index.parts}
    for entry in (found.get("measurements") or {}).get("drc") or ():
        for item in entry.get("items") or ():
            ref = names.get(str(item.get("uuid") or "").lower())
            # A pad or a footprint by what KiCad calls it: "Pad 2 [GND] of R1 on F.Cu", "Footprint U3".
            said = str(item.get("description") or "")
            pad = re.match(r"(?:PTH |NPTH |SMD )?pad (\S+).*? of (\S+)", said, re.IGNORECASE)
            part = re.match(r"footprint (\S+)", said, re.IGNORECASE)
            if ref is None and pad and pad.group(2) in parts:
                ref = f"#{pad.group(2)}.{pad.group(1)}"
            elif ref is None and part and part.group(1) in parts:
                ref = f"#{part.group(1)}"
            if ref:
                item["ref"] = ref
    return found


class BoardAnswers:
    """The plot and DRC routes' work, off the request, and the answers they made (see the module)."""

    def __init__(self, *, hold_seconds: float = HOLD_SECONDS, retry_ms: int = 0, on_crash=None,
                 refill=None) -> None:
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self._on_crash = on_crash
        # ``refill`` stands in for KiCad's in a test; the engine's is ``boards.payload``'s.
        self._refill = refill
        self._lock = threading.Lock()
        self._work: dict[tuple[str, str], _Work] = {}
        self._held: OrderedDict[tuple[str, str], _Work] = OrderedDict()
        self._keys: dict[str, tuple[tuple[int, int, int], str]] = {}
        # The model names each board key's text writes (``models``): the last ``HELD``.
        self._names: OrderedDict[tuple[str, str], list[str]] = OrderedDict()

    def key(self, path: str) -> str:
        """The board's key (``poured.key``), worked out again when its stat changes."""
        from cad.engine.formats.kicad.poured import key

        stats = []
        for suffix in ("", ".kicad_pro", ".kicad_dru"):
            try:
                info = os.stat(path if not suffix else str(Path(path).with_suffix(suffix)))
                stats.append((info.st_ino, info.st_size, info.st_mtime_ns))
            except OSError:
                stats.append((0, -1, 0))
        stamp = tuple(stats)
        known = self._keys.get(path)
        if known is not None and known[0] == stamp:
            return known[1]
        found = key(path)
        self._keys[path] = (stamp, found)  # type: ignore[assignment]
        return found

    def response(self, product: str, file_ref, *, if_none_match: str = "") -> tuple[int, Any, str]:
        """``(status, body, key)``: the product's ``compressed.Coded`` at 200, 304 for the key the client
        named, 202 while it is made, or a JSON error dict."""
        candidate = resolve_plot_path(file_ref)
        if candidate is None:
            return 404, {"error": "Not found"}, ""
        if not candidate.lower().endswith(".kicad_pcb"):
            raise ValueError(f"a board's {product} is a .kicad_pcb's; {node_basename(candidate)} is not one")
        try:
            board_key = self.key(candidate)
        except OSError as error:
            return 400, {"error": f"{node_basename(candidate)} could not be read ({error}); "
                                  "check that it is a file this user may read"}, ""
        if if_none_match and if_none_match.strip() in (f'"{board_key}"', f'W/"{board_key}"'):
            return 304, b"", board_key
        slot = (product, board_key)
        with self._lock:
            work = self._held.get(slot)
            if work is not None:
                self._held.move_to_end(slot)
                return work.status, work.body, board_key
            work = self._work.get(slot)
            if work is None:
                work = self._work[slot] = _Work()
                threading.Thread(target=self._make, args=(work, slot, Path(candidate)), name=f"cad-board-{product}",
                                 daemon=True).start()
        if work.done.wait(self.hold_seconds):
            return work.status, work.body, board_key
        return 202, {"state": "plotting" if product == "plot" else "checking", "retryMs": self.retry_ms}, board_key

    def models(self, file_ref, remember) -> tuple[int, dict]:
        """``(status, body)``: the board's 3D models table (``GET .../models``), as the file is now.

        Each model a footprint names (``models3d.model_names``, read from the board's text once per board key and
        kept with its other answers) is answered as this computer has it NOW (``models3d.resolve_models``: only
        ``stat``, ``realpath`` and ``isfile``, inside the folders it allows, every request): ``{"file", "document",
        "api", "stamp"}`` for a STEP inside the board's folder, KiCad's 3D library or ``CAD_KICAD_3DMODELS`` --
        ``remember``-ed, so the engine's STEP routes serve its mesh by that id (that document's structure and
        catalog entry name its file, as every document's do), the table itself carrying no path -- else
        ``{"file", "missing": <reason>}``. Nothing is read but the board and nothing is written."""
        from cad.engine.formats.kicad.models3d import model_names, resolve_models

        from .kinds import document_api

        candidate = resolve_plot_path(file_ref)
        if candidate is None:
            return 404, {"error": "Not found"}
        if not candidate.lower().endswith(".kicad_pcb"):
            raise ValueError(f"a board's models are a .kicad_pcb's; {node_basename(candidate)} is not one")
        try:
            board_key = self.key(candidate)
            slot = ("models", board_key)
            with self._lock:
                names = self._names.get(slot)
                if names is not None:
                    self._names.move_to_end(slot)
            if names is None:
                with open(candidate, encoding="utf-8", errors="replace") as handle:
                    names = model_names(handle.read())
                with self._lock:
                    self._names[slot] = names
                    while len(self._names) > HELD:
                        self._names.popitem(last=False)
        except OSError as error:
            return 400, {"error": f"{node_basename(candidate)} could not be read ({error}); "
                                  "check that it is a file this user may read"}
        table: dict[str, dict] = {}
        for name, answer in resolve_models(candidate, names).items():
            if answer.path is None:
                table[name] = {"file": answer.file, "missing": answer.reason}
                continue
            ident = remember(answer.path)
            table[name] = {"file": os.path.basename(answer.path), "document": ident, "api": document_api("step", ident),
                           "stamp": answer.stamp}
        return 200, {"models": table}

    def _make(self, work: _Work, slot: tuple[str, str], board: Path) -> None:
        from cad.engine.formats.kicad import PlotError

        from .compressed import Coded

        product, board_key = slot
        keep = True
        try:
            if product == "plot":
                if self._refill is not None:
                    from cad.engine.formats.kicad.poured import payload

                    body, refilled = payload(board, refill=self._refill, board_key=board_key)
                else:
                    from cad_server._internal.boards import payload

                    body, refilled = payload(board, board_key)
                # A plot as saved is kept in memory alone (``poured`` keeps none on disk): the engine's next
                # start tries KiCad again.
                work.status, work.body, work.refilled = 200, Coded(body), refilled
            else:
                from cad_server._internal.boards import drc

                found = _refs(drc(board, board_key), board)
                work.status, work.body = 200, Coded(json.dumps(found, separators=(",", ":")).encode("utf-8"))
        except PlotError as error:
            work.status, work.body = 400, {"error": str(error)}
        except Exception as error:  # noqa: BLE001 - answered as the GET funnel answers a route's bug
            keep = False
            if self._on_crash is not None:
                self._on_crash(error)
            work.status, work.body = 400, {"error": str(error) or type(error).__name__}
        finally:
            with self._lock:
                self._work.pop(slot, None)
                if keep:
                    self._held[slot] = work
                    while len(self._held) > HELD:
                        self._held.popitem(last=False)
            work.done.set()
