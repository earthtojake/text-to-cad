"""Hypercar system model: chassis — monocoque tub, subframes, crash structures.

A sub-assembly of the car: the group `lib/chassis.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.4`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import chassis as chassis_lib


@step(out="../STEP/chassis.step")
def chassis():
    return chassis_lib.build()


if __name__ == "__main__":
    chassis()
