"""F1 part model: drivetrain_ancillaries.

The hardware bolted to the gearbox casing, in car coordinates, from
`lib/drivetrain.py`: bellhousing flange, engine mount bolts and dowels, oil
pump, hydraulic pack and lines, ARB platforms and machined pads.
`drivetrain.py` links it; rebuild `drivetrain.py` (and `f1.py`) to pick up a
change here.
"""

from __future__ import annotations

from cadgen import step

from lib import drivetrain as drivetrain_lib


@step(out="../STEP/drivetrain_ancillaries.step")
def drivetrain_ancillaries():
    return drivetrain_lib.build_drivetrain_ancillaries()


if __name__ == "__main__":
    drivetrain_ancillaries()
