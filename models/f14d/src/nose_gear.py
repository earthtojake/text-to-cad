"""F-14D system model: nose_gear — leg, wheels, launch bar, doors, bay.

The group `lib/nose_gear.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.8`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import nose_gear as nose_gear_lib


@step(out="../STEP/nose_gear.step")
def nose_gear():
    return nose_gear_lib.build()


if __name__ == "__main__":
    nose_gear()
