"""SO-101 wrist-guide camera: Innomaker U20CAM-1080P, dimensional reference.

Manufacturer specifies 32 mm PCB and 2.2 mm mounting bores; the official
SO-101/pgripper interface is 27 mm square. No manufacturer STEP was found.
1.5 mm PCB, 12.5 mm front lens depth and rear connector envelopes follow the
camera reference embedded in Norma's gripper assembly, not a tolerance drawing.
Origin: PCB front mounting face, optical axis +Z, cable exits toward -Y.


Pinned STEP input; see STEP/imported/README.md for provenance.
"""
from pathlib import Path
from cadgen import read_step
INPUT=Path(__file__).resolve().parents[2]/"STEP/imported/electronics/innomaker_u20cam.step"

def innomaker_u20cam():
    return read_step(INPUT)
