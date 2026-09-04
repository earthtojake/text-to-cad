"""F1 part model: front suspension.

The geometry `lib/suspension.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.19`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension as suspension_lib


@step(out="../STEP/suspension_front.step")
def suspension_front():
    return suspension_lib.build_suspension_front()


if __name__ == "__main__":
    suspension_front()
