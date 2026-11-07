"""Step 1 of the layout: the schematic's netlist onto the board (a new board is made by KiCad, with its
project). Run: cad run scripts/board_01_import.py [--dry-run]"""

import sys
from pathlib import Path

from cad import kicad_pcb, kicad_sch

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp" / "netlist"
BOARD = ROOT / "twin_orbit.kicad_pcb"

(netlist,) = kicad_sch.export(ROOT / "twin_orbit.kicad_sch", "netlist", TMP).written
with kicad_pcb.edit(BOARD) as b:
    result = b.import_netlist(str(netlist), dry_run="--dry-run" in sys.argv)
    print(result.report if hasattr(result, "report") else result)
    print("footprints now:", len(b.get_footprints()))
