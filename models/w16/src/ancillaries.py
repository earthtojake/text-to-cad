"""W16 system: ancillaries — alternator, water pumps, belt, coolant manifolds, bell housing.

A stage of the engine: the parts `lib/ancillaries.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import ancillaries as ancillaries_lib
from lib import spec as S


@memo
def ancillaries():
    parts = ancillaries_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("ancillaries.build() produced no parts")
    group = bd.Compound(children=parts, label="ancillaries")
    return group
