"""Left foot mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.legs.build_foot("left")` exactly; the URDF
link frame coincides with this part-local frame (foot link (ankle-roll joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.legs import build_foot


@step(out="../STEP/foot_left.step")
@threemf(out="../3MF/foot_left.3mf")
def foot_left():
    return build_foot('left')


if __name__ == "__main__":
    foot_left()
