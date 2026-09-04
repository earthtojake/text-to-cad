"""F1 part model: rear-right corner.

The geometry `lib/wheels.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.26`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import wheels as wheels_lib


@step(out="../STEP/corner_rr.step")
def corner_rr():
    return wheels_lib.build_corner("rr")


if __name__ == "__main__":
    corner_rr()
