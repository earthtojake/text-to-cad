"""F1 part model: power unit.

The geometry `lib/power_unit.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.13`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import power_unit as power_unit_lib


@step(out="../STEP/power_unit.step")
def power_unit():
    return power_unit_lib.build_power_unit()


if __name__ == "__main__":
    power_unit()
