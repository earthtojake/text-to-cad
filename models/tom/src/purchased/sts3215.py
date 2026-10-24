"""Selected Robotopian ST3215 engineering STEP, shared as the STS3250 envelope.

Source provenance and measured differences: SERVO_ALTERNATIVES.md. The STL is
regenerated with the imported reference so the URDF uses the same geometry.


Pinned STEP input; see STEP/imported/README.md for provenance.
"""
from pathlib import Path
from cadgen import read_step
INPUT=Path(__file__).resolve().parents[2]/"STEP/imported/sts3215.step"

def sts3215():
    return read_step(INPUT)
