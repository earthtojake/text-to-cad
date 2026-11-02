"""The public ``pcb`` namespace: a saved KiCad board read as what a person can point at.

A ``.kicad_pcb`` is an AUTHORED file, edited in KiCad or as text, never a document the engine
builds: this namespace reads it and nothing else. :func:`read_board` parses the file and the
``.kicad_pro`` beside it with the standard library alone (:mod:`cad.engine.formats.kicad`), so a
script run with ``cad run`` imports it without the CAD kernel and without KiCad. KiCad's own design
rule check is a command, ``cad pcb drc``; ``cad snapshot`` draws a board.
"""

from __future__ import annotations

from cad.engine.formats.kicad.board_index import read_board

__all__ = ["read_board"]
