"""Radial system model: pushrods — 18 pushrods, 18 pushrod tubes, packing nuts, connectors.

A sub-assembly of the engine: the parts `lib/pushrods.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/pushrods.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import pushrods as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/pushrods.step", materials=materials_for("pushrods", impl.MATERIALS))
def pushrods():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/pushrods.py build() produced no parts")
    return material_compound(parts, "pushrods", impl.MATERIALS)


if __name__ == "__main__":
    pushrods()
