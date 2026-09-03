"""Right thigh mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.legs.build_thigh("right")` exactly; the URDF
link frame coincides with this part-local frame (thigh link (hip-pitch joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.legs import build_thigh


@step(out="../STEP/thigh_right.step")
@threemf(out="../3MF/thigh_right.3mf")
def thigh_right():
    return build_thigh('right')


if __name__ == "__main__":
    thigh_right()
