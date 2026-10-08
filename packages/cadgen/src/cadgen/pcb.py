"""The public ``pcb`` namespace: the ``@pcb`` decorator, the board API, and its verbs.

``@pcb`` DECLARES a printed circuit board model (``@pcb(gerber=True, bom=True,
pos=True)`` with its manufacturing files); ``pcb.Board`` is what its function
builds and returns; ``pcb.validate(...)`` checks any KiCad project, and
``pcb.gerber``/``pcb.bom``/``pcb.pos`` write a saved board's manufacturing files.
They are the same object -- this module is callable (see
:mod:`cadgen._internal.format_namespace`) -- so ``from cadgen import pcb``
gives a model script all three.

A board is written as a KiCad project: ``<name>.kicad_pro``,
``<name>.kicad_sch``, ``<name>.kicad_pcb`` and its custom design rules,
``<name>.kicad_dru``. KiCad itself (its command line, ``kicad-cli``) fills the
zones and runs the electrical and design rule checks inside every build; a
build with errors writes nothing.

``pcb.Testbench`` simulates a board's subcircuits with ngspice, the simulator
KiCad ships: a circuit like a board, built by the same functions, whose runs
are facts for a script to assert (``pcb.SimulationError`` when ngspice cannot
solve it).

``pcb.read_board(path)`` reads any KiCad board back for the references a
person copies from the viewer (``#U3``, ``#U3.9``, ``#net:VIN``,
``#net:VIN@x40.1y21.6``, ``#@x40.1y21.6``): ``.resolve(ref)`` answers what one
names, in the script's coordinates, and a part's ``script`` is the line that
made it (:mod:`cadgen.kicad.board_index`). ``pcb.read_schematic(path)`` answers
the same references on a schematic (``#U3``, ``#U3.9``, ``#net:VIN``), sheets
within sheets included: a part with the units it draws on each sheet, a pin, a
net by KiCad's own name, from one run of KiCad's netlist export
(:mod:`cadgen.kicad.schematic_index`).

Import discipline: nothing here pulls in OCP or touches KiCad at module scope.
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import plot_snapshot_verb
from cadgen.results import FabExportResult, ValidationResult

__all__ = [
    "AISLER",
    "Board",
    "DesignError",
    "EUROCIRCUITS",
    "FABS",
    "Fab",
    "JLCPCB",
    "NEXTPCB",
    "Net",
    "NetClass",
    "OSHPARK",
    "PCBWAY",
    "Part",
    "Pin",
    "Rules",
    "SEEED_FUSION",
    "SimulationError",
    "Testbench",
    "bom",
    "find_footprints",
    "find_symbols",
    "gerber",
    "pos",
    "read_board",
    "read_schematic",
    "snapshot",
    "validate",
]

_DESIGN = {"Board", "DesignError", "Net", "NetClass", "Part", "Pin", "Rules"}
_FABS = {"AISLER", "EUROCIRCUITS", "FABS", "Fab", "JLCPCB", "NEXTPCB", "OSHPARK", "PCBWAY", "SEEED_FUSION"}
_SIMULATION = {"SimulationError", "Testbench"}

_SUFFIXES = (".kicad_pcb", ".kicad_sch", ".kicad_pro")

#: ``cadgen pcb snapshot``'s verb: a board or schematic drawn as KiCad plots it, as the viewer draws it.
snapshot = plot_snapshot_verb("pcb")


def validate(path: Path, *, strict: bool = False, verbose: bool = False) -> ValidationResult:
    """Check one KiCad project with KiCad's own ERC and DRC.

    The project's files are copied aside first, so checking never writes into
    the project. The DRC refills zones and, when the project has a schematic,
    compares it with the board. Unrouted connections are reported; they block
    like any other error. Positions are millimetres from the board's
    drill/place origin, y up.

    path: the project's .kicad_pcb, .kicad_sch or .kicad_pro.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    import sys

    from cadgen._internal.validation_door import display_path, failed, resolved_target
    from cadgen.results import ValidationIssue

    target = resolved_target(path, label="pcb")
    if verbose:
        print(f"[pcb] validating {target}", file=sys.stderr)
    if target.suffix.lower() not in _SUFFIXES:
        return failed(target, "target must be a KiCad project file (.kicad_pcb, .kicad_sch or .kicad_pro)")
    if not target.is_file():
        return failed(target, "file not found")
    from cadgen.kicad.check import check_project
    from cadgen.kicad.install import KicadMissingError

    try:
        report = check_project(target)
    except KicadMissingError as error:
        return failed(target, str(error), code="kicad_missing")
    issues = []
    for finding in sorted(report.findings, key=lambda finding: (finding.severity != "error", finding.check, finding.type)):
        located = [text + (f" at ({position[0]:g}, {position[1]:g})" if position is not None else "") for text, position in finding.items]
        issues.append(
            ValidationIssue(
                severity=finding.severity,
                message=(finding.summary or finding.description) + (": " + "; ".join(located) if located else ""),
                code=f"{finding.check}.{finding.type}",
            )
        )
    errors = sum(1 for finding in report.findings if finding.severity == "error" and finding.check != "review")
    warnings = sum(1 for finding in report.findings if finding.severity == "warning")
    advice = sum(1 for finding in report.findings if finding.severity == "warning" and finding.check == "review")
    blocking = bool(errors or (strict and warnings > advice))  # the review advises; strict never fails on it
    return ValidationResult(
        ok=not blocking,
        path=target,
        issues=tuple(issues),
        summary="" if blocking else f"OK {display_path(target)}: ERC and DRC clean ({warnings} warning(s))",
    )


def gerber(board: Path, out: Path | None = None, *, verbose: bool = False) -> FabExportResult:
    """Write the Gerber and drill files of the KiCad board BOARD, in one zip: what a fab makes it from.

    Every copper, mask, paste and silkscreen layer and the outline, as Gerber X2,
    and the Excellon drill files, plated and unplated apart: the files every PCB
    fab takes. What @pcb(gerber=True) writes. Refused for a board with unrouted
    connections or DRC errors.

    board: the .kicad_pcb to export.
    out: destination file. Omitted, writes the sibling <name>.gerbers.zip beside BOARD.
    verbose: narrate the target on stderr.
    """
    from cadgen._internal.fab_door import board_export

    return board_export("gerber", board, out, verbose=verbose)


def bom(board: Path, out: Path | None = None, *, verbose: bool = False) -> FabExportResult:
    """Write the bill of materials (CSV) of the KiCad board BOARD: what to buy, and what an assembler places.

    One row per distinct part, read from the schematic beside the board; parts
    marked do-not-populate are left out. What @pcb(bom=True) writes.

    board: the .kicad_pcb to export (its .kicad_sch beside it).
    out: destination file. Omitted, writes the sibling <name>.bom.csv beside BOARD.
    verbose: narrate the target on stderr.
    """
    from cadgen._internal.fab_door import board_export

    return board_export("bom", board, out, verbose=verbose)


def pos(board: Path, out: Path | None = None, *, verbose: bool = False) -> FabExportResult:
    """Write the pick-and-place file (CSV) of the KiCad board BOARD: where an assembler puts each part.

    One row per placed part: its reference, position (millimetres from the
    board's drill/place origin), rotation and side; do-not-populate parts are
    left out. What @pcb(pos=True) writes. Refused for a board with unrouted
    connections or DRC errors.

    board: the .kicad_pcb to export.
    out: destination file. Omitted, writes the sibling <name>.pos.csv beside BOARD.
    verbose: narrate the target on stderr.
    """
    from cadgen._internal.fab_door import board_export

    return board_export("pos", board, out, verbose=verbose)


def __getattr__(name: str):
    if name in _DESIGN:
        from cadgen.kicad import design

        return getattr(design, name)
    if name in _FABS:
        from cadgen.kicad import fabs

        return getattr(fabs, name)
    if name in _SIMULATION:
        from cadgen.kicad import sim

        return getattr(sim, name)
    if name in {"find_symbols", "find_footprints"}:
        from cadgen.kicad import library

        return getattr(library, name)
    if name in {"read_board", "BoardView"}:
        from cadgen.kicad import board_index

        return getattr(board_index, name)
    if name in {"read_schematic", "SchematicView"}:
        from cadgen.kicad import schematic_index

        return getattr(schematic_index, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


callable_namespace(__name__, "pcb")
