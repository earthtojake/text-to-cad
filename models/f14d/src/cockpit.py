"""F-14D system model: cockpit — tub, panels, seats, HUD, canopy, windscreen.

The group `lib/cockpit.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.2`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import cockpit as cockpit_lib


@step(out="../STEP/cockpit.step")
def cockpit():
    return cockpit_lib.build()


if __name__ == "__main__":
    cockpit()
