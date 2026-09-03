#!/usr/bin/env python3
"""middle_middle mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_middle("middle")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_middle


@threemf(out="../3MF/middle_middle.3mf")
@step(out="../STEP/middle_middle.step")
def middle_middle():
    return build_finger_middle("middle")


if __name__ == "__main__":
    middle_middle()
