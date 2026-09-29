"""Radial system model: pistons — 9 pistons, 54 rings, 9 wrist pins + plugs.

A sub-assembly of the engine: the parts `lib/pistons.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/pistons.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import pistons as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/pistons.step", materials=materials_for("pistons", impl.MATERIALS))
def pistons():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/pistons.py build() produced no parts")
    return material_compound(parts, "pistons", impl.MATERIALS)


if __name__ == "__main__":
    pistons()
