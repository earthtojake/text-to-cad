"""``cad.kicad_sch``: the KiCad schematic document type (``cad.registry``), a saved KiCad schematic.

A ``.kicad_sch`` is an AUTHORED file, edited in KiCad, as text or in place by :func:`edit`, never a
document a model makes: the type has no decorator. A schematic is a hierarchy: its project's root sheet
(the ``<project>.kicad_sch`` beside the ``.kicad_pro``) and the sheets it places, each a file of its own.
Its functions take paths and plain values, so they are the type's, not the ``kicad`` integration's (the
signature rule):

* :func:`read` reads the whole hierarchy from the root, whichever of its sheets it is given,
  with the standard library (:mod:`cad.engine.formats.kicad.schematic`), so a script run with ``cad
  run`` imports it without the CAD kernel and without KiCad: its sheets, symbols and their pins,
  wires, labels and the nets they make, and ``resolve(ref)`` for a reference in the board's grammar
  (``#U3``, ``#U3.7``, ``#net:VBUS``) and the schematic's own (``#sheet:/Power/``, ``#wire:<uuid>``).
* :func:`edit` opens the saved schematic in KiCad's IPC API for a ``with`` block, the ``kicad``
  integration's (``cad.kicad._session``): its project's symbol libraries loaded, saved at the block's end
  when it was changed and not at all when the block raises.

The schematic in one look, and what a reference names, is ``cad.inspect`` (``cad inspect SCHEMATIC [REF]``),
one sheet drawn flat ``cad.snapshot`` (``cad snapshot SCHEMATIC OUT.png --sheet /Power/``), KiCad's outputs of it
(a ``.pdf``, the ``.net`` netlist, a ``.csv`` BOM, its SVGs into a folder or a ``.zip``) ``cad.export(schematic,
dst)``, and KiCad's electrical rules check ``cad.kicad.erc`` (``cad kicad erc SCHEMATIC``): the last two run KiCad's
own ``kicad-cli``, the ``kicad`` integration's (kicode, ``cad[kicad]``), as the board's do.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from typing import Any

__all__ = ["edit", "read"]


def __getattr__(name: str) -> Any:
    # The reader loads when first used: the formats package it lives in imports numpy, and a command's
    # help (``cad kicad erc --help``) is made from this module without it.
    if name == "read":
        from cad.engine.formats.kicad.schematic import read_schematic

        globals()["read"] = read_schematic
        return read_schematic
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | {"read"})


def edit(schematic: Path | str) -> AbstractContextManager[Any]:
    """The schematic at ``schematic`` (its project's root sheet, or any sheet) open in KiCad, for a ``with``
    block: ``with kicad_sch.edit("design.kicad_sch") as s:`` hands the block KiPy's open schematic (kicode's
    ``kicode.schematic.Schematic``), through kicode's headless ``kicad-cli api-server``, its project's symbol
    libraries (its own ``sym-lib-table``) loaded first; a placement from a library the project does not list
    is refused in one line naming it. At the block's end the schematic is saved when it was changed, so a
    block that changes nothing leaves the file byte for byte; when the block raises, nothing is saved and the
    exception goes on. A schematic not there yet is made by KiCad, with its project, and saved. A
    ``kicad_pcb.edit`` of the same project inside the block shares its KiCad. Needs the kicad extra
    (``cad[kicad]``; ``cad run`` gives a script that calls it the extra)."""
    from cad.kicad._session import edit as editing

    return editing(schematic, "kicad_sch")


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
