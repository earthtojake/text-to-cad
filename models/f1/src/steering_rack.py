"""F1 part model: steering rack.

The geometry `lib/suspension.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.27`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension as suspension_lib


@step(out="../STEP/steering_rack.step")
def steering_rack():
    return suspension_lib.build_steering_rack()


if __name__ == "__main__":
    steering_rack()
