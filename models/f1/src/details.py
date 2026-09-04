"""F1 part model: details.

The geometry `lib/details.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.28`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import details as details_lib


@step(out="../STEP/details.step")
def details():
    return details_lib.build_details()


if __name__ == "__main__":
    details()
