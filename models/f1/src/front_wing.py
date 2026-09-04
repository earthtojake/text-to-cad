"""F1 part model: front wing.

The geometry `lib/front_wing.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.1`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import front_wing as front_wing_lib


@step(out="../STEP/front_wing.step")
def front_wing():
    return front_wing_lib.build_front_wing()


if __name__ == "__main__":
    front_wing()
