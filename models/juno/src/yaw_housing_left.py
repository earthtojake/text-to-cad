"""Left yaw housing mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_yaw_housing("left")` exactly; the URDF
link frame coincides with this part-local frame (yaw housing link (shoulder-roll joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_yaw_housing


@step(out="../STEP/yaw_housing_left.step")
@threemf(out="../3MF/yaw_housing_left.3mf")
def yaw_housing_left():
    return build_yaw_housing('left')


if __name__ == "__main__":
    yaw_housing_left()
