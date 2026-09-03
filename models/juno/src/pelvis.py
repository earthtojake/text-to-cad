"""Pelvis link mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.pelvis.build_pelvis()` exactly; the URDF
link frame coincides with this part-local frame (waist-yaw joint center at
the origin).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.pelvis import build_pelvis


@step(out="../STEP/pelvis.step")
@threemf(out="../3MF/pelvis.3mf")
def pelvis():
    return build_pelvis()


if __name__ == "__main__":
    pelvis()
