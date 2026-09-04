"""Left turn signal: one amber signal, authored at the front-left position.

The assembly links this model twice — front-left as returned, rear-left
placed with `Pos`. The right-hand signals are `turn_signal_right.py`: a
reflection is new geometry, so the right side is its own model from the same
`lib/trim.py` factory.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import spec as S
from lib import trim as T


@step(out="../STEP/turn_signal_left.step")
def turn_signal_left():
    x, y, z = S.FRONT_SIGNAL_POS
    return bd.Compound(children=T.build_turn_signal((x, y, z), 1.0), label="turn_signal")


if __name__ == "__main__":
    turn_signal_left()
