"""Mirror entry: one round bar-end mirror (rider-left instance shown).

The assembly instances this geometry twice, one per handlebar side.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import trim as T


@step(out="../STEP/mirror.step")
def mirror():
    return bd.Compound(children=T.build_mirror(1.0), label="mirror")


if __name__ == "__main__":
    mirror()
