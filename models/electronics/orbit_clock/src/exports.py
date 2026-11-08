"""Orbit's standing deliverables, rewritten on each run: a 3MF of each printed part in its print orientation
(3MF/), at a tolerance about a tenth of its smallest clearance, the two-material front among them, and the
assembly's STEP and GLB (the GLB carries the explode animation). The assembly's files are named
orbit_assembly so they never take the place of the board's own STEP/orbit.step, which KiCad writes.

    cad run src/exports.py
"""
from pathlib import Path

from cad import model

from orbit import baffle, diffuser_print, front_print, orbit, stand

ROOT = Path(__file__).resolve().parent.parent      # the project folder

if __name__ == "__main__":
    model.export(baffle(), ROOT / "3MF" / "baffle.3mf", tolerance=0.02)
    model.export(diffuser_print(), ROOT / "3MF" / "diffuser.3mf", tolerance=0.02)
    model.export(stand(), ROOT / "3MF" / "stand.3mf", tolerance=0.03)
    model.export(front_print(), ROOT / "3MF" / "front_two_material.3mf", tolerance=0.02)
    model.export(orbit(), ROOT / "STEP" / "orbit_assembly.step", ROOT / "GLB" / "orbit_assembly.glb")
