"""F1 part model: drivetrain.

The geometry `lib/drivetrain.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.14`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import drivetrain as drivetrain_lib


@step(out="../STEP/drivetrain.step")
def drivetrain():
    return drivetrain_lib.build_drivetrain()


if __name__ == "__main__":
    drivetrain()
