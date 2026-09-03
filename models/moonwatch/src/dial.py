"""Dial + hands entry: black three-register step dial with applied indices,
printed tracks, snailed registers, and the full hand stack at 10:09:38.

Positioned in the WATCH frame (`lib/spec.py`): dial top at S.DIAL_Z, +Z up,
12 o'clock at +Y. Unbranded — numerals and scale markings only.
"""

from cadgen import build123d as bd
from cadgen import step

from lib import dial as D
from lib import materials as M


@step(out="../STEP/dial.step")
def dial():
    compound = bd.Compound(children=D.build_dial_parts(), label="dial")
    M.apply(compound)
    return compound


if __name__ == "__main__":
    dial()
