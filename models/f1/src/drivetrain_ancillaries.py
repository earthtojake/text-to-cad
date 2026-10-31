"""F1 part: the hardware bolted to the gearbox casing.

Built in car coordinates by `lib/drivetrain.py`; `drivetrain.py` calls it.
"""

from lib import drivetrain as drivetrain_lib


def drivetrain_ancillaries():
    built = drivetrain_lib.build_drivetrain_ancillaries()
    return built
