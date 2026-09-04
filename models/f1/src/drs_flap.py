"""F1 part model: DRS flap (rotates in `f1.step.js`).

The geometry `lib/rear_wing.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.16`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import rear_wing as rear_wing_lib


@step(out="../STEP/drs_flap.step")
def drs_flap():
    return rear_wing_lib.build_drs_flap()


if __name__ == "__main__":
    drs_flap()
