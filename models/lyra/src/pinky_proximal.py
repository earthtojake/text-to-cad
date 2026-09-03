#!/usr/bin/env python3
"""pinky_proximal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_proximal("pinky")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_proximal


@threemf(out="../3MF/pinky_proximal.3mf")
@step(out="../STEP/pinky_proximal.step")
def pinky_proximal():
    return build_finger_proximal("pinky")


if __name__ == "__main__":
    pinky_proximal()
