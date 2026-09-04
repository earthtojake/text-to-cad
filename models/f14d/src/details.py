"""F-14D system model: details — antennas, probes, lights, wicks, vents, panels.

The group `lib/details.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.10`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import details as details_lib


@step(out="../STEP/details.step")
def details():
    return details_lib.build()


if __name__ == "__main__":
    details()
