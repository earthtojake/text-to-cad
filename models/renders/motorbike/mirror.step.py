"""Mirror entry: one round bar-end mirror (rider-left instance shown).

The assembly instances this geometry twice, one per handlebar side.
"""

from build123d import Compound

import _trim as T


DISPLAY_NAME = "Motorbike mirror"


def gen_step():
    return Compound(children=T.build_mirror(1.0), label="mirror")
