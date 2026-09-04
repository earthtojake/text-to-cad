"""F1 part model: nose.

The geometry `lib/nose.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.2`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import nose as nose_lib


@step(out="../STEP/nose.step")
def nose():
    return nose_lib.build_nose()


if __name__ == "__main__":
    nose()
