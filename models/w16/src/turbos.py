"""W16 system model: turbos — four turbochargers.

A sub-assembly of the engine: the parts `lib/turbos.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.10`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import turbos as turbos_lib
from lib import spec as S


@step(out="../STEP/turbos.step")
def turbos():
    parts = turbos_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("turbos.build() produced no parts")
    return bd.Compound(children=parts, label="turbos")


if __name__ == "__main__":
    turbos()
