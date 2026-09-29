"""Radial system model: crankshaft — two-piece single-throw crankshaft, counterweights, main bearings, drive gears.

A sub-assembly of the engine: the parts `lib/crankshaft.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/crankshaft.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import crankshaft as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/crankshaft.step", materials=materials_for("crankshaft", impl.MATERIALS))
def crankshaft():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/crankshaft.py build() produced no parts")
    return material_compound(parts, "crankshaft", impl.MATERIALS)


if __name__ == "__main__":
    crankshaft()
