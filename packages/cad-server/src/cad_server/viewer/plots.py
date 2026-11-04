"""``GET /api/v1/documents/kicad_pcb/<id>/plot`` and ``.../drc``: a KiCad board drawn as geometry per layer,
and KiCad's design rule check of it, each kept by the board's bytes.
``GET /api/v1/documents/kicad_sch/<id>/plot``: a KiCad schematic, its hierarchy read from its files, every
sheet a page of layers (:mod:`cad.engine.formats.kicad.schematic_plot`), read again on each request; with
``?sheet=/Power/`` that sheet's page alone, and with ``index=0`` without the hierarchy's index (the viewer
reads the sheet on screen, the index with the first).

The board is the document's file, by its absolute path (``http_app`` resolves the id): a path that is not
absolute, or not a ``.kicad_pcb``, is 400, a missing file 404. A file that is not a readable board is 400
with the reason (``PlotError``).

* ``plot``: the payload (``cad.engine.formats.kicad.poured.payload``) with the pours KiCad refills on a
  copy (``cad_server._internal.boards.refill``: kicode, in the environment of ``cad[kicad]``); without
  KiCad, or when the refill fails, the board as saved, the payload's ``pours`` saying so.
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
from collections import OrderedDict
from pathlib import Path
from typing import Any

from cad.engine.formats.kicad import PLOT_SUFFIXES

from .backend import absolute_path
from .scanner import node_basename

__all__ = ["HOLD_SECONDS", "HELD", "BoardAnswers", "PLOT_SUFFIXES", "resolve_plot_path", "schematic_payload_response"]

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


def schematic_payload_response(file_ref, *, sheet: str | None = None, index: bool = True) -> tuple[int, bytes | dict]:
    """``(status, body)``: a schematic's plot payload's bytes at 200, or a JSON error dict. ``sheet`` (a
    sheet's path, ``/`` the root) plots that sheet's page alone, and ``index`` False leaves the index out;
    a sheet the hierarchy does not have is a 400 naming those it has."""
    candidate = resolve_plot_path(file_ref)
    if candidate is None:
        return 404, {"error": "Not found"}
    if not candidate.lower().endswith(".kicad_sch"):
        raise ValueError(f"a schematic's plot is a .kicad_sch's; {node_basename(candidate)} is not one")
    from cad.engine.formats.kicad.schematic_plot import schematic_payload_bytes

    return 200, schematic_payload_bytes(candidate, sheets=None if sheet is None else [sheet], index=index)


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
