"""F-14D system model: inlets — ramps, splitters, bleed slots, ducts.

The group `lib/inlets.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.4`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import inlets as inlets_lib


@step(out="../STEP/inlets.step")
def inlets():
    return inlets_lib.build()


if __name__ == "__main__":
    inlets()
