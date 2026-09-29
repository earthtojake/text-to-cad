"""Radial system model: mount — engine mount ring, bosses, bushings, bolts.

A sub-assembly of the engine: the parts `lib/mount.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/mount.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import mount as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/mount.step", materials=materials_for("mount", impl.MATERIALS))
def mount():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/mount.py build() produced no parts")
    return material_compound(parts, "mount", impl.MATERIALS)


if __name__ == "__main__":
    mount()
