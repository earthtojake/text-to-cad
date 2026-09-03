#!/usr/bin/env python3
"""thumb_base mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_thumb_base()` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_thumb_base


@threemf(out="../3MF/thumb_base.3mf")
@step(out="../STEP/thumb_base.step")
def thumb_base():
    return build_thumb_base()


if __name__ == "__main__":
    thumb_base()
