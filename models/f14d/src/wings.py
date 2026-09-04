"""F-14D system model: wings — panels, slats, flaps, spoilers, tip lights.

The group `lib/wings.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.3`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import wings as wings_lib


@step(out="../STEP/wings.step")
def wings():
    return wings_lib.build()


if __name__ == "__main__":
    wings()
