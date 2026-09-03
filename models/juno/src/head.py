"""Head mesh source for the juno URDF (part-local frame, mm).

The compound matches `lib.head.build_head()` exactly; the URDF
link frame coincides with this part-local frame (head link (neck-pitch joint center at the origin)).
"""

from __future__ import annotations

from cadgen import step
from cadgen import threemf

from lib.head import build_head


@step(out="../STEP/head.step")
@threemf(out="../3MF/head.3mf")
def head():
    return build_head()


if __name__ == "__main__":
    head()
