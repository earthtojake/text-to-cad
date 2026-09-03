"""Right hip carrier mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_hip_carrier("right")` exactly; the URDF
link frame coincides with this part-local frame (hip carrier link (hip-roll joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_hip_carrier


@step(out="../STEP/hip_carrier_right.step")
@threemf(out="../3MF/hip_carrier_right.3mf")
def hip_carrier_right():
    return build_hip_carrier('right')


if __name__ == "__main__":
    hip_carrier_right()
