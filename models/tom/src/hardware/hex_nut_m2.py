"""ISO 4032 M2 hex nut, step.parts catalog model (nominal thread envelope).

Pinned STEP input; see STEP/imported/README.md for provenance.
"""
from pathlib import Path
from cadgen import read_step
INPUT=Path(__file__).resolve().parents[2]/"STEP/imported/hardware/hex_nut_m2_simple.step"

def hex_nut_m2():
    shape = read_step(INPUT)
    return shape.solids()[0] if len(shape.solids()) == 1 else shape
