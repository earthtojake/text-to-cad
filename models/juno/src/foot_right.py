"""Right foot mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.legs.build_foot("right")` exactly; the URDF
link frame coincides with this part-local frame (foot link (ankle-roll joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.legs import build_foot


@step(out="../STEP/foot_right.step")
@threemf(out="../3MF/foot_right.3mf")
def foot_right():
    return build_foot('right')


if __name__ == "__main__":
    foot_right()
