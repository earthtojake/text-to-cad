"""F1 part: steering rack.

Built in car coordinates by `lib/suspension.py`; the `front_suspension` stage
(`stages.py`) builds it.
"""

from lib import suspension as suspension_lib


def steering_rack():
    built = suspension_lib.build_steering_rack()
    return built
