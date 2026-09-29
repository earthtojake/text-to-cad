"""Radial system model: crankcase — split power-section crankcase, cylinder pads, studs, main-bearing housings.

A sub-assembly of the engine: the parts `lib/crankcase.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/crankcase.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import crankcase as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/crankcase.step", materials=materials_for("crankcase", impl.MATERIALS))
def crankcase():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/crankcase.py build() produced no parts")
    return material_compound(parts, "crankcase", impl.MATERIALS)


if __name__ == "__main__":
    crankcase()
