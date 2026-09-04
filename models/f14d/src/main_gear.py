"""F-14D system model: main_gear — legs, wheels, brakes, doors, bays.

The group `lib/main_gear.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.9`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import main_gear as main_gear_lib


@step(out="../STEP/main_gear.step")
def main_gear():
    return main_gear_lib.build()


if __name__ == "__main__":
    main_gear()
