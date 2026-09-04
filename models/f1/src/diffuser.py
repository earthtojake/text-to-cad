"""F1 part model: diffuser.

The geometry `lib/floor.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.11`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import floor as floor_lib


@step(out="../STEP/diffuser.step")
def diffuser():
    return floor_lib.build_diffuser()


if __name__ == "__main__":
    diffuser()
