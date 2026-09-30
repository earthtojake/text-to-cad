"""F1 part model: cover_panel.

The carbon engine cover shell, in car coordinates, from `lib/engine_cover.py`.
Nine tenths of the engine cover's build time, so it is its own model.
`engine_cover.py` links it; rebuild `engine_cover.py` (and `f1.py`) to pick up
a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import engine_cover as engine_cover_lib


@step(out="../STEP/cover_panel.step")
def cover_panel():
    return engine_cover_lib.build_cover_panel()


if __name__ == "__main__":
    cover_panel()
