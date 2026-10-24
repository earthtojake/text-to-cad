"""F1 part: drivetrain -- the running gear: gearbox casing, its ancillaries, the rear structure.

Built in car coordinates by `lib/drivetrain.py`; `f1.py` calls it in the car's body,
a `@memo` stage of its own.
"""

from cadgen import memo

from drivetrain_ancillaries import drivetrain_ancillaries
from gearbox_casing import gearbox_casing
from lib import drivetrain as drivetrain_lib
from lib import surfaces
from rear_structure import rear_structure


@memo
def drivetrain():
    built = surfaces.group("drivetrain", [
        gearbox_casing(),
        drivetrain_ancillaries(),
        rear_structure(),
        *drivetrain_lib.build_drivetrain_parts(),
    ])
    return built
