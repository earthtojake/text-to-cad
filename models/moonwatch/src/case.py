"""Case cluster entry: every case part positioned in the watch frame.

z = 0 at the case-middle / caseback joint plane, +Z through the crystal,
crown at +X (see `lib/spec.py`).
"""

from cad import xbf

from lib import watch


@xbf
def case():
    return watch.case()


if __name__ == "__main__":
    case()
