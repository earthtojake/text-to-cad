"""Builds Nine's KiCad project from its scripts: the footprints, the four schematic sheets, the board and its
project file and rules, every part placed, every track and via, the pours and the silkscreen.

    cad run build.py

The KiCad files are build output (`.gitignore` keeps them out of Git): run this before opening the board or the
schematic in the CAD Viewer or in KiCad, and before any script that reads the board (`src/`, `check_macropad.py`).
It needs the `cad` command (KiCad 10.99's kicad-cli and API come with it) and KiCad's stock libraries, which the
generators and KiCad read in an installed KiCad or beside the `3dmodels` folder `CAD_KICAD_3DMODELS` names
(`scripts/stock.py`; README.md, Rebuild): without them it stops before the first step, saying so. Rerunning it over
a built board is harmless: each step states the board it wants.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts"))
import stock  # noqa: E402

# (how, script): "python" runs with this interpreter (`cad run`'s: the standard library, and the `cad` library
# for where KiCad's libraries are), "cad" through `cad run` (KiCad's API for the script).
STEPS = (
    ("python", "scripts/gen_footprints.py"),   # macropad.pretty
    ("python", "scripts/gen_schematic.py"),    # the four sheets
    ("cad", "scripts/step1_import.py"),        # the board (and its project, made by KiCad) with the netlist
    ("python", "scripts/step0_rules.py"),      # JLCPCB rules and netclasses into the project, the custom rules
    ("cad", "scripts/step2_place.py"),         # outline, every part's place, side and angle
    ("cad", "scripts/route.py"),               # every track and via, then the pours
    ("cad", "scripts/step4_silk.py"),          # silkscreen
)


def main() -> None:
    cad = shutil.which("cad")
    if cad is None:
        sys.exit("build.py: no `cad` command on PATH; install text-to-cad (README's Quickstart) first")
    stock.require("symbols", "footprints")
    start = time.monotonic()
    for how, script in STEPS:
        began = time.monotonic()
        print(f"==> {script}", flush=True)
        command = [sys.executable, script] if how == "python" else [cad, "run", script]
        if subprocess.run(command, cwd=HERE).returncode:  # the step said why: no traceback over it
            sys.exit(f"build.py: {script} failed; the steps after it did not run")
        print(f"    {script}: {time.monotonic() - began:.0f} s", flush=True)
    print(f"built macropad.kicad_pcb and its schematic in {time.monotonic() - start:.0f} s")


if __name__ == "__main__":
    main()
