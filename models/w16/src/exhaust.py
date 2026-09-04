"""W16 system model: exhaust — 16 primaries, collectors, downpipes, shields.

A sub-assembly of the engine: the parts `lib/exhaust.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.11`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import exhaust as exhaust_lib
from lib import spec as S


@step(out="../STEP/exhaust.step")
def exhaust():
    parts = exhaust_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("exhaust.build() produced no parts")
    return bd.Compound(children=parts, label="exhaust")


if __name__ == "__main__":
    exhaust()
