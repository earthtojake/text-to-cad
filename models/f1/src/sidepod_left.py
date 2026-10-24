"""F1 part: left sidepod.

Built in car coordinates by `lib/sidepods.py`; the `sidepods` stage
(`stages.py`) builds it.
"""

from lib import sidepods as sidepods_lib


def sidepod_left():
    built = sidepods_lib.build_sidepod("left")
    return built
