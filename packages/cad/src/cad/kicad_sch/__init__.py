"""``cad.kicad_sch``: the KiCad schematic document type (``cad.registry``), a saved KiCad schematic.

A ``.kicad_sch`` is an AUTHORED file, edited in KiCad or as text, never a document a model makes: the
type has no decorator. A schematic is a hierarchy: its project's root sheet (the ``<project>.kicad_sch``
beside the ``.kicad_pro``) and the sheets it places, each a file of its own. Its functions take paths
and plain values, so they are the type's, not the ``kicad`` integration's (the signature rule):

* :func:`read` reads the whole hierarchy from the root, whichever of its sheets it is given,
  with the standard library (:mod:`cad.engine.formats.kicad.schematic`), so a script run with ``cad
  run`` imports it without the CAD kernel and without KiCad: its sheets, symbols and their pins,
  wires, labels and the nets they make, and ``resolve(ref)`` for a reference in the board's grammar
  (``#U3``, ``#U3.7``, ``#net:VBUS``) and the schematic's own (``#sheet:/Power/``, ``#wire:<uuid>``).
* :func:`inspect` is the schematic in one look as plain data -- its sheets, parts and nets, and what a
  reference names -- what ``cad kicad_sch inspect`` prints; ``snapshot`` draws one sheet flat, as
  ``cad kicad_sch snapshot`` does.
* :func:`erc` (KiCad's electrical rules check) and :func:`export` (a pdf, svgs, the netlist, a BOM) run
  KiCad's own ``kicad-cli``, the ``kicad`` integration's (kicode, ``cad[kicad]``), as the board's do: they
  are the commands ``cad kicad_sch erc`` and ``cad kicad_sch export``, one to one. Where this environment
  lacks kicode, the command runs them in the environment of ``cad[kicad]`` the engine makes on first need;
  a function called here says to install the extra (or run the script with ``cad run``, which does).
"""

from __future__ import annotations

from pathlib import Path

from cad.engine.formats.kicad.schematic import read_schematic as read
from cad.results import CheckResult, ExportResult

__all__ = ["erc", "export", "inspect", "read"]


def inspect(path: Path | str, ref: str | None = None) -> dict:
    """What the schematic at ``path`` holds, as plain data: ``file``, ``root``, ``format``, ``sheets``,
    ``parts``, ``nets`` and ``counts``; with ``ref``, ``resolved``: what that reference names
    (``cad kicad_sch inspect``)."""
    from cad.engine.formats.kicad.schematic_summary import inspect_schematic

    return inspect_schematic(path, ref)


def erc(schematic: Path) -> CheckResult:
    """Check the KiCad schematic SCHEMATIC with KiCad's electrical rules check.

    Runs ``kicad-cli sch erc`` on the saved hierarchy (from its project's root sheet) with every
    severity reported, and lists each violation with its sheet and where it is (millimetres on that
    sheet's page). The schematic fails when any error-severity violation exists; warnings are reported
    and do not fail it.

    schematic: the .kicad_sch to check (any sheet of its project: the check reads the whole hierarchy).
    """
    from cad.kicad._schematic import check

    return check(Path(schematic))


def export(schematic: Path | str, to: str, out: Path | str) -> ExportResult:
    """KiCad's ``to`` export of the saved ``schematic``'s hierarchy into the folder ``out`` (``cad kicad_sch
    export SCHEMATIC --to KIND -o DIR``): ``to`` is one of ``pdf`` (every sheet), ``svg`` (one a sheet),
    ``netlist`` (the one a board imports) and ``bom``. The result says the files written. ``RuntimeError``
    in KiCad's words when it fails."""
    from cad.kicad._schematic import export as run

    source = Path(schematic).expanduser()
    written = run(source, str(to), Path(out).expanduser())
    return ExportResult(path=source.resolve(), to=str(to), written=tuple(written), warnings=())


from cad._internal.document_type import bind as _bind  # noqa: E402

_bind(__name__)
