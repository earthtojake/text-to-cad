#!/usr/bin/env python3
"""pinky_middle mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_middle("pinky")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_middle


@threemf(out="../3MF/pinky_middle.3mf")
@step(out="../STEP/pinky_middle.step")
def pinky_middle():
    return build_finger_middle("pinky")


if __name__ == "__main__":
    pinky_middle()
