"""W16 system: exhaust — 16 primaries, collectors, downpipes, shields.

A stage of the engine: the parts `lib/exhaust.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import exhaust as exhaust_lib
from lib import spec as S


@memo
def exhaust():
    parts = exhaust_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("exhaust.build() produced no parts")
    group = bd.Compound(children=parts, label="exhaust")
    return group
