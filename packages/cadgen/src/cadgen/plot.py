"""A document drawn by its own tool: the plot payload's contract, and which tool draws a file.

KiCad draws a board or a schematic (:mod:`cadgen.kicad.plot`), WireViz a wiring
harness (:mod:`cadgen.wireviz.plot`). Both answer the same payload --
``{schemaVersion, kind, unrouted, sheets: [{name, svg, width, height, background}]}``
-- and refuse what they cannot draw with :class:`PlotError`. The CAD Viewer's
``GET /__cad/plot`` and ``cadgen snapshot`` both draw through
:func:`plot_payload_bytes`, which imports a tool's builder only when its kind is drawn.
"""

from __future__ import annotations

from pathlib import Path

from cadgen.file_types import format_of

__all__ = ["PLOT_SCHEMA_VERSION", "PLOT_SUFFIXES", "PlotError", "plot_payload_bytes"]

PLOT_SCHEMA_VERSION = 2
#: Every document a plot draws: a KiCad board or schematic, a wiring harness.
PLOT_SUFFIXES = (".kicad_pcb", ".kicad_sch", ".harness.yml")


class PlotError(ValueError):
    """A document its tool could not plot, with the reason. A ``ValueError``: the
    viewer's GET funnel answers it as a 400 with this message."""


def plot_payload_bytes(path: Path | str) -> bytes:
    """The plot payload of the document at ``path`` as JSON bytes, drawn by its tool.

    A machine without the tool is a :class:`PlotError` that says how to get it."""
    if format_of(path) == "harness":
        from cadgen.wireviz.install import WirevizMissingError as missing
        from cadgen.wireviz.plot import plot_payload_bytes as build
    else:
        from cadgen.kicad.install import KicadMissingError as missing
        from cadgen.kicad.plot import plot_payload_bytes as build
    try:
        return build(path)
    except missing as error:
        raise PlotError(str(error)) from None
