"""Neck collar mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_neck_collar()` exactly; the URDF
link frame coincides with this part-local frame (neck collar link (neck-yaw joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_neck_collar


@step(out="../STEP/neck_collar.step")
@threemf(out="../3MF/neck_collar.3mf")
def neck_collar():
    return build_neck_collar()


if __name__ == "__main__":
    neck_collar()
