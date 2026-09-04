"""W16 system model: valvetrain — 64 valves + springs + retainers + followers + HLAs.

A sub-assembly of the engine: the parts `lib/valvetrain.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.5`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import valvetrain as valvetrain_lib
from lib import spec as S


@step(out="../STEP/valvetrain.step")
def valvetrain():
    parts = valvetrain_lib.build()
    if not parts:
        raise RuntimeError("valvetrain.build() produced no parts")
    return bd.Compound(children=parts, label="valvetrain")


if __name__ == "__main__":
    valvetrain()
