"""Radial system model: reduction — planetary reduction: bell gear, fixed sun, 6 planets, carrier, propeller shaft, thrust bearing.

A sub-assembly of the engine: the parts `lib/reduction.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/reduction.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import reduction as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/reduction.step", materials=materials_for("reduction", impl.MATERIALS))
def reduction():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/reduction.py build() produced no parts")
    return material_compound(parts, "reduction", impl.MATERIALS)


if __name__ == "__main__":
    reduction()
