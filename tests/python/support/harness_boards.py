"""Board scripts a harness test can read without KiCad.

A ``@pcb`` board on the tiny test library (``kicad_library``) whose two-pin
connector ``J1`` carries two named nets, in the order a test asks for. A
harness only reads a board's netlist (its build never writes the board), so the
outline is a stand-in that is never read.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

BOARD = textwrap.dedent(
    '''
    from cadgen import {imports}

    LIBRARY = {library!r}


    class _Outline:
        """Read only when the board itself is written; a harness never writes it."""


    {decorators}
    def {name}():
        board = pcb.Board(outline=_Outline(), libraries=[LIBRARY], title="{name}")
        first, second = board.net("{first}"), board.net("{second}")
        j1 = board.part("Test:R", footprint="Test:R_0603", ref="J1")
        load = board.part("Test:R", footprint="Test:R_0603")
        board.connect(first, j1[1], load[1])
        board.connect(second, j1[2], load[2])
        return board
    '''
)


def write_board(
    folder: Path, name: str, first: str, second: str, *, library: str, decorators: str = "@pcb", imports: str = "pcb"
) -> Path:
    """``folder/<name>.py``: a board whose ``J1`` carries ``first`` on pin 1 and ``second`` on pin 2."""
    path = Path(folder) / f"{name}.py"
    text = BOARD.format(name=name, first=first, second=second, library=library, decorators=decorators, imports=imports)
    path.write_text(text, encoding="utf-8")
    return path
