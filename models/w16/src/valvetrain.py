"""W16 system: valvetrain — 64 valves + springs + retainers + followers + HLAs.

A stage of the engine: the parts `lib/valvetrain.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import valvetrain as valvetrain_lib


@memo
def valvetrain():
    parts = valvetrain_lib.build()
    if not parts:
        raise RuntimeError("valvetrain.build() produced no parts")
    group = bd.Compound(children=parts, label="valvetrain")
    return group
