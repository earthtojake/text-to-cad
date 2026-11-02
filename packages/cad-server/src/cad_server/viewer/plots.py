"""``GET /api/v1/documents/kicad_pcb/<id>/plot``: a KiCad board drawn from its file, as geometry per layer.

A ``.kicad_pcb`` is read by the library's board reader (:mod:`cad.engine.formats.kicad.plot`): no
KiCad runs, and each request reads the current file without a parsed-board cache. This module is
the route's two decisions -- what may be opened, and what the HTTP answer is. The reader is imported
only when a board is drawn, so nothing KiCad-related loads at ``cad_server.viewer`` import time.

The board is the document's file, by its absolute path (``http_app`` resolves the id): a path that
is not absolute, or not a ``.kicad_pcb``, is 400, a missing file 404. A file that is not a readable
board is 400 with the reason (``PlotError``, a ``ValueError`` the API's funnel answers).
"""

from __future__ import annotations

import os

from cad.engine.formats.kicad import PLOT_SUFFIXES

from .backend import absolute_path
from .scanner import node_basename

__all__ = ["PLOT_SUFFIXES", "plot_payload_response", "resolve_plot_path"]


def resolve_plot_path(file_ref) -> str | None:
    """The absolute ``.kicad_pcb`` this ref names, or ``None`` for a 404.

    Raises ``ValueError`` for a ref this route will not take.
    """
    if not file_ref:
        raise ValueError("a board's plot is read from the absolute path of a .kicad_pcb")
    candidate = absolute_path(file_ref)
    if not candidate.lower().endswith(PLOT_SUFFIXES):
        raise ValueError(f"a plot is a KiCad board's; {node_basename(candidate)} is not a .kicad_pcb file")
    return candidate if os.path.isfile(candidate) else None


def plot_payload_response(file_ref) -> tuple[int, bytes | dict]:
    """``(status, body)``: the plot payload's bytes at 200, or a JSON error dict."""
    candidate = resolve_plot_path(file_ref)
    if candidate is None:
        return 404, {"error": "Not found"}
    from cad.engine.formats.kicad.plot import plot_payload_bytes

    return 200, plot_payload_bytes(candidate)
