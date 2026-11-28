"""The case's standing deliverables, rewritten on each run: a 3MF and a STEP of each printed part in its
print orientation (3MF/, STEP/), and the assembly's STEP and GLB (the GLB carries the explode animation).

    cad run src/exports.py
"""
from pathlib import Path

import cad

from assembly import nine
from case import keycap_print, knob_print, plate_print, tray_print

ROOT = Path(__file__).resolve().parent.parent      # the project folder

if __name__ == "__main__":
    for name, part in (("tray", tray_print), ("plate", plate_print), ("keycap", keycap_print), ("knob", knob_print)):
        handle = part()
        cad.export(handle, ROOT / "3MF" / f"{name}.3mf")
        cad.export(handle, ROOT / "STEP" / f"{name}.step")
    assembly = nine()
    cad.export(assembly, ROOT / "STEP" / "nine.step")
    cad.export(assembly, ROOT / "GLB" / "nine.glb")
