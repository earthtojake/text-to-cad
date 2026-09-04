"""Hypercar system model: details — mirrors, badges, filler, vents, fasteners.

A sub-assembly of the car: the group `lib/details.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.13`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import details as details_lib


@step(out="../STEP/details.step")
def details():
    return details_lib.build()


if __name__ == "__main__":
    details()
