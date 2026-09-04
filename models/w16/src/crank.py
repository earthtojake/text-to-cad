"""W16 system model: crank — crankshaft, damper, flywheel.

A sub-assembly of the engine: the parts `lib/bottom_end.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.2`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import bottom_end as bottom_end_lib
from lib import spec as S


@step(out="../STEP/crank.step",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def crank():
    parts = bottom_end_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("bottom_end.build() produced no parts")
    return bd.Compound(children=parts, label="crank")


if __name__ == "__main__":
    crank()
