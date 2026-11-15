"""Step 1 of the layout: the schematic's netlist onto the board (a new board is made by KiCad, with its
project). Run: cad run scripts/board_01_import.py [--dry-run]"""

import sys
from pathlib import Path

from cad import kicad_pcb, kicad_sch

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp" / "netlist"
BOARD = ROOT / "twin_orbit.kicad_pcb"


def checked(result):
    """The import's result; where KiCad's report has errors (a footprint no library of the project's
    `fp-lib-table` holds, most often), its lines and a stop: the board is not saved without those parts."""
    if result.error_count:
        lines = [line for line in result.report.splitlines() if line.strip()]
        lines = [line for line in lines if "not found" in line or line.startswith(("Cannot", "Error"))] or lines
        print("\n".join(lines[:15] + ([f"... and {len(lines) - 15} more lines"] if len(lines) > 15 else [])))
        sys.exit(f"netlist import: {result.error_count} errors in KiCad's report (above); the board is not saved")
    return result


(netlist,) = kicad_sch.export(ROOT / "twin_orbit.kicad_sch", "netlist", TMP).written
with kicad_pcb.edit(BOARD) as b:
    result = checked(b.import_netlist(str(netlist), dry_run="--dry-run" in sys.argv))
    print(result.report)
    print("footprints now:", len(b.get_footprints()))
