"""F1 part: diffuser.

Built in car coordinates by `lib/floor.py`; the `underbody` stage
(`stages.py`) builds it.
"""

from lib import floor as floor_lib


def diffuser():
    built = floor_lib.build_diffuser()
    return built
