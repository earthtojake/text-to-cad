"""W16 system model: oil_system — dry-sump pan, windage tray, pumps, filter.

A sub-assembly of the engine: the parts `lib/oil_system.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.9`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import oil_system as oil_system_lib
from lib import spec as S


@step(out="../STEP/oil_system.step",
      mesh_tolerance=0.0006, mesh_angular_tolerance=0.3)
def oil_system():
    parts = oil_system_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("oil_system.build() produced no parts")
    return bd.Compound(children=parts, label="oil_system")


if __name__ == "__main__":
    oil_system()
