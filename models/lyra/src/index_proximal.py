#!/usr/bin/env python3
"""index_proximal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_proximal("index")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_proximal


@threemf(out="../3MF/index_proximal.3mf")
@step(out="../STEP/index_proximal.step")
def index_proximal():
    return build_finger_proximal("index")


if __name__ == "__main__":
    index_proximal()
