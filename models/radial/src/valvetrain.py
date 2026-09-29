"""Radial system model: valvetrain — 18 valves, springs, retainers, keepers, 18 rockers + shafts.

A sub-assembly of the engine: the parts `lib/valvetrain.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/valvetrain.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import valvetrain as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/valvetrain.step", materials=materials_for("valvetrain", impl.MATERIALS))
def valvetrain():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/valvetrain.py build() produced no parts")
    return material_compound(parts, "valvetrain", impl.MATERIALS)


if __name__ == "__main__":
    valvetrain()
