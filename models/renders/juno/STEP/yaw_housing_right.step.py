#!/usr/bin/env python3
"""Right yaw housing mesh source for the juno URDF (part-local frame, mm).

The compound matches `juno_parts.joints.build_yaw_housing("right")` exactly; the URDF
link frame coincides with this part-local frame (yaw housing link (shoulder-roll joint center at the origin)).
"""

from __future__ import annotations

import sys
from pathlib import Path

JUNO_ROOT = Path(__file__).resolve().parents[1]
if str(JUNO_ROOT) not in sys.path:
    sys.path.insert(0, str(JUNO_ROOT))

from juno_parts.joints import build_yaw_housing


def gen_step():
    return build_yaw_housing("right")
