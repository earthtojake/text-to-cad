"""``GET /__cad/plot``: a KiCad board drawn from its file, as geometry per layer.

A ``.kicad_pcb`` is read by ``cadgen.plot`` (:mod:`cadgen.engine.formats.kicad.plot`): no
KiCad runs, and each request reads the current file without a parsed-board cache. This module is the route's two decisions -- what may be
opened, and what the HTTP answer is. ``cadgen.plot`` imports the board reader
only when a board is drawn, so nothing KiCad-related loads at ``cadgen.viewer``
import time.

The board is named by its absolute path, through the drawing route's helper: a
ref that is not an absolute path, or not a ``.kicad_pcb``, is 400, a missing file
404. A file that is not a readable board is 400 with the reason
(``PlotError``, a ``ValueError`` the GET funnel answers).
"""

from __future__ import annotations

from cadgen.plot import PLOT_SUFFIXES

from .drawings import resolve_drawing_path

__all__ = ["PLOT_ROUTE_PATH", "PLOT_SUFFIXES", "plot_payload_response"]

PLOT_ROUTE_PATH = "/__cad/plot"


def plot_payload_response(file_ref) -> tuple[int, bytes | dict]:
    """``(status, body)``: the plot payload's bytes at 200, or a JSON error dict."""
    candidate = resolve_drawing_path(file_ref, suffixes=PLOT_SUFFIXES, route=PLOT_ROUTE_PATH, noun="KiCad boards")
    if candidate is None:
        return 404, {"error": "Not found"}
    from cadgen.plot import plot_payload_bytes

    return 200, plot_payload_bytes(candidate)
