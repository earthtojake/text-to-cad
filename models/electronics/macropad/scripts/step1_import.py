"""Layout step 1: the schematic's parts and nets onto the board (the board is made, with its project,
when it is not there yet). Run: cad run scripts/step1_import.py   (from the project folder)"""
import os
from pathlib import Path

from cad import kicad_pcb, kicad_sch

PROJ = Path(__file__).resolve().parent.parent
os.chdir(PROJ)
SCH, BOARD = "macropad.kicad_sch", "macropad.kicad_pcb"

(netlist,) = kicad_sch.export(SCH, "netlist", "tmp/netlist").written
with kicad_pcb.edit(BOARD) as b:
    dry = b.import_netlist(str(Path(netlist).resolve()), dry_run=True)
    print("dry run:", dry.report[:3000])
    result = b.import_netlist(str(Path(netlist).resolve()))
    print("errors", result.error_count, "warnings", result.warning_count, "new", result.new_footprint_count)
board = kicad_pcb.read(BOARD)
print(len(board.parts), "parts,", len(board.nets), "nets")
