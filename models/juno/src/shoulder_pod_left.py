"""Left shoulder pod mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.joints.build_shoulder_pod("left")` exactly; the URDF
link frame coincides with this part-local frame (shoulder pod link (shoulder-pitch joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.joints import build_shoulder_pod


@step(out="../STEP/shoulder_pod_left.step")
@threemf(out="../3MF/shoulder_pod_left.3mf")
def shoulder_pod_left():
    return build_shoulder_pod('left')


if __name__ == "__main__":
    shoulder_pod_left()
