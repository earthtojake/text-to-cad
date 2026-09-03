#!/usr/bin/env python3
"""ring_proximal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_proximal("ring")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_proximal


@threemf(out="../3MF/ring_proximal.3mf")
@step(out="../STEP/ring_proximal.step")
def ring_proximal():
    return build_finger_proximal("ring")


if __name__ == "__main__":
    ring_proximal()
