#!/usr/bin/env python3
"""pinky_distal mesh source for the lyra URDF (part-local frame, mm).

The compound matches `lyra_parts.digits.build_finger_distal("pinky")` exactly; the
URDF link frame coincides with this part-local frame.
"""

from __future__ import annotations

import sys
from pathlib import Path

LYRA_ROOT = Path(__file__).resolve().parents[1]
if str(LYRA_ROOT) not in sys.path:
    sys.path.insert(0, str(LYRA_ROOT))

from lyra_parts.digits import build_finger_distal


def gen_step():
    return build_finger_distal("pinky")
