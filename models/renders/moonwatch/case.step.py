"""Case cluster entry: every case part positioned in the watch frame.

z = 0 at the case-middle / caseback joint plane, +Z through the crystal,
crown at +X (see `_spec`).
"""

from build123d import Compound

import _case as C
import _materials as M


def gen_step():
    compound = Compound(children=C.build_case_parts(), label="case")
    M.apply(compound)
    return compound
