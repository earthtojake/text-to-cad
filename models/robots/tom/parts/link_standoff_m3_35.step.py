#!/usr/bin/env python3
"""
35 mm M3 female-female round aluminum spacer for the tom v2 link bracket pair.

The part is authored centered on the link frame Y axis so assemblies can place
it by translating to the bracket web hole center. The simplified thread is a
continuous M3 minor-diameter bore. Outside dimensions match the MECCANIXITY
M3x35 round aluminum female-threaded spacer: 5 mm OD, 35 mm length.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))

import build123d

import link_common as lc


PART_NAME = Path(__file__).stem

STANDOFF_LENGTH_MM = float(os.environ.get("TOM_V2_LINK_STANDOFF_LENGTH_MM", "35.0"))
ROUND_OUTER_DIAMETER_MM = float(os.environ.get("TOM_V2_LINK_STANDOFF_OD_MM", "5.0"))
M3_THREAD_MINOR_RADIUS_MM = float(os.environ.get("TOM_V2_LINK_STANDOFF_THREAD_MINOR_RADIUS_MM", "1.25"))
END_ENTRY_RADIUS_MM = float(os.environ.get("TOM_V2_LINK_STANDOFF_THREAD_ENTRY_RADIUS_MM", "1.65"))
END_ENTRY_DEPTH_MM = 1.2
CUT_EXTENSION_MM = 1.0
SILVER_ALUMINUM_COLOR = build123d.Color(0.78, 0.80, 0.82, 1.0)


def build_step() -> build123d.Shape:
    if STANDOFF_LENGTH_MM <= 0.0:
        raise ValueError("TOM_V2_LINK_STANDOFF_LENGTH_MM must be positive")
    if ROUND_OUTER_DIAMETER_MM <= 2.0 * END_ENTRY_RADIUS_MM:
        raise ValueError("Round body OD is too small for the requested M3 thread entry")

    body: build123d.Shape = lc.make_y_cylinder(
        x=0.0,
        z=0.0,
        radius=0.5 * ROUND_OUTER_DIAMETER_MM,
        y_min=-0.5 * STANDOFF_LENGTH_MM,
        y_max=0.5 * STANDOFF_LENGTH_MM,
    )
    body = body.cut(
        lc.make_y_cylinder(
            x=0.0,
            z=0.0,
            radius=M3_THREAD_MINOR_RADIUS_MM,
            y_min=-0.5 * STANDOFF_LENGTH_MM - CUT_EXTENSION_MM,
            y_max=0.5 * STANDOFF_LENGTH_MM + CUT_EXTENSION_MM,
        )
    )
    for end_y in (-0.5 * STANDOFF_LENGTH_MM, 0.5 * STANDOFF_LENGTH_MM - END_ENTRY_DEPTH_MM):
        body = body.cut(
            lc.make_y_cylinder(
                x=0.0,
                z=0.0,
                radius=END_ENTRY_RADIUS_MM,
                y_min=end_y - CUT_EXTENSION_MM,
                y_max=end_y + END_ENTRY_DEPTH_MM + CUT_EXTENSION_MM,
            )
        )

    solids = body.solids()
    if len(solids) != 1:
        raise RuntimeError(f"Expected one standoff solid, found {len(solids)}")

    body.label = PART_NAME
    body.color = SILVER_ALUMINUM_COLOR
    bb = body.bounding_box()
    print(
        "M3 female-female round aluminum link spacer "
        f"length={bb.size.Y:.3f} mm, outer_diameter={ROUND_OUTER_DIAMETER_MM:.3f} mm, "
        f"thread_minor_diameter={2.0 * M3_THREAD_MINOR_RADIUS_MM:.3f} mm"
    )
    return body


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
