"""Right hand mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.hand.build_hand("right")` exactly; the URDF
link frame coincides with this part-local frame (hand link (wrist-pitch joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.hand import build_hand


@step(out="../STEP/hand_right.step")
@threemf(out="../3MF/hand_right.3mf")
def hand_right():
    return build_hand('right')


if __name__ == "__main__":
    hand_right()
