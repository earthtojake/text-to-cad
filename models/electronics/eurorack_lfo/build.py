"""Builds Twin Orbit's KiCad project from its scripts: the footprint library and the library tables, the three
schematic sheets, the board with the netlist, the placement, the routing, the pours, the cleanup and the silkscreen.

    cad run build.py

The KiCad files the scripts write are build output (`.gitignore` keeps them out of Git): run this before opening
the board or the schematic in the CAD Viewer or in KiCad, and before any script that reads the board (`src/`,
`check_twin_orbit.py`, `scripts/check_schematic.py`). `twin_orbit.kicad_pro` is not written by a script: it is the
source of the board's rules and netclasses, and KiCad makes the board beside it. It needs the `cad` command (KiCad
10.99's kicad-cli and API come with it) and KiCad's stock libraries, which the generators read from macOS's
KiCad.app or from `KICAD10_SYMBOL_DIR` and `KICAD10_FOOTPRINT_DIR`. Rerunning it over a built board is harmless:
each step states the board it wants.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRC_BEFORE_CLEANUP = "tmp/drc_before_cleanup.json"

# (how, script, arguments): "python" runs with this interpreter (the standard library alone), "cad" through
# `cad run`, "drc" saves `cad kicad_pcb drc --json` of the board as it stands to the file named.
STEPS = (
    ("python", "scripts/make_libs.py"),            # twin_orbit.pretty and the library tables
    ("python", "scripts/gen_schematic.py"),        # root, LFO (x2) and power sheets
    ("cad", "scripts/board_01_import.py"),         # netlist -> board
    ("cad", "scripts/board_02_place.py"),          # outline + placement (scripts/place_table.py)
    ("python", "scripts/board_02_keepouts.py"),    # the jacks' own keepouts back over the jacks
    ("cad", "scripts/board_03_route.py"),          # tracks + vias: the plan, routed by cad.kicad.route
    ("cad", "scripts/board_04_pour.py"),           # GND pours both layers + stitching
    ("cad", "scripts/board_05_islands.py"),        # a via in any pour piece left without one
    ("drc", DRC_BEFORE_CLEANUP),                   # what the cleanup reads
    ("cad", "scripts/board_06_cleanup.py", DRC_BEFORE_CLEANUP),   # vias DRC calls dangling, same-net vias too close
    ("cad", "scripts/board_07_silk.py"),           # every reference to a free spot, or onto the Fab layer
)


def main() -> None:
    cad = shutil.which("cad")
    if cad is None:
        sys.exit("build.py: no `cad` command on PATH; install text-to-cad (README's Quickstart) first")
    start = time.monotonic()
    for how, script, *args in STEPS:
        began = time.monotonic()
        print(f"==> {how} {script} {' '.join(args)}".rstrip(), flush=True)
        if how == "drc":
            # DRC fails the board before its cleanup; the findings are what the next step wants, so no check here.
            out = HERE / script
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as fh:
                subprocess.run([cad, "kicad_pcb", "drc", "twin_orbit.kicad_pcb", "--json"], cwd=HERE, stdout=fh)
        else:
            command = [sys.executable, script, *args] if how == "python" else [cad, "run", script, *args]
            subprocess.run(command, cwd=HERE, check=True)
        print(f"    {time.monotonic() - began:.0f} s", flush=True)
    print(f"built twin_orbit.kicad_pcb and its schematic in {time.monotonic() - start:.0f} s")


if __name__ == "__main__":
    main()
