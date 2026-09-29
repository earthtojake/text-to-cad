"""Radial system model: ignition — harness ring, 18 leads, plug elbows, magneto feeds.

A sub-assembly of the engine: the parts `lib/ignition.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/ignition.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import ignition as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/ignition.step", materials=materials_for("ignition", impl.MATERIALS))
def ignition():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/ignition.py build() produced no parts")
    return material_compound(parts, "ignition", impl.MATERIALS)


if __name__ == "__main__":
    ignition()
