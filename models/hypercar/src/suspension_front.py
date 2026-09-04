"""Hypercar system model: suspension_front — wishbones, uprights, pushrods, rockers, coilovers.

A sub-assembly of the car: the group `lib/suspension_front.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.5`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import suspension_front as suspension_front_lib


@step(out="../STEP/suspension_front.step")
def suspension_front():
    return suspension_front_lib.build()


if __name__ == "__main__":
    suspension_front()
