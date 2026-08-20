"""Turn signal entry: one amber signal (rider-left front instance shown).

The assembly instances this geometry four times: front-left, front-right on
the leg shield, rear-left, rear-right on the under-seat body.
"""

from build123d import Compound

import _spec as S
import _trim as T


DISPLAY_NAME = "Motorbike turn signal"


def gen_step():
    x, y, z = S.FRONT_SIGNAL_POS
    return Compound(children=T.build_turn_signal((x, y, z), 1.0), label="turn_signal")
