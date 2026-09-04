"""Hypercar system model: brakes — discs, calipers, hubs.

A sub-assembly of the car: the group `lib/brakes.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.8`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import brakes as brakes_lib


@step(out="../STEP/brakes.step")
def brakes():
    return brakes_lib.build()


if __name__ == "__main__":
    brakes()
