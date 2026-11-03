"""The kicad integration's producers: a board script makes its ``kicad_pcb``, and the files stacked on it --
a ``step`` and a ``glb`` (the board and its parts in 3D) and a ``dxf`` (its outline and holes).

A board script is what ``@kicad_pcb`` makes of a function (``_session.BoardScript``); its matcher reads the
value's type name and module alone, importing nothing. Each producer here also DECLARES: it says what
the decorator does with the function it is stacked on (``declare``), since a board script runs in the
person's process through KiCad's IPC API, never in the engine's worker.
"""

from __future__ import annotations

from typing import Any

from cad.registry import Producer

__all__ = ["PRODUCERS", "declare_board", "declare_file", "is_board_script"]


def is_board_script(value: Any) -> bool:
    """Whether ``value`` is a ``@kicad_pcb`` board script, by its class's name and module."""
    cls = type(value)
    return cls.__name__ == "BoardScript" and cls.__module__ == "cad.kicad._session"


def declare_board(kind: str, out: Any, name: str | None) -> Any:
    from cad.kicad._session import declare

    return declare(out, name=name)


def declare_file(kind: str, out: Any, name: str | None) -> Any:
    """``@step``, ``@glb`` or ``@dxf`` stacked on a board script: a file written from its saved board."""
    if name is not None:
        raise TypeError(f"@{kind} on a board script takes no name=: the board names it")
    from cad.kicad._session import declare_output

    return lambda script: declare_output(kind, script, out)


_BOARD = ("board outline", "layers", "footprints", "pads", "nets", "tracks", "vias", "zones", "design rules")

PRODUCERS: tuple[Producer, ...] = (
    Producer("kicad_pcb", "kicad", "a function editing the open board through KiCad's IPC API (kipy)",
             lambda value: callable(value) and not is_board_script(value), "cad.kicad._session.run", _BOARD,
             declare="cad.kicad._producers.declare_board"),
    Producer("step", "kicad", "a @kicad_pcb board script's saved board", is_board_script,
             "cad.kicad._session.write_step", ("geometry", "assembly", "names", "colours"),
             decorates=is_board_script, declare="cad.kicad._producers.declare_file"),
    Producer("glb", "kicad", "a @kicad_pcb board script's saved board", is_board_script,
             "cad.kicad._session.write_glb", ("triangles", "assembly", "names", "colours"),
             decorates=is_board_script, declare="cad.kicad._producers.declare_file"),
    Producer("dxf", "kicad", "a @kicad_pcb board script's saved board: its outline and holes", is_board_script,
             "cad.kicad._session.write_dxf", ("2D geometry",),
             decorates=is_board_script, declare="cad.kicad._producers.declare_file"),
)
