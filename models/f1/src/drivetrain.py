"""F1 part model: drivetrain.

The running gear `lib/drivetrain.py` builds (clutch, gear cluster, selectors,
differential, driveshafts), in car coordinates, plus three child models: the
gearbox casing, the ancillaries bolted to it, and the rear structure. The
casing is two thirds of the drivetrain's build time, so it is its own model and
an edit elsewhere never rebuilds it. `f1.py` links the drivetrain as occurrence
`#o1.14`; rebuild `f1.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from drivetrain_ancillaries import drivetrain_ancillaries
from gearbox_casing import gearbox_casing
from lib import drivetrain as drivetrain_lib
from lib import surfaces
from rear_structure import rear_structure


@step(out="../STEP/drivetrain.step")
def drivetrain():
    return surfaces.group("drivetrain", [
        gearbox_casing(),
        drivetrain_ancillaries(),
        rear_structure(),
        *drivetrain_lib.build_drivetrain_parts(),
    ])


if __name__ == "__main__":
    drivetrain()
