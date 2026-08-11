#!/usr/bin/env python3
"""
M2 spacer for the tom v2 base clamp servo mount.

The simplified body represents an off-the-shelf M2 PCB/servo spacer. It is
authored upright on +Z so the assembly can drop it directly between the base
plate and the selected underside mount face on the servo.
"""

from __future__ import annotations

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
M2_THREAD_MINOR_RADIUS_MM = 0.8
THREAD_ENTRY_RADIUS_MM = 1.05
THREAD_ENTRY_DEPTH_MM = 0.6
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


def build_step() -> build123d.Shape:
    height = base_clamp.SERVO_STANDOFF_HEIGHT_MM
    outer_radius = 0.5 * base_clamp.SERVO_STANDOFF_BODY_DIAMETER_MM
    if height <= 0.0:
        raise ValueError("SERVO_STANDOFF_HEIGHT_MM must be positive")
    if outer_radius <= THREAD_ENTRY_RADIUS_MM:
        raise ValueError("M2 spacer outer diameter is too small for the thread entry")

    body: build123d.Shape = _make_z_cylinder(radius=outer_radius, z_min=0.0, z_max=height)
    body = body.cut(
        _make_z_cylinder(
            radius=M2_THREAD_MINOR_RADIUS_MM,
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
        raise RuntimeError(f"Expected one M2 spacer solid, found {len(solids)}")

    spacer = solids[0]
    spacer.label = PART_NAME
    spacer.color = BRASS_COLOR
    print(
        "M2 spacer "
        f"height={height:.3f} mm, "
        f"outer_diameter={base_clamp.SERVO_STANDOFF_BODY_DIAMETER_MM:.3f} mm, "
        f"thread_minor_diameter={2.0 * M2_THREAD_MINOR_RADIUS_MM:.3f} mm"
    )
    return spacer


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
