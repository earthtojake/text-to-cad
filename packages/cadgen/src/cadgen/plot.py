"""A board drawn from its file: the plot payload's contract.

The CAD Viewer's ``GET /__cad/plot`` and ``cadgen pcb snapshot`` both draw a
``.kicad_pcb`` through :func:`plot_payload_bytes`, which reads the file with
:mod:`cadgen.kicad.board_index` and answers geometry per layer
(:mod:`cadgen.kicad.plot`). No KiCad process runs: the file is KiCad's own
format, and everything the picture needs is in it, the filled copper included.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PLOT_SCHEMA_VERSION", "PLOT_SUFFIXES", "PlotError", "plot_payload_bytes"]

PLOT_SCHEMA_VERSION = 3
#: Every document a plot draws.
PLOT_SUFFIXES = (".kicad_pcb",)


class PlotError(ValueError):
    """A document that could not be plotted, with the reason. A ``ValueError``: the
    viewer's GET funnel answers it as a 400 with this message."""


def plot_payload_bytes(path: Path | str) -> bytes:
    """The plot payload of the board at ``path`` as JSON bytes."""
    from cadgen.kicad.plot import plot_payload_bytes as build

    return build(Path(path))
