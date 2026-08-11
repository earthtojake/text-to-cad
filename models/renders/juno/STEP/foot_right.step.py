#!/usr/bin/env python3
"""Right foot mesh source for the juno URDF (part-local frame, mm).

The compound matches `juno_parts.legs.build_foot("right")` exactly; the URDF
link frame coincides with this part-local frame (foot link (ankle-roll joint center at the origin)).
"""

from __future__ import annotations

import sys
from pathlib import Path

JUNO_ROOT = Path(__file__).resolve().parents[1]
if str(JUNO_ROOT) not in sys.path:
    sys.path.insert(0, str(JUNO_ROOT))

from juno_parts.legs import build_foot


def gen_step():
    return build_foot("right")
