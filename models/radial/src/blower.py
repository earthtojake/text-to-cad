"""Radial system model: blower — blower section, diffuser, impeller, impeller drive gears.

A sub-assembly of the engine: the parts `lib/blower.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/blower.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import blower as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/blower.step", materials=materials_for("blower", impl.MATERIALS))
def blower():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/blower.py build() produced no parts")
    return material_compound(parts, "blower", impl.MATERIALS)


if __name__ == "__main__":
    blower()
