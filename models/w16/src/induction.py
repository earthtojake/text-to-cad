"""W16 system: induction — intercoolers, plenums, throttles, charge pipes, fuel rails.

A stage of the engine: the parts `lib/induction.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import induction as induction_lib
from lib import spec as S


@memo
def induction():
    parts = induction_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("induction.build() produced no parts")
    group = bd.Compound(children=parts, label="induction")
    return group
