"""F1 part model: beam wing.

The geometry `lib/rear_wing.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.18`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import rear_wing as rear_wing_lib


@step(out="../STEP/beam_wing.step")
def beam_wing():
    return rear_wing_lib.build_beam_wing()


if __name__ == "__main__":
    beam_wing()
