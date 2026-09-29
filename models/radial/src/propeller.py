"""Radial system model: propeller — hub, three blades, spinner, retention hardware.

A sub-assembly of the engine: the parts `lib/propeller.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/propeller.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import propeller as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/propeller.step", materials=materials_for("propeller", impl.MATERIALS))
def propeller():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/propeller.py build() produced no parts")
    return material_compound(parts, "propeller", impl.MATERIALS)


if __name__ == "__main__":
    propeller()
