"""Raspberry Pi 5, owner-supplied SolidWorks 2023 export (raspberry-pi-5-2.snapshot.8,
file dated 2023-11-03), adopted 2026-09-17 in place of Raspberry Pi's own mechanical
reference RP-004882-DD. Board outline, 58 x 49 mounting pattern and orientation agree
with that reference; its board is 1.6 mm rather than 1.4, its mount holes are modelled
as 6 mm rings rather than 2.7 mm bores, and it carries 590 solids against 47.

Purchased raspberry pi 5; dimensions preserved from supplied/catalog STEP.

Pinned STEP input; see STEP/imported/README.md for provenance.
"""
from pathlib import Path
from cadgen import read_step
INPUT=Path(__file__).resolve().parents[2]/"STEP/imported/electronics/raspberry_pi_5.step"

def raspberry_pi_5():
    return read_step(INPUT)
