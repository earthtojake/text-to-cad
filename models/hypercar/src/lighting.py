"""Hypercar system: lighting — lamp internals + light signature.

A stage of the car: the group `lib/lighting.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import lighting as lighting_lib


@memo
def lighting():
    built = lighting_lib.build()
    return built
