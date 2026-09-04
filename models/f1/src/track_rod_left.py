"""F1 part model: left track rod.

The geometry `lib/suspension.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.23`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension as suspension_lib


@step(out="../STEP/track_rod_left.step")
def track_rod_left():
    return suspension_lib.build_track_rod("left")


if __name__ == "__main__":
    track_rod_left()
