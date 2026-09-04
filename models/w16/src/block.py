"""W16 system model: block — block casting + main caps + shells + block fasteners.

A sub-assembly of the engine: the parts `lib/block.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.1`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import block as block_lib
from lib import spec as S


@step(out="../STEP/block.step",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def block():
    parts = block_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("block.build() produced no parts")
    return bd.Compound(children=parts, label="block")


if __name__ == "__main__":
    block()
