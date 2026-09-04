"""F1 part model: right sidepod (the left one's mirror image, from the same factory).

The geometry `lib/sidepods.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.7`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import sidepods as sidepods_lib


@step(out="../STEP/sidepod_right.step")
def sidepod_right():
    return sidepods_lib.build_sidepod("right")


if __name__ == "__main__":
    sidepod_right()
