"""Radial system model: nose — nose case, tappet guides, thrust-bearing housing, governor pad.

A sub-assembly of the engine: the parts `lib/nose.py` builds, as one model with
its own STEP, record and worker. `radial.py` links it; rebuild `radial.py` to pick
up a change here. Finishes: `lib/nose.py:MATERIALS`.
"""

from __future__ import annotations

from cadgen import step

from lib import nose as impl
from lib.palette import material_compound, materials_for


@step(out="../STEP/nose.step", materials=materials_for("nose", impl.MATERIALS))
def nose():
    parts = impl.build()
    if not parts:
        raise RuntimeError("lib/nose.py build() produced no parts")
    return material_compound(parts, "nose", impl.MATERIALS)


if __name__ == "__main__":
    nose()
