"""Radial system model: accessory — accessory case, 2 magnetos, starter, generator, fuel + oil pumps, oil sump.

A sub-assembly of the engine: the parts `lib/accessory.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/accessory.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import accessory as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/accessory.step", materials=materials_for("accessory", impl.MATERIALS))
def accessory():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/accessory.py build() produced no parts")
    return material_compound(parts, "accessory", impl.MATERIALS)


if __name__ == "__main__":
    accessory()
