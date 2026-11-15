"""Builds SHORT CIRCUIT's playfield KiCad project from the design model and its scripts: the project libraries and
their tables, the seven schematic sheets, then the board from nothing: setup (with the project file and the custom
rules), place, art, the routes planned (`scripts/routes.py`, the longest step), then route, zones, silk and finish.

    cad run build.py

The KiCad files are build output (`.gitignore` keeps them out of Git): run this before opening the board or the
schematic in the CAD Viewer or in KiCad, and before any script that reads the board (`check_board.py`,
`check_fit.py`). It needs the `cad` command (KiCad 10.99's kicad-cli and API come with it) and KiCad's stock
libraries, which `build_libraries.py` reads in an installed KiCad or beside the `3dmodels` folder
`CAD_KICAD_3DMODELS` names (`scripts/stock.py`; README.md, Rebuild): without them it stops before the first step,
saying so. The board is made again each time (the old one removed first), so a build is the same from a clean
checkout and over an earlier build.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts"))
import stock  # noqa: E402

STEPS = (
    ("scripts/build_libraries.py",),                                   # pinball.kicad_sym, power.kicad_sym, pinball.pretty, tables
    ("scripts/schematic.py",),                                         # the root and six sheets, as text
    ("scripts/board.py", "setup", "place", "art"),                     # the board, its project and rules, parts, art
    ("scripts/routes.py",),                                            # tmp/routes.json: the plan (about ten minutes)
    ("scripts/board.py", "route", "zones", "silk", "finish"),         # tracks and vias, the pours (filled), legends, stackup
)


def main() -> None:
    cad = shutil.which("cad")
    if cad is None:
        sys.exit("build.py: no `cad` command on PATH; install text-to-cad (README's Quickstart) first")
    stock.require("symbols", "footprints")
    start = time.monotonic()
    (HERE / "pinball.kicad_pcb").unlink(missing_ok=True)
    for script, *args in STEPS:
        began = time.monotonic()
        print(f"==> {script} {' '.join(args)}".rstrip(), flush=True)
        if subprocess.run([cad, "run", script, *args], cwd=HERE).returncode:  # the step said why: no traceback over it
            sys.exit(f"build.py: {script} failed; the steps after it did not run")
        print(f"    {time.monotonic() - began:.0f} s", flush=True)
    print(f"built pinball.kicad_pcb and its schematic in {time.monotonic() - start:.0f} s")


if __name__ == "__main__":
    main()
