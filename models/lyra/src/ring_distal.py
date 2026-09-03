#!/usr/bin/env python3
"""ring_distal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_distal("ring")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_distal


@threemf(out="../3MF/ring_distal.3mf")
@step(out="../STEP/ring_distal.step")
def ring_distal():
    return build_finger_distal("ring")


if __name__ == "__main__":
    ring_distal()
