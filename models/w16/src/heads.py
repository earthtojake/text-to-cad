"""W16 system model: heads — two heads, plugs, core plugs, head bolts.

A sub-assembly of the engine: the parts `lib/heads.py` builds, as one model
with its own STEP, its own record and its own worker. `w16.py` links it as
occurrence `o1.4`; rebuild `w16.py` to pick up a change here.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import heads as heads_lib
from lib import spec as S


@step(out="../STEP/heads.step")
def heads():
    parts = heads_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("heads.build() produced no parts")
    return bd.Compound(children=parts, label="heads")


if __name__ == "__main__":
    heads()
