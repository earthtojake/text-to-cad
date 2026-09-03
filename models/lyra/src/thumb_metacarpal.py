#!/usr/bin/env python3
"""thumb_metacarpal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_thumb_metacarpal()` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_thumb_metacarpal


@threemf(out="../3MF/thumb_metacarpal.3mf")
@step(out="../STEP/thumb_metacarpal.step")
def thumb_metacarpal():
    return build_thumb_metacarpal()


if __name__ == "__main__":
    thumb_metacarpal()
