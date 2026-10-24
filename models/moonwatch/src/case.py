"""Case cluster entry: every case part positioned in the watch frame.

z = 0 at the case-middle / caseback joint plane, +Z through the crystal,
crown at +X (see `lib/spec.py`).
"""

from cadgen import model

from lib import watch


@model
def case():
    return watch.case()


if __name__ == "__main__":
    case()
