"""F1 part: the ribbed magnesium gearbox casing, two thirds of the drivetrain's build.

Built in car coordinates by `lib/drivetrain.py`; `drivetrain.py` calls it.
"""

from lib import drivetrain as drivetrain_lib


def gearbox_casing():
    built = drivetrain_lib.build_gearbox_casing()
    return built
