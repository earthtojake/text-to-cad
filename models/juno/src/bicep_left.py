"""Left bicep mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.arms.build_bicep("left")` exactly; the URDF
link frame coincides with this part-local frame (bicep link (shoulder-yaw joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.arms import build_bicep


@step(out="../STEP/bicep_left.step")
@threemf(out="../3MF/bicep_left.3mf")
def bicep_left():
    return build_bicep('left')


if __name__ == "__main__":
    bicep_left()
