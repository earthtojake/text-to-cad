"""W16 system: pistons — 16 x piston/rings/pin/circlips/rod/cap/bolts/shells.

A stage of the engine: the parts `lib/pistons.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import pistons as pistons_lib


@memo
def pistons():
    parts = pistons_lib.build()
    if not parts:
        raise RuntimeError("pistons.build() produced no parts")
    group = bd.Compound(children=parts, label="pistons")
    return group
