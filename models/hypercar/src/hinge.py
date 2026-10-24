"""Hypercar system: hinge — dihedral synchro-helix door mechanism.

A stage of the car: the group `lib/hinge.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import hinge as hinge_lib


@memo
def hinge():
    built = hinge_lib.build()
    return built
