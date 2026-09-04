"""F1 part model: floor.

The geometry `lib/floor.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.10`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import floor as floor_lib


@step(out="../STEP/floor.step")
def floor():
    return floor_lib.build_floor()


if __name__ == "__main__":
    floor()
