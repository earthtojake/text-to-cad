"""F1 part model: rear suspension.

The geometry `lib/suspension.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.20`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension as suspension_lib


@step(out="../STEP/suspension_rear.step")
def suspension_rear():
    return suspension_lib.build_suspension_rear()


if __name__ == "__main__":
    suspension_rear()
