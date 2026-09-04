"""Hypercar system model: body — painted panels, pillars, aero skins.

A sub-assembly of the car: the group `lib/body.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.1`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import body as body_lib


@step(out="../STEP/body.step")
def body():
    return body_lib.build()


if __name__ == "__main__":
    body()
