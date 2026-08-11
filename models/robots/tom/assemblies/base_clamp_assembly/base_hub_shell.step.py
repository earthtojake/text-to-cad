#!/usr/bin/env python3
"""Generate a lightweight printed shell that keys into the base clamp slots."""

from __future__ import annotations

import sys
from pathlib import Path

import build123d

ASSEMBLY_DIR = Path(__file__).resolve().parent
if str(ASSEMBLY_DIR) not in sys.path:
    sys.path.insert(0, str(ASSEMBLY_DIR))

import sys as _sys
from pathlib import Path as _Path
_TOM_DIR = _Path(__file__).resolve().parents[2]
if str(_TOM_DIR) not in _sys.path:
    _sys.path.insert(0, str(_TOM_DIR))
from robot_common.step_entry import load_step_entry

base_clamp = load_step_entry("base_clamp")


DISPLAY_NAME = "Base Hub Shell"
PLASTIC_SHELL_COLOR = build123d.Color(0.18, 0.42, 0.78, 0.34)
PLASTIC_SHELL_EDGE_INSET_MM = 3.0
PLASTIC_SHELL_WALL_MM = 2.4
PLASTIC_SHELL_HEIGHT_MM = 18.0
PLASTIC_SHELL_BOTTOM_LIFT_MM = 0.15
PLASTIC_SHELL_LEFT_CHAMFER_X_MM = 13.0
PLASTIC_SHELL_LEFT_CHAMFER_Z_MM = 10.0
PLASTIC_SHELL_TAB_CLEARANCE_MM = 0.65
PLASTIC_SHELL_TAB_LENGTH_CLEARANCE_MM = 4.0
PLASTIC_SHELL_TAB_DROP_BELOW_PLATE_MM = 0.4
PLASTIC_SHELL_TAB_RISE_ABOVE_PLATE_MM = 1.4
PLASTIC_SHELL_RIGHT_SERVICE_OPENING_EXTRA_MM = 0.5


def _shell_outline_points(
    layout: base_clamp.BracketLayout,
    *,
    inset: float,
) -> tuple[tuple[float, float], ...]:
    x_min = layout.x_min + PLASTIC_SHELL_EDGE_INSET_MM + inset
    x_max = layout.neck_start_x - PLASTIC_SHELL_EDGE_INSET_MM - inset
    z_min = layout.z_min + PLASTIC_SHELL_EDGE_INSET_MM + inset
    z_max = layout.z_max - PLASTIC_SHELL_EDGE_INSET_MM - inset
    chamfer_x = x_min + max(PLASTIC_SHELL_LEFT_CHAMFER_X_MM - inset, PLASTIC_SHELL_WALL_MM)
    lower_left_z = z_min + max(PLASTIC_SHELL_LEFT_CHAMFER_Z_MM - inset, PLASTIC_SHELL_WALL_MM)
    upper_left_z = z_max - max(PLASTIC_SHELL_LEFT_CHAMFER_Z_MM - inset, PLASTIC_SHELL_WALL_MM)
    if x_max <= chamfer_x or upper_left_z <= lower_left_z:
        raise RuntimeError("Plastic shell outline collapsed; reduce shell inset or wall thickness")
    return (
        (chamfer_x, z_min),
        (x_max, z_min),
        (x_max, z_max),
        (chamfer_x, z_max),
        (x_min, upper_left_z),
        (x_min, lower_left_z),
    )


def _make_oriented_tab(
    *,
    x: float,
    z: float,
    length: float,
    width: float,
    rotation_deg: float,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    import math

    angle = math.radians(rotation_deg)
    unit_x = math.cos(angle)
    unit_z = math.sin(angle)
    perp_x = -unit_z
    perp_z = unit_x
    half_length = 0.5 * length
    half_width = 0.5 * width
    points = (
        (
            x - (half_length * unit_x) - (half_width * perp_x),
            z - (half_length * unit_z) - (half_width * perp_z),
        ),
        (
            x + (half_length * unit_x) - (half_width * perp_x),
            z + (half_length * unit_z) - (half_width * perp_z),
        ),
        (
            x + (half_length * unit_x) + (half_width * perp_x),
            z + (half_length * unit_z) + (half_width * perp_z),
        ),
        (
            x - (half_length * unit_x) + (half_width * perp_x),
            z - (half_length * unit_z) + (half_width * perp_z),
        ),
    )
    return base_clamp._make_xz_outline_solid(points, y_min=y_min, y_max=y_max)


def build_shell() -> build123d.Solid:
    layout = base_clamp._build_bracket_layout()
    y_min = layout.y_max + PLASTIC_SHELL_BOTTOM_LIFT_MM
    y_max = y_min + PLASTIC_SHELL_HEIGHT_MM
    outer = base_clamp._make_xz_outline_solid(
        _shell_outline_points(layout, inset=0.0),
        y_min=y_min,
        y_max=y_max,
    )
    inner = base_clamp._make_xz_outline_solid(
        _shell_outline_points(layout, inset=PLASTIC_SHELL_WALL_MM),
        y_min=y_min - base_clamp.CUT_EXTENSION_MM,
        y_max=y_max + base_clamp.CUT_EXTENSION_MM,
    )
    shell = outer.cut(inner)
    shell_x_max = layout.neck_start_x - PLASTIC_SHELL_EDGE_INSET_MM
    shell = shell.cut(
        base_clamp._make_box(
            x_min=shell_x_max
            - PLASTIC_SHELL_WALL_MM
            - PLASTIC_SHELL_RIGHT_SERVICE_OPENING_EXTRA_MM,
            x_max=shell_x_max + PLASTIC_SHELL_RIGHT_SERVICE_OPENING_EXTRA_MM,
            y_min=y_min - base_clamp.CUT_EXTENSION_MM,
            y_max=y_max + base_clamp.CUT_EXTENSION_MM,
            z_min=layout.z_min,
            z_max=layout.z_max,
        )
    )

    tab_length = base_clamp.BASE_PLATE_HUB_SLOT_LENGTH_MM - PLASTIC_SHELL_TAB_LENGTH_CLEARANCE_MM
    tab_width = base_clamp.BASE_PLATE_HUB_SLOT_WIDTH_MM - PLASTIC_SHELL_TAB_CLEARANCE_MM
    if tab_length <= tab_width:
        raise RuntimeError(
            f"Plastic shell tab is too short: {tab_length:.3f} x {tab_width:.3f} mm"
        )
    for x, z, _slot_length, _slot_width, rotation_deg in base_clamp._top_plate_hub_slot_specs(layout):
        shell = shell.fuse(
            _make_oriented_tab(
                x=x,
                z=z,
                length=tab_length,
                width=tab_width,
                rotation_deg=rotation_deg,
                y_min=layout.y_min - PLASTIC_SHELL_TAB_DROP_BELOW_PLATE_MM,
                y_max=layout.y_max + PLASTIC_SHELL_TAB_RISE_ABOVE_PLATE_MM,
            )
        )

    shell = base_clamp._as_single_solid(shell)
    shell.color = PLASTIC_SHELL_COLOR
    print(
        f"{DISPLAY_NAME}: "
        f"wall={PLASTIC_SHELL_WALL_MM:.3f} mm, "
        f"height={PLASTIC_SHELL_HEIGHT_MM:.3f} mm, "
        f"right_service_opening_start_x={shell_x_max - PLASTIC_SHELL_WALL_MM - PLASTIC_SHELL_RIGHT_SERVICE_OPENING_EXTRA_MM:.3f} mm, "
        f"tabs={len(base_clamp._top_plate_hub_slot_specs(layout))}, "
        f"tab_size={tab_length:.3f}x{tab_width:.3f} mm"
    )
    return shell


def gen_step() -> dict[str, object]:
    return {
        "shape": build_shell(),
    }


if __name__ == "__main__":
    gen_step()
