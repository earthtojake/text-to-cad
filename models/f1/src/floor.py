"""F1 part: floor.

Built in car coordinates by `lib/floor.py`; the `underbody` stage
(`stages.py`) builds it.
"""

from lib import floor as floor_lib


def floor():
    built = floor_lib.build_floor()
    return built
