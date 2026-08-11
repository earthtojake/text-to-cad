#!/usr/bin/env python3
"""
6 mm M2.5 hex spacer for the Waveshare bus board on the tom v2 base clamp.

The simplified body represents an off-the-shelf female-female hex spacer. It is
authored upright on +Z so the assembly can place it between the clamp plate and
the Waveshare board mounting holes.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ASSEMBLY_DIR = Path(__file__).resolve().parent
if str(ASSEMBLY_DIR) not in sys.path:
    sys.path.insert(0, str(ASSEMBLY_DIR))

import build123d

import sys as _sys
from pathlib import Path as _Path
_TOM_DIR = _Path(__file__).resolve().parents[2]
if str(_TOM_DIR) not in _sys.path:
    _sys.path.insert(0, str(_TOM_DIR))
from robot_common.step_entry import load_step_entry

base_clamp = load_step_entry("base_clamp")


PART_NAME = Path(__file__).stem
M2_5_THREAD_MINOR_RADIUS_MM = 0.5 * 2.05
THREAD_ENTRY_RADIUS_MM = 1.35
THREAD_ENTRY_DEPTH_MM = 0.7
CUT_EXTENSION_MM = 0.5
BRASS_COLOR = build123d.Color(0.82, 0.63, 0.31, 1.0)


def _make_z_cylinder(*, radius: float, z_min: float, z_max: float) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        z_max - z_min,
        plane=build123d.Plane(
            origin=build123d.Vector(0.0, 0.0, z_min),
            z_dir=build123d.Vector(0.0, 0.0, 1.0),
        ),
    )


def _make_hex_prism(*, across_flats: float, height: float) -> build123d.Shape:
    circumradius = across_flats / math.sqrt(3.0)
    with build123d.BuildPart() as spacer:
        with build123d.BuildSketch():
            build123d.RegularPolygon(circumradius, 6, rotation=30.0)
        build123d.extrude(amount=height)
    return spacer.part


def build_step() -> build123d.Shape:
    height = base_clamp.SERVO_BUS_STANDOFF_HEIGHT_MM
    across_flats = base_clamp.SERVO_BUS_STANDOFF_HEX_ACROSS_FLATS_MM
    if height <= 0.0:
        raise ValueError("SERVO_BUS_STANDOFF_HEIGHT_MM must be positive")
    if across_flats <= (2.0 * THREAD_ENTRY_RADIUS_MM):
        raise ValueError("M2.5 spacer hex body is too small for the thread entry")

    body = _make_hex_prism(across_flats=across_flats, height=height)
    body = body.cut(
        _make_z_cylinder(
            radius=M2_5_THREAD_MINOR_RADIUS_MM,
            z_min=-CUT_EXTENSION_MM,
            z_max=height + CUT_EXTENSION_MM,
        )
    )
    for z_min in (0.0, height - THREAD_ENTRY_DEPTH_MM):
        body = body.cut(
            _make_z_cylinder(
                radius=THREAD_ENTRY_RADIUS_MM,
                z_min=z_min - CUT_EXTENSION_MM,
                z_max=z_min + THREAD_ENTRY_DEPTH_MM + CUT_EXTENSION_MM,
            )
        )

    solids = list(body.solids())
    if len(solids) != 1:
        raise RuntimeError(f"Expected one M2.5 hex spacer solid, found {len(solids)}")

    spacer = solids[0]
    spacer.label = PART_NAME
    spacer.color = BRASS_COLOR
    print(
        "M2.5 bus hex spacer "
        f"height={height:.3f} mm, "
        f"across_flats={across_flats:.3f} mm, "
        f"thread_minor_diameter={2.0 * M2_5_THREAD_MINOR_RADIUS_MM:.3f} mm"
    )
    return spacer


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
