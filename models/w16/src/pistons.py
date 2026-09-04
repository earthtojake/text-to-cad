"""W16 system model: pistons — 16 x piston/rings/pin/circlips/rod/cap/bolts/shells.

A sub-assembly of the engine: the parts `lib/pistons.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.3`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import pistons as pistons_lib
from lib import spec as S


@step(out="../STEP/pistons.step",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def pistons():
    parts = pistons_lib.build()
    if not parts:
        raise RuntimeError("pistons.build() produced no parts")
    return bd.Compound(children=parts, label="pistons")


if __name__ == "__main__":
    pistons()
