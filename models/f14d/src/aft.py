"""F-14D system model: aft — speed brakes, beavertail, tailhook, dump mast.

The group `lib/aft.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.7`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import aft as aft_lib


@step(out="../STEP/aft.step")
def aft():
    return aft_lib.build()


if __name__ == "__main__":
    aft()
