#!/usr/bin/env python3
"""palm mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lib.palm.build_palm()` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

from cadgen import step, threemf


from lib.palm import build_palm


@threemf(out="../3MF/palm.3mf")
@step(out="../STEP/palm.step")
def palm():
    return build_palm()


if __name__ == "__main__":
    palm()
