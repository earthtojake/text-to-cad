"""F1 part: DRS flap, modelled shut (the `drs_flap` joint in `f1.py` turns it).

Built in car coordinates by `lib/rear_wing.py`; the `rear_aero` stage
(`stages.py`) builds it.
"""

from lib import rear_wing as rear_wing_lib


def drs_flap():
    built = rear_wing_lib.build_drs_flap()
    return built
