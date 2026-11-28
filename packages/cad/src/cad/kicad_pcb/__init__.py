"""``cad.kicad_pcb``: the KiCad PCB document type (``cad.registry``), a saved KiCad board.

A ``.kicad_pcb`` is an AUTHORED file, edited in KiCad, as text or in place by :func:`edit`, never a
document a model makes: the type has no decorator. Its functions take paths and our own board objects, so
they are the type's, not the ``kicad`` integration's (the signature rule):

* :func:`read` parses the file and the ``.kicad_pro`` beside it with the standard library
  (:mod:`cad.engine.formats.kicad`), so a check script run with ``cad run`` imports it without the
  CAD kernel and without KiCad; :func:`inside` is the even-odd test a check measures a pour or an
  outline with, in the same millimetres.
* :func:`edit` opens the saved board in KiCad's IPC API for a ``with`` block, the ``kicad`` integration's
  (``cad.kicad._session``): the block gets KiPy's open board, which is saved at its end when it was changed
  (made by KiCad when the file is not there yet) and not at all when the block raises.

The board in one look is ``cad.inspect`` (``cad inspect BOARD``), a still of it ``cad.snapshot``, KiCad's
fabrication, assembly and 3D outputs ``cad.export(board, dst, as_=...)`` (``cad export BOARD DST [--as KIND]``:
``board.step``, ``fab/gerbers/ --as gerbers``), and KiCad's design rule check ``cad.kicad.drc`` (``cad kicad drc
BOARD``): the last two run KiCad's own ``kicad-cli``, the ``kicad`` integration's (kicode, ``cad[kicad]``).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from typing import Any

__all__ = ["edit", "inside", "read"]

# The reader and the even-odd test load when first used: the formats package they live in imports
# numpy, and a command's help (``cad kicad drc --help``) is made from this module without it.
_LAZY = {"read": ("cad.engine.formats.kicad.board_index", "read_board"),
         "inside": ("cad.engine.formats.kicad.geometry", "inside")}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib

        module, attribute = _LAZY[name]
        value = getattr(importlib.import_module(module), attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


def edit(board: Path | str) -> AbstractContextManager[Any]:
    """The board at ``board`` open in KiCad, for a ``with`` block: ``with kicad_pcb.edit("board.kicad_pcb") as
    b:`` hands the block KiPy's open board (kicode's ``kicode.board.Board``), through kicode's headless
    ``kicad-cli api-server``. At the block's end the board is saved when it was changed (KiCad's own modified
    state), so a block that changes nothing leaves the file byte for byte; when the block raises, nothing is
    saved and the exception goes on. A board not there yet is made by KiCad, with its project, and saved. A
    ``kicad_sch.edit`` of the same project inside the block shares its KiCad. A saved board is checked for the
    nets KiCad moved (it gives copper the net of a pad it overlaps): each track, via, copper shape or zone saved
    on another net than the block gave it, else the file had, is a warning on stderr and, after the block, one
    of ``b.net_changes`` (``kind``, ``id``, ``ref``, ``was``, ``now``, ``pad``, ``joined``). Needs the kicad extra
    (``cad[kicad]``; ``cad run`` gives a script that calls it the extra)."""
    from cad.kicad._session import edit as editing

    return editing(board, "kicad_pcb")


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
