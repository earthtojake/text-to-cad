"""F1 part: cooling (radiators, ducts).

Built in car coordinates by `lib/sidepods.py`; the `sidepods` stage
(`stages.py`) builds it.
"""

from lib import sidepods as sidepods_lib


def cooling():
    built = sidepods_lib.build_cooling()
    return built
