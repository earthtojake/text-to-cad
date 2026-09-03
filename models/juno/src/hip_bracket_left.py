"""Left hip bracket mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_hip_bracket("left")` exactly; the URDF
link frame coincides with this part-local frame (hip bracket link (hip-yaw joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_hip_bracket


@step(out="../STEP/hip_bracket_left.step")
@threemf(out="../3MF/hip_bracket_left.3mf")
def hip_bracket_left():
    return build_hip_bracket('left')


if __name__ == "__main__":
    hip_bracket_left()
