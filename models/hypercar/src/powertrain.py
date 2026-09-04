"""Hypercar system model: powertrain — engine, intake, exhaust, transaxle, driveshafts.

A sub-assembly of the car: the group `lib/powertrain.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.9`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import powertrain as powertrain_lib


@step(out="../STEP/powertrain.step")
def powertrain():
    return powertrain_lib.build()


if __name__ == "__main__":
    powertrain()
