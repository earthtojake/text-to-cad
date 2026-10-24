"""Hypercar system: glazing — DLO glass + lamp lenses.

A stage of the car: the group `lib/glazing.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import glazing as glazing_lib


@memo
def glazing():
    built = glazing_lib.build()
    return built
