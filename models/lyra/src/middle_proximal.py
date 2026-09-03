#!/usr/bin/env python3
"""middle_proximal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_proximal("middle")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_proximal


@threemf(out="../3MF/middle_proximal.3mf")
@step(out="../STEP/middle_proximal.step")
def middle_proximal():
    return build_finger_proximal("middle")


if __name__ == "__main__":
    middle_proximal()
