"""F1 part: beam wing.

Built in car coordinates by `lib/rear_wing.py`; the `rear_aero` stage
(`stages.py`) builds it.
"""

from lib import rear_wing as rear_wing_lib


def beam_wing():
    built = rear_wing_lib.build_beam_wing()
    return built
