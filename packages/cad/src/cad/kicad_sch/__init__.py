"""``cad.kicad_sch``: the KiCad schematic document type (``cad.registry``), a saved KiCad schematic.

A ``.kicad_sch`` is an AUTHORED file, edited in KiCad or as text, never a document a model makes: the
type has no decorator. A schematic is a hierarchy: its project's root sheet (the ``<project>.kicad_sch``
beside the ``.kicad_pro``) and the sheets it places, each a file of its own. Its functions take paths
and plain values, so they are the type's, not the ``kicad`` integration's (the signature rule):

* :func:`read_schematic` reads the whole hierarchy from the root, whichever of its sheets it is given,
  with the standard library (:mod:`cad.engine.formats.kicad.schematic`), so a script run with ``cad
  run`` imports it without the CAD kernel and without KiCad: its sheets, symbols and their pins,
  wires, labels and the nets they make, and ``resolve(ref)`` for a reference in the board's grammar
  (``#U3``, ``#U3.7``, ``#net:VBUS``) and the schematic's own (``#sheet:/Power/``, ``#wire:<uuid>``).
* :func:`inspect` is the schematic in one look as plain data -- its sheets, parts and nets, and what a
  reference names -- what ``cad kicad_sch inspect`` prints; ``snapshot`` draws one sheet flat, as
  ``cad kicad_sch snapshot`` does.
* ``check`` (KiCad's electrical rules check) and ``export`` (a pdf, svgs, the netlist, a BOM) run
  KiCad's own ``kicad-cli``, which the server finds and runs and a model's environment never does:
  they are the commands ``cad kicad_sch check`` and ``cad kicad_sch export``, and as functions they say so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cad.engine.formats.kicad.schematic import read_schematic

__all__ = ["check", "export", "inspect", "read_schematic"]


def inspect(path: Path | str, ref: str | None = None) -> dict:
    """What the schematic at ``path`` holds, as plain data: ``file``, ``root``, ``format``, ``sheets``,
    ``parts``, ``nets`` and ``counts``; with ``ref``, ``resolved``: what that reference names
    (``cad kicad_sch inspect``)."""
    from cad.engine.formats.kicad.schematic_summary import inspect_schematic

    return inspect_schematic(path, ref)


def _runs_kicad(operation: str) -> RuntimeError:
    return RuntimeError(f"cad.kicad_sch.{operation} runs KiCad's kicad-cli, which the CAD server runs, not a model's "
                        f"process: run the command, cad kicad_sch {operation} SCHEMATIC (cad kicad_sch {operation} --help)")


def check(path: Path | str, *args: Any, **options: Any) -> Any:
    """KiCad's electrical rules check: the server's command, ``cad kicad_sch check SCHEMATIC``."""
    raise _runs_kicad("check")


def export(path: Path | str, *args: Any, **options: Any) -> Any:
    """KiCad's schematic outputs: the server's command, ``cad kicad_sch export SCHEMATIC --to KIND -o DIR``."""
    raise _runs_kicad("export")


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
