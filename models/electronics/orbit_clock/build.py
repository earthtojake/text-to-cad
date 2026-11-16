"""Builds Orbit's KiCad project from its scripts: the project libraries and their tables, the five schematic
sheets (and the project, made by KiCad), then the board: setup, place, route, zones and silk.

    cad run build.py

The KiCad files are build output (`.gitignore` keeps them out of Git): run this before opening the board or the
schematic in the CAD Viewer or in KiCad, and before any script that reads the board (`src/`, `check_orbit.py`).
It needs the `cad` command (KiCad 10.99's kicad-cli and API come with it) and KiCad's stock libraries, which
`build_libraries.py` reads from macOS's KiCad.app or from `KICAD_STOCK`. Rerunning it over a built board is
harmless: each stage states the board it wants, and a sheet that already holds symbols is left as it is.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = (
    ("scripts/build_libraries.py",),        # orbit.kicad_sym, power.kicad_sym, orbit.pretty, the library tables
    ("scripts/schematic.py",),              # the root (KiCad makes it and the project) and four sheets
    ("scripts/board.py", "all"),            # setup, place, route, zones, silk
)


def main() -> None:
    cad = shutil.which("cad")
    if cad is None:
        sys.exit("build.py: no `cad` command on PATH; install text-to-cad (README's Quickstart) first")
    start = time.monotonic()
    for script, *args in STEPS:
        began = time.monotonic()
        print(f"==> {script} {' '.join(args)}".rstrip(), flush=True)
        subprocess.run([cad, "run", script, *args], cwd=HERE, check=True)
        print(f"    {time.monotonic() - began:.0f} s", flush=True)
    print(f"built orbit.kicad_pcb and its schematic in {time.monotonic() - start:.0f} s")


if __name__ == "__main__":
    main()
