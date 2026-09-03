#!/usr/bin/env python3
"""thumb_distal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_thumb_distal()` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_thumb_distal


@threemf(out="../3MF/thumb_distal.3mf")
@step(out="../STEP/thumb_distal.step")
def thumb_distal():
    return build_thumb_distal()


if __name__ == "__main__":
    thumb_distal()
