"""Left forearm mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.arms.build_forearm("left")` exactly; the URDF
link frame coincides with this part-local frame (forearm link (elbow joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.arms import build_forearm


@step(out="../STEP/forearm_left.step")
@threemf(out="../3MF/forearm_left.3mf")
def forearm_left():
    return build_forearm('left')


if __name__ == "__main__":
    forearm_left()
