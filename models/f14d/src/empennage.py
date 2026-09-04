"""F-14D system model: empennage — fins, rudders, stabilators, ventral fins.

The group `lib/empennage.py` builds, already on its gear stance, as one model
with its own STEP, record and worker. `f14d.py` links it as occurrence
`o1.6`; rebuild `f14d.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import step

from lib import empennage as empennage_lib


@step(out="../STEP/empennage.step")
def empennage():
    return empennage_lib.build()


if __name__ == "__main__":
    empennage()
