"""F1 part model: left sidepod.

The geometry `lib/sidepods.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.6`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import sidepods as sidepods_lib


@step(out="../STEP/sidepod_left.step")
def sidepod_left():
    return sidepods_lib.build_sidepod("left")


if __name__ == "__main__":
    sidepod_left()
