#!/usr/bin/env python3
"""pinky_distal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_distal("pinky")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_distal


@threemf(out="../3MF/pinky_distal.3mf")
@step(out="../STEP/pinky_distal.step")
def pinky_distal():
    return build_finger_distal("pinky")


if __name__ == "__main__":
    pinky_distal()
