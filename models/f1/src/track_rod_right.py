"""F1 part: right track rod.

Built in car coordinates by `lib/suspension.py`; the `front_suspension` stage
(`stages.py`) builds it.
"""

from lib import suspension as suspension_lib


def track_rod_right():
    built = suspension_lib.build_track_rod("right")
    return built
