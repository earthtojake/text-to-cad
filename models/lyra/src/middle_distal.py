#!/usr/bin/env python3
"""middle_distal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_distal("middle")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_distal


@threemf(out="../3MF/middle_distal.3mf")
@step(out="../STEP/middle_distal.step")
def middle_distal():
    return build_finger_distal("middle")


if __name__ == "__main__":
    middle_distal()
