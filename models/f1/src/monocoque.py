"""F1 part: monocoque (survival cell).

Built in car coordinates by `lib/monocoque.py`; the `survival_cell` stage
(`stages.py`) builds it.
"""

from lib import monocoque as monocoque_lib


def monocoque():
    built = monocoque_lib.build_monocoque()
    return built
