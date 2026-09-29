"""Radial system model: barrels — 9 finned steel cylinder barrels + hold-down nuts.

A sub-assembly of the engine: the parts `lib/barrels.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/barrels.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import barrels as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/barrels.step", materials=materials_for("barrels", impl.MATERIALS))
def barrels():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/barrels.py build() produced no parts")
    return material_compound(parts, "barrels", impl.MATERIALS)


if __name__ == "__main__":
    barrels()
