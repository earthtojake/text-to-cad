"""A board drawn from its file: the plot payload's contract.

The CAD Viewer's ``GET /__cad/plot`` and ``cadgen pcb snapshot`` both draw a
``.kicad_pcb`` through :func:`plot_payload_bytes`, which reads the file with
:mod:`cadgen.engine.formats.kicad.board_index` and answers geometry per layer
(:mod:`cadgen.engine.formats.kicad.plot`). No KiCad process runs: the file is KiCad's own
format, and everything the picture needs is in it, the filled copper included.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PLOT_SCHEMA_VERSION", "PLOT_SUFFIXES", "PlotError", "plot_payload_bytes"]

from cadgen.engine.formats.kicad import PLOT_SCHEMA_VERSION, PLOT_SUFFIXES, PlotError


def plot_payload_bytes(path: Path | str) -> bytes:
    """The plot payload of the board at ``path`` as JSON bytes."""
    from cadgen.engine.formats.kicad.plot import plot_payload_bytes as build

    return build(Path(path))
