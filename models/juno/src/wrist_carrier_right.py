"""Right wrist carrier mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_wrist_carrier("right")` exactly; the URDF
link frame coincides with this part-local frame (wrist carrier link (wrist-roll joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_wrist_carrier


@step(out="../STEP/wrist_carrier_right.step")
@threemf(out="../3MF/wrist_carrier_right.3mf")
def wrist_carrier_right():
    return build_wrist_carrier('right')


if __name__ == "__main__":
    wrist_carrier_right()
