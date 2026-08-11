"""Bracelet entry: flat three-link bracelet with end links and closed
fold-over clasp, draped in the watch frame (see `_spec` conventions).

Every link, pin, end link, and clasp component is its own labeled,
colored body; rows articulate about shared pin axes with 0.06 radial
clearance.
"""

import _materials
from _bracelet import build_bracelet


def gen_step():
    compound = build_bracelet()
    _materials.apply(compound)
    return compound
