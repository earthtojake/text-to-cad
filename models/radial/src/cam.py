"""Radial system model: cam — cam ring, cam idler, 18 tappets + rollers.

A sub-assembly of the engine: the parts `lib/cam.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/cam.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import cam as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/cam.step", materials=materials_for("cam", impl.MATERIALS))
def cam():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/cam.py build() produced no parts")
    return material_compound(parts, "cam", impl.MATERIALS)


if __name__ == "__main__":
    cam()
