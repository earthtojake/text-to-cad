"""The public ``pcb`` namespace: a saved KiCad board read as what a person can point at.

A ``.kicad_pcb`` is an AUTHORED file, edited in KiCad or as text, never a document the engine
builds: this namespace reads it and nothing else. :func:`read_board` parses the file and the
``.kicad_pro`` beside it with the standard library (:mod:`cad.engine.formats.kicad`), so a check
script run with ``cad run`` imports it without the CAD kernel and without KiCad; :func:`inside` is the
even-odd test a check measures a pour or an outline with, in the same millimetres.

KiCad's own design rule check is the server's, a command: ``cad pcb drc BOARD [--json]``. It finds
and runs ``kicad-cli``, which a model's environment never does. ``cad snapshot`` draws a board.
"""

from __future__ import annotations

from cad.engine.formats.kicad.board_index import read_board
from cad.engine.formats.kicad.geometry import inside

__all__ = ["inside", "read_board"]
