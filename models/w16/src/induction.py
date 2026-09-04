"""W16 system model: induction — intercoolers, plenums, throttles, charge pipes, fuel rails.

A sub-assembly of the engine: the parts `lib/induction.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.12`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import induction as induction_lib
from lib import spec as S


@step(out="../STEP/induction.step")
def induction():
    parts = induction_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("induction.build() produced no parts")
    return bd.Compound(children=parts, label="induction")


if __name__ == "__main__":
    induction()
