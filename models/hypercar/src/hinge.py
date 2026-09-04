"""Hypercar system model: hinge — dihedral synchro-helix door mechanism.

A sub-assembly of the car: the group `lib/hinge.py` builds, as one model with
its own STEP, its own record and its own worker. `hypercar.py` links it as
occurrence `o1.12`; rebuild `hypercar.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import hinge as hinge_lib


@step(out="../STEP/hinge.step")
def hinge():
    return hinge_lib.build()


if __name__ == "__main__":
    hinge()
