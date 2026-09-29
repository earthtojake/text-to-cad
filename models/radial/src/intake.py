"""Radial system model: intake — 9 intake pipes, couplings, carburettor.

A sub-assembly of the engine: the parts `lib/intake.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/intake.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import intake as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/intake.step", materials=materials_for("intake", impl.MATERIALS))
def intake():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/intake.py build() produced no parts")
    return material_compound(parts, "intake", impl.MATERIALS)


if __name__ == "__main__":
    intake()
