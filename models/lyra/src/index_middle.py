#!/usr/bin/env python3
"""index_middle mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_middle("index")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_middle


@threemf(out="../3MF/index_middle.3mf")
@step(out="../STEP/index_middle.step")
def index_middle():
    return build_finger_middle("index")


if __name__ == "__main__":
    index_middle()
