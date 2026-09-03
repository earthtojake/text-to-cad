"""Right bicep mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.arms.build_bicep("right")` exactly; the URDF
link frame coincides with this part-local frame (bicep link (shoulder-yaw joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.arms import build_bicep


@step(out="../STEP/bicep_right.step")
@threemf(out="../3MF/bicep_right.3mf")
def bicep_right():
    return build_bicep('right')


if __name__ == "__main__":
    bicep_right()
