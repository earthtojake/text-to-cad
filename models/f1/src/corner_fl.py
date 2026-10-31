"""F1 part: front-left corner: wheel, brake, upright.

Built in car coordinates by `lib/wheels.py`; the `corners` stage
(`stages.py`) builds it.
"""

from lib import wheels as wheels_lib


def corner_fl():
    built = wheels_lib.build_corner("fl")
    return built
