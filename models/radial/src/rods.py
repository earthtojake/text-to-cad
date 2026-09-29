"""Radial system model: rods — master rod + flange, 8 knuckle pins + retainers, crankpin bearing, 8 articulating rods.

A sub-assembly of the engine: the parts `lib/rods.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/rods.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import rods as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/rods.step", materials=materials_for("rods", impl.MATERIALS))
def rods():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/rods.py build() produced no parts")
    return material_compound(parts, "rods", impl.MATERIALS)


if __name__ == "__main__":
    rods()
