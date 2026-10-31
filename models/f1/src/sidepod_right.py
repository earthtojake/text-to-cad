"""F1 part: right sidepod (the left one's mirror image, from the same factory).

Built in car coordinates by `lib/sidepods.py`; the `sidepods` stage
(`stages.py`) builds it.
"""

from lib import sidepods as sidepods_lib


def sidepod_right():
    built = sidepods_lib.build_sidepod("right")
    return built
