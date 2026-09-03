"""Turn signal entry: one amber signal (rider-left front instance shown).

The assembly instances this geometry four times: front-left, front-right on
the leg shield, rear-left, rear-right on the under-seat body.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import spec as S
from lib import trim as T


@step(out="../STEP/turn_signal.step")
def turn_signal():
    x, y, z = S.FRONT_SIGNAL_POS
    return bd.Compound(children=T.build_turn_signal((x, y, z), 1.0), label="turn_signal")


if __name__ == "__main__":
    turn_signal()
