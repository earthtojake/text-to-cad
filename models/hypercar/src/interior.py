"""Hypercar system model: interior — seats, wheel, dash, console, pedals, door cards.

A sub-assembly of the car: the group `lib/interior.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.10`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import interior as interior_lib


@step(out="../STEP/interior.step")
def interior():
    return interior_lib.build()


if __name__ == "__main__":
    interior()
