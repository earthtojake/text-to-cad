"""W16 system: turbos — four turbochargers.

A stage of the engine: the parts `lib/turbos.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import turbos as turbos_lib
from lib import spec as S


@memo
def turbos():
    parts = turbos_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("turbos.build() produced no parts")
    group = bd.Compound(children=parts, label="turbos")
    return group
