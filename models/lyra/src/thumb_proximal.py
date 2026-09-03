#!/usr/bin/env python3
"""thumb_proximal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.digits.build_thumb_proximal()` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.digits import build_thumb_proximal


@threemf(out="../3MF/thumb_proximal.3mf")
@step(out="../STEP/thumb_proximal.step")
def thumb_proximal():
    return build_thumb_proximal()


if __name__ == "__main__":
    thumb_proximal()
