"""Layout step 1: the schematic's parts and nets onto the board (the board is made, with its project,
when it is not there yet). Run: cad run scripts/step1_import.py   (from the project folder)"""
import os
import sys
from pathlib import Path

from cad import kicad_pcb, kicad_sch

PROJ = Path(__file__).resolve().parent.parent
os.chdir(PROJ)
SCH, BOARD = "macropad.kicad_sch", "macropad.kicad_pcb"


def checked(result):
    """The import's result; where KiCad's report has errors (a footprint no library of the project's
    `fp-lib-table` holds, most often), its lines and a stop: the board is not saved without those parts."""
    if result.error_count:
        lines = [line for line in result.report.splitlines() if line.strip()]
        lines = [line for line in lines if "not found" in line or line.startswith(("Cannot", "Error"))] or lines
        print("\n".join(lines[:15] + ([f"... and {len(lines) - 15} more lines"] if len(lines) > 15 else [])))
        sys.exit(f"netlist import: {result.error_count} errors in KiCad's report (above); the board is not saved")
    return result


(netlist,) = kicad_sch.export(SCH, "netlist", "tmp/netlist").written
with kicad_pcb.edit(BOARD) as b:
    dry = checked(b.import_netlist(str(Path(netlist).resolve()), dry_run=True))
    print("dry run:", dry.report[:3000])
    result = checked(b.import_netlist(str(Path(netlist).resolve())))
    print("errors", result.error_count, "warnings", result.warning_count, "new", result.new_footprint_count)
board = kicad_pcb.read(BOARD)
print(len(board.parts), "parts,", len(board.nets), "nets")
