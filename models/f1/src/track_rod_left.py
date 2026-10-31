"""F1 part: left track rod.

Built in car coordinates by `lib/suspension.py`; the `front_suspension` stage
(`stages.py`) builds it.
"""

from lib import suspension as suspension_lib


def track_rod_left():
    built = suspension_lib.build_track_rod("left")
    return built
