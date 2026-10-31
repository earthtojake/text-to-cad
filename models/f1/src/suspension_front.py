"""F1 part: front suspension.

Built in car coordinates by `lib/suspension.py`; the `front_suspension` stage
(`stages.py`) builds it.
"""

from lib import suspension as suspension_lib


def suspension_front():
    built = suspension_lib.build_suspension_front()
    return built
