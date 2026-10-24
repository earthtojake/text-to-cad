"""F1 part: rear-left corner.

Built in car coordinates by `lib/wheels.py`; the `corners` stage
(`stages.py`) builds it.
"""

from lib import wheels as wheels_lib


def corner_rl():
    built = wheels_lib.build_corner("rl")
    return built
