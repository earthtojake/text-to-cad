"""F1 part model: right track rod.

The geometry `lib/suspension.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.24`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension as suspension_lib


@step(out="../STEP/track_rod_right.step")
def track_rod_right():
    return suspension_lib.build_track_rod("right")


if __name__ == "__main__":
    track_rod_right()
