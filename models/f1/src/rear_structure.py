"""F1 part: rear impact structure, pickup carriers, pylon pad, rear light.

Built in car coordinates by `lib/drivetrain.py`; `drivetrain.py` calls it.
"""

from lib import drivetrain as drivetrain_lib


def rear_structure():
    built = drivetrain_lib.build_rear_structure()
    return built
