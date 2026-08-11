#!/usr/bin/env python3
"""Head mesh source for the juno URDF (part-local frame, mm).

The compound matches `juno_parts.head.build_head()` exactly; the URDF
link frame coincides with this part-local frame (head link (neck-pitch joint center at the origin)).
"""

from __future__ import annotations

import sys
from pathlib import Path

JUNO_ROOT = Path(__file__).resolve().parents[1]
if str(JUNO_ROOT) not in sys.path:
    sys.path.insert(0, str(JUNO_ROOT))

from juno_parts.head import build_head


def gen_step():
    return build_head()
