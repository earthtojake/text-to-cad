"""F1 part model: front-left corner: wheel, brake, upright.

The geometry `lib/wheels.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.21`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import wheels as wheels_lib


@step(out="../STEP/corner_fl.step")
def corner_fl():
    return wheels_lib.build_corner("fl")


if __name__ == "__main__":
    corner_fl()
