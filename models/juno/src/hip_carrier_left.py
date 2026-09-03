"""Left hip carrier mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_hip_carrier("left")` exactly; the URDF
link frame coincides with this part-local frame (hip carrier link (hip-roll joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_hip_carrier


@step(out="../STEP/hip_carrier_left.step")
@threemf(out="../3MF/hip_carrier_left.3mf")
def hip_carrier_left():
    return build_hip_carrier('left')


if __name__ == "__main__":
    hip_carrier_left()
