"""``cad.kicad``: the kicad integration -- our code for KiCad: kicad-cli and its IPC API, both kicode's.

KiCad's command line, ``kicad-cli``, is an external program our code runs (kind C), with a separate
process; its extra, ``cad[kicad]``, is kicode, which carries that program and KiPy, the IPC API's Python
client (as ``kicode``), one KiCad nightly's build of both. A person's own KiCad is never run. What is here:

* ``_program``: ``kicad-cli`` found and run, by the library's one helper for external programs
  (``cad._internal.programs``): ``CAD_KICAD_CLI``, refused unless it names a ``kicad-cli``, then
  kicode's; only ``kicad-cli`` itself is ever run, headless, in private homes (``kicode.environment``).
* ``_command``: ``cad run kicad-cli ARGS`` -- KiCad's own command line, the environment's (kicode's console
  script), headless in a private folder, its exit code kicad-cli's.
* ``_session``: what ``kicad_pcb.edit`` and ``kicad_sch.edit`` run, a ``with`` block -- a private
  ``kicad-cli api-server`` on the file (KiCad makes one not there yet), one per project, which the board's
  and the schematic's edits share; KiPy connected to it, the open document handed over (a schematic's
  project symbol libraries loaded first), saved at the block's end when it was changed and not when the
  block raises, the server stopped and its folder removed; ``_drift``, the board's check at the save of the
  nets KiCad moved onto a pad's.
* ``drc`` and ``erc``: KiCad's own checks, its design rule check of a board (``_check``) and its electrical
  rules check of a schematic (``_schematic``), the integration's operations on its tool's files: ``cad kicad
  drc BOARD`` and ``cad kicad erc SCHEMATIC``, one to one.
* ``_export``: the board's fabrication, assembly and 3D outputs by ``kicad-cli`` (``EXPORTS``: gerbers,
  drill, pos, bom, step, glb, odb, ipc2581, pdf, dxf), each into a folder as KiCad names its files.
* ``_schematic``: a schematic's electrical rules check and its outputs (``EXPORTS``: pdf, svg, netlist,
  bom) by ``kicad-cli``, from its project's root sheet (``erc``).
* ``_destination``: where ``cad.export(file, dst, as_=KIND)`` and ``cad export FILE DST [--as KIND]`` put
  either's: DST a file by its suffix, a folder or a ``.zip``, checked before KiCad runs, and the files KiCad
  wrote put there.
* ``route`` (``_route``, its search in ``_routing``): copper for the connections an agent names, in the order
  it names them, written into the board a ``kicad_pcb.edit`` block has open: KiPy's board in, the copper out
  through it, every rule the board's own; it answers a ``Routed``.

The board readers are the document type's (``cad.kicad_pcb``), our own code for the file format: viewing,
reading and drawing a board need no KiCad. Importing this package starts nothing and imports no kicode.
"""

from __future__ import annotations

from pathlib import Path

from cad.kicad._route import Routed, route
from cad.results import CheckResult

__all__ = ["Routed", "drc", "erc", "route"]


def _taken(path: Path | str, suffix: str, check: str) -> Path:
    """``path`` as a check takes it, after refusing a file of another kind by name before anything runs."""
    given = Path(path)
    if given.suffix.lower() != suffix:
        raise ValueError(f"cad.kicad.{check} checks a {suffix} file, not {str(path)!r}"
                         + ("; a schematic's check is cad.kicad.erc" if given.suffix.lower() == ".kicad_sch" else
                            "; a board's check is cad.kicad.drc" if given.suffix.lower() == ".kicad_pcb" else ""))
    return given


def drc(board: Path) -> CheckResult:
    """Check the KiCad board BOARD with KiCad's design rule check.

    Runs ``kicad-cli pcb drc`` on the saved file with every severity reported
    and lists each violation and unconnected item with where it is (millimetres
    from the board's origin). The board fails when any error-severity violation
    or any unconnected item exists; warnings are reported and do not fail it.
    The result's ``measurements["drc"]`` is every finding as KiCad reported it,
    each item with its uuid and position.

    board: the .kicad_pcb to check (its .kicad_pro beside it carries the rules).
    """
    from cad.kicad._check import check

    return check(_taken(board, ".kicad_pcb", "drc"))


def erc(schematic: Path) -> CheckResult:
    """Check the KiCad schematic SCHEMATIC with KiCad's electrical rules check.

    Runs ``kicad-cli sch erc`` on the saved hierarchy (from its project's root sheet) with every
    severity reported, and lists each violation with its sheet and where it is (millimetres on that
    sheet's page). Beside KiCad's, a warning for every pin joined some other way besides, and every wire's
    end, that lies on a wire's span with no junction there (``pin_on_wire_span``, ``wire_end_on_wire_span``):
    KiCad joins them and its ERC passes. A pin whose one connection is a wire's span is KiCad's own straight
    run through a pin (it saves a rail drawn to each pin as one wire across them), not a finding. The schematic
    fails when any error-severity violation exists; warnings are reported and do not fail it.

    schematic: the .kicad_sch to check (any sheet of its project: the check reads the whole hierarchy).
    """
    from cad.kicad._schematic import check

    return check(_taken(schematic, ".kicad_sch", "erc"))
