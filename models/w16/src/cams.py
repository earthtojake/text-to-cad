"""W16 system model: cams — four camshafts + caps.

A sub-assembly of the engine: the parts `lib/cams.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.6`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import cams as cams_lib
from lib import spec as S
from lib.palette import material_compound, materials_for_system


@step(out="../STEP/cams.step", materials=materials_for_system("cams"),
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def cams():
    parts = cams_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("cams.build() produced no parts")
    return material_compound(parts, "cams")


if __name__ == "__main__":
    cams()
