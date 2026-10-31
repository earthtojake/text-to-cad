"""F1 part: halo.

Built in car coordinates by `lib/monocoque.py`; the `survival_cell` stage
(`stages.py`) builds it.
"""

from lib import monocoque as monocoque_lib


def halo():
    built = monocoque_lib.build_halo()
    return built
