"""F1 part: front wing.

Built in car coordinates by `lib/front_wing.py`; the `front_end` stage
(`stages.py`) builds it.
"""

from lib import front_wing as front_wing_lib


def front_wing():
    built = front_wing_lib.build_front_wing()
    return built
