"""Hypercar system model: lighting — lamp internals + light signature.

A sub-assembly of the car: the group `lib/lighting.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.3`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import lighting as lighting_lib


@step(out="../STEP/lighting.step")
def lighting():
    return lighting_lib.build()


if __name__ == "__main__":
    lighting()
