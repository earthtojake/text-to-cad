#!/usr/bin/env python3
"""ring_middle mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_middle("ring")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_middle


@threemf(out="../3MF/ring_middle.3mf")
@step(out="../STEP/ring_middle.step")
def ring_middle():
    return build_finger_middle("ring")


if __name__ == "__main__":
    ring_middle()
