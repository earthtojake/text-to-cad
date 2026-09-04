"""W16 system model: camdrive — sprockets, chains, guides, tensioners.

A sub-assembly of the engine: the parts `lib/camdrive.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.7`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import camdrive as camdrive_lib
from lib import spec as S


@step(out="../STEP/camdrive.step",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def camdrive():
    parts = camdrive_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("camdrive.build() produced no parts")
    return bd.Compound(children=parts, label="camdrive")


if __name__ == "__main__":
    camdrive()
