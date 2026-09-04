"""W16 system model: covers — cam covers, coils, plug wells, breathers.

A sub-assembly of the engine: the parts `lib/covers.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.8`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import covers as covers_lib
from lib import spec as S


@step(out="../STEP/covers.step")
def covers():
    parts = covers_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("covers.build() produced no parts")
    return bd.Compound(children=parts, label="covers")


if __name__ == "__main__":
    covers()
