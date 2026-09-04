"""F1 part model: monocoque (survival cell).

The geometry `lib/monocoque.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.3`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import monocoque as monocoque_lib


@step(out="../STEP/monocoque.step")
def monocoque():
    return monocoque_lib.build_monocoque()


if __name__ == "__main__":
    monocoque()
