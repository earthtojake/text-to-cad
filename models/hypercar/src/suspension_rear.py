"""Hypercar system model: suspension_rear — the same, rear.

A sub-assembly of the car: the group `lib/suspension_rear.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.6`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension_rear as suspension_rear_lib


@step(out="../STEP/suspension_rear.step")
def suspension_rear():
    return suspension_rear_lib.build()


if __name__ == "__main__":
    suspension_rear()
