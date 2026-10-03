"""``GET /__cad/plot``: a document drawn by its own tool, as SVG sheets.

A KiCad board or schematic is drawn by KiCad (``cadgen.kicad.plot``); a wiring
harness (``.harness.yml``) by WireViz (``cadgen.wireviz.plot``). This module
is the route's two decisions -- what may be opened, and what the HTTP answer
is. The payload builders are imported inside the handler so nothing KiCad- or
WireViz-related loads at ``cadgen.viewer`` import time; a cached plot never
runs ``kicad-cli`` or ``wireviz`` at all.

Path resolution is the containment rule the drawing route applies, through the
same helper: a ``..`` walk and an absolute path outside the root are 403, a
hidden component or a missing file 404. A ref that is none of the plotted
suffixes is 400, checked before containment. A document its tool cannot plot,
or a machine without the tool, is 400 with the teaching message.
"""

from __future__ import annotations

from .drawings import resolve_drawing_path

__all__ = ["PLOT_ROUTE_PATH", "PLOT_SUFFIXES", "plot_payload_response"]

PLOT_ROUTE_PATH = "/__cad/plot"
_HARNESS_SUFFIX = ".harness.yml"
PLOT_SUFFIXES = (".kicad_pcb", ".kicad_sch", _HARNESS_SUFFIX)


def plot_payload_response(root_path: str, file_ref, *, lazy: bool = False) -> tuple[int, bytes | dict]:
    """``(status, body)``: the plot payload's bytes at 200, or a JSON error dict."""
    candidate = resolve_drawing_path(
        root_path, file_ref, lazy=lazy, suffixes=PLOT_SUFFIXES, route=PLOT_ROUTE_PATH,
        noun="KiCad boards and schematics and wiring harnesses",
    )
    if candidate is None:
        return 404, {"error": "Not found"}
    from cadgen.kicad.plot import PlotError

    if candidate.lower().endswith(_HARNESS_SUFFIX):
        from cadgen.wireviz.install import WirevizMissingError
        from cadgen.wireviz.plot import plot_payload_bytes as harness_payload_bytes

        try:
            return 200, harness_payload_bytes(candidate)
        except WirevizMissingError as error:
            raise PlotError(str(error)) from None
    from cadgen.kicad.install import KicadMissingError
    from cadgen.kicad.plot import plot_payload_bytes

    try:
        return 200, plot_payload_bytes(candidate)
    except KicadMissingError as error:
        raise PlotError(str(error)) from None
