"""Hypercar system: aero — splitter, diffuser, wing.

A stage of the car: the group `lib/aero.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import aero as aero_lib


@memo
def aero():
    built = aero_lib.build()
    return built
