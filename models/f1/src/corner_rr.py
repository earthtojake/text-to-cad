"""F1 part: rear-right corner.

Built in car coordinates by `lib/wheels.py`; the `corners` stage
(`stages.py`) builds it.
"""

from lib import wheels as wheels_lib


def corner_rr():
    built = wheels_lib.build_corner("rr")
    return built
