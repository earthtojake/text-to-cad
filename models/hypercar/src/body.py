"""Hypercar system: body — painted panels, pillars, aero skins.

A stage of the car: the group `lib/body.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import body as body_lib


@memo
def body():
    built = body_lib.build()
    return built
