"""Case cluster entry: every case part positioned in the watch frame.

z = 0 at the case-middle / caseback joint plane, +Z through the crystal,
crown at +X (see `lib/spec.py`).
"""

from cadgen import build123d as bd
from cadgen import step

from lib import case as C
from lib import materials as M


@step(out="../STEP/case.step")
def case():
    compound = bd.Compound(children=C.build_case_parts(), label="case")
    M.apply(compound)
    return compound


if __name__ == "__main__":
    case()
