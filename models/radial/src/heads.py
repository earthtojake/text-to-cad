"""Radial system model: heads — 9 aluminium heads: deep fins, rocker boxes, covers, guides, seats, 18 spark plugs.

A sub-assembly of the engine: the parts `lib/heads.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/heads.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import heads as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/heads.step", materials=materials_for("heads", impl.MATERIALS))
def heads():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/heads.py build() produced no parts")
    return material_compound(parts, "heads", impl.MATERIALS)


if __name__ == "__main__":
    heads()
