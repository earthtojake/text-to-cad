"""Torso mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.torso.build_torso()` exactly; the URDF
link frame coincides with this part-local frame (torso link (waist-yaw joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.torso import build_torso


@step(out="../STEP/torso.step")
@threemf(out="../3MF/torso.3mf")
def torso():
    return build_torso()


if __name__ == "__main__":
    torso()
