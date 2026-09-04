"""F1 part model: cockpit furniture.

The geometry `lib/cockpit.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.5`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import cockpit as cockpit_lib


@step(out="../STEP/cockpit.step")
def cockpit():
    return cockpit_lib.build_cockpit()


if __name__ == "__main__":
    cockpit()
