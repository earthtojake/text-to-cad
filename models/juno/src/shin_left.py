"""Left shin mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.legs.build_shin("left")` exactly; the URDF
link frame coincides with this part-local frame (shin link (knee joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.legs import build_shin


@step(out="../STEP/shin_left.step")
@threemf(out="../3MF/shin_left.3mf")
def shin_left():
    return build_shin('left')


if __name__ == "__main__":
    shin_left()
