"""F1 part: DRS actuator four-bar (the `drs_crank` joint in `f1.py` turns it).

Built in car coordinates by `lib/rear_wing.py`; the `rear_aero` stage
(`stages.py`) builds it.
"""

from lib import rear_wing as rear_wing_lib


def drs_actuator():
    built = rear_wing_lib.build_drs_actuator()
    return built
