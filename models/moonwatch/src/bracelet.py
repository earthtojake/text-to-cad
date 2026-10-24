"""Bracelet entry: flat three-link bracelet with end links and closed
fold-over clasp, draped in the watch frame (see `lib/spec.py` conventions).

Every link, pin, end link, and clasp component is its own labeled,
colored body; rows articulate about shared pin axes with 0.06 radial
clearance.
"""

from cadgen import model

from lib import watch


@model
def bracelet():
    return watch.bracelet()


if __name__ == "__main__":
    bracelet()
