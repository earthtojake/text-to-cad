"""F1 part model: airbox.

The geometry `lib/engine_cover.py` builds, in car coordinates, as one model with its
own STEP and record. `f1.py` links it as occurrence `#o1.9`; rebuild `f1.py`
to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import engine_cover as engine_cover_lib


@step(out="../STEP/airbox.step")
def airbox():
    return engine_cover_lib.build_airbox()


if __name__ == "__main__":
    airbox()
