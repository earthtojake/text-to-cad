"""F-14D system model: nozzles — C-D nozzles, petals, seals, actuator rings.

The group `lib/nozzles.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.5`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import nozzles as nozzles_lib


@step(out="../STEP/nozzles.step")
def nozzles():
    return nozzles_lib.build()


if __name__ == "__main__":
    nozzles()
