"""Hypercar system model: aero — splitter, diffuser, wing.

A sub-assembly of the car: the group `lib/aero.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.11`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import aero as aero_lib


@step(out="../STEP/aero.step")
def aero():
    return aero_lib.build()


if __name__ == "__main__":
    aero()
