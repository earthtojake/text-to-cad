"""F1 part: rear wing mainplane + endplates.

Built in car coordinates by `lib/rear_wing.py`; the `rear_aero` stage
(`stages.py`) builds it.
"""

from lib import rear_wing as rear_wing_lib


def rear_wing():
    built = rear_wing_lib.build_rear_wing()
    return built
