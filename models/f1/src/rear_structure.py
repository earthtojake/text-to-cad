"""F1 part model: rear_structure.

The rear impact structure with the pickup carriers, rear wing pylon pad and
rear light it is cut around, in car coordinates, from `lib/drivetrain.py`.
`drivetrain.py` links it; rebuild `drivetrain.py` (and `f1.py`) to pick up a
change here.
"""

from __future__ import annotations

from cadgen import step

from lib import drivetrain as drivetrain_lib


@step(out="../STEP/rear_structure.step")
def rear_structure():
    return drivetrain_lib.build_rear_structure()


if __name__ == "__main__":
    rear_structure()
