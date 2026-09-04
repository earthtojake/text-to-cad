"""W16 system model: ancillaries — alternator, water pumps, belt, coolant manifolds, bell housing.

A sub-assembly of the engine: the parts `lib/ancillaries.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.13`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import ancillaries as ancillaries_lib
from lib import spec as S


@step(out="../STEP/ancillaries.step",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def ancillaries():
    parts = ancillaries_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("ancillaries.build() produced no parts")
    return bd.Compound(children=parts, label="ancillaries")


if __name__ == "__main__":
    ancillaries()
