"""F1 part model: gearbox_casing.

The ribbed magnesium gearbox casing, in car coordinates, from
`lib/drivetrain.py`. Two thirds of the drivetrain's build time, so it is its
own model. `drivetrain.py` links it; rebuild `drivetrain.py` (and `f1.py`) to
pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import drivetrain as drivetrain_lib


@step(out="../STEP/gearbox_casing.step")
def gearbox_casing():
    return drivetrain_lib.build_gearbox_casing()


if __name__ == "__main__":
    gearbox_casing()
