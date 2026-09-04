"""Hypercar system model: glazing — DLO glass + lamp lenses.

A sub-assembly of the car: the group `lib/glazing.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.2`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import glazing as glazing_lib


@step(out="../STEP/glazing.step")
def glazing():
    return glazing_lib.build()


if __name__ == "__main__":
    glazing()
