"""Right ankle link mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_ankle_link("right")` exactly; the URDF
link frame coincides with this part-local frame (ankle link (ankle-pitch joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_ankle_link


@step(out="../STEP/ankle_link_right.step")
@threemf(out="../3MF/ankle_link_right.3mf")
def ankle_link_right():
    return build_ankle_link('right')


if __name__ == "__main__":
    ankle_link_right()
