"""Radial system model: exhaust — 9 stacks, collector ring, outlet, clamps.

A sub-assembly of the engine: the parts `lib/exhaust.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/exhaust.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import exhaust as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/exhaust.step", materials=materials_for("exhaust", impl.MATERIALS))
def exhaust():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/exhaust.py build() produced no parts")
    return material_compound(parts, "exhaust", impl.MATERIALS)


if __name__ == "__main__":
    exhaust()
