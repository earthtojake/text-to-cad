"""m2_mf_standoff_10mm

Pinned STEP input; see STEP/imported/README.md for provenance.
"""
from pathlib import Path
from cadgen import read_step
INPUT=Path(__file__).resolve().parents[2]/"STEP/imported/hardware/m2_mf_standoff_10mm.step"

def m2_mf_standoff_10mm():
    shape = read_step(INPUT)
    return shape.solids()[0] if len(shape.solids()) == 1 else shape
