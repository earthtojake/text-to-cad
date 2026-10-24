"""F1 part: front-right corner.

Built in car coordinates by `lib/wheels.py`; the `corners` stage
(`stages.py`) builds it.
"""

from lib import wheels as wheels_lib


def corner_fr():
    built = wheels_lib.build_corner("fr")
    return built
