"""F1 part model: engine cover.

The geometry `lib/engine_cover.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.8`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import engine_cover as engine_cover_lib


@step(out="../STEP/engine_cover.step")
def engine_cover():
    return engine_cover_lib.build_engine_cover()


if __name__ == "__main__":
    engine_cover()
