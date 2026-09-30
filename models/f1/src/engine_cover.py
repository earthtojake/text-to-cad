"""F1 part model: engine cover.

The parts `lib/engine_cover.py` builds around the cover shell (aerial fin, exit
duct liner, aperture and cover flanges, Dzus fasteners, louvres), in car
coordinates, plus the shell itself as a child model: the shell is nine tenths of
the cover's build time, so an edit to anything else never rebuilds it. `f1.py`
links the engine cover as occurrence `#o1.8`; rebuild `f1.py` to pick up a
change here.
"""

from __future__ import annotations

from cadgen import step

from cover_panel import cover_panel
from lib import engine_cover as engine_cover_lib
from lib import surfaces


@step(out="../STEP/engine_cover.step")
def engine_cover():
    return surfaces.group("engine_cover", [
        cover_panel(),
        *engine_cover_lib.build_engine_cover_parts(),
    ])


if __name__ == "__main__":
    engine_cover()
