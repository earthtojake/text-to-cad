#!/usr/bin/env python3
"""index_distal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_finger_distal("index")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_finger_distal


@threemf(out="../3MF/index_distal.3mf")
@step(out="../STEP/index_distal.step")
def index_distal():
    return build_finger_distal("index")


if __name__ == "__main__":
    index_distal()
