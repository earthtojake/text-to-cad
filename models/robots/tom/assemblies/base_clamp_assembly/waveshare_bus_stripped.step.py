#!/usr/bin/env python3
"""
Stripped Waveshare bus board envelope for base-clamp fit checks.

This intentionally models only the PCB outline and the four M2.5 mounting
holes, leaving connectors and electronics out so the clamp assembly stays easy
to inspect.
"""

from __future__ import annotations

from pathlib import Path

import build123d


PART_NAME = Path(__file__).stem
BOARD_X_MIN_MM = -0.390013
BOARD_X_MAX_MM = 42.401989
BOARD_Y_MIN_MM = -0.012095
BOARD_Y_MAX_MM = 33.012075
BOARD_THICKNESS_MM = 1.6
MOUNT_HOLE_RADIUS_MM = 1.25
CUT_EXTENSION_MM = 0.5
BOARD_COLOR = build123d.Color(0.08, 0.24, 0.2, 1.0)

MOUNT_HOLE_CENTERS_XY_MM: tuple[tuple[float, float], ...] = (
    (2.4930065, 2.4999875),
    (2.4930065, 30.4999925),
    (39.493009, 2.4999875),
    (39.505008000000004, 30.4999925),
)


def _make_z_cylinder(*, radius: float, x: float, y: float, z_min: float, z_max: float) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        z_max - z_min,
        plane=build123d.Plane(
            origin=build123d.Vector(x, y, z_min),
            z_dir=build123d.Vector(0.0, 0.0, 1.0),
        ),
    )


def build_step() -> build123d.Solid:
    board: build123d.Shape = build123d.Solid.make_box(
        BOARD_X_MAX_MM - BOARD_X_MIN_MM,
        BOARD_Y_MAX_MM - BOARD_Y_MIN_MM,
        BOARD_THICKNESS_MM,
        plane=build123d.Plane(
            origin=build123d.Vector(BOARD_X_MIN_MM, BOARD_Y_MIN_MM, 0.0),
            z_dir=build123d.Vector(0.0, 0.0, 1.0),
        ),
    )

    for x, y in MOUNT_HOLE_CENTERS_XY_MM:
        board = board.cut(
            _make_z_cylinder(
                radius=MOUNT_HOLE_RADIUS_MM,
                x=x,
                y=y,
                z_min=-CUT_EXTENSION_MM,
                z_max=BOARD_THICKNESS_MM + CUT_EXTENSION_MM,
            )
        )

    solids = list(board.solids())
    if len(solids) != 1:
        raise RuntimeError(f"Expected one stripped bus solid, found {len(solids)}")

    stripped_bus = solids[0]
    stripped_bus.label = PART_NAME
    stripped_bus.color = BOARD_COLOR
    print(
        "Waveshare bus stripped "
        f"size={BOARD_X_MAX_MM - BOARD_X_MIN_MM:.3f}x"
        f"{BOARD_Y_MAX_MM - BOARD_Y_MIN_MM:.3f}x{BOARD_THICKNESS_MM:.3f} mm, "
        f"mount_holes={len(MOUNT_HOLE_CENTERS_XY_MM)}, "
        f"hole_diameter={2.0 * MOUNT_HOLE_RADIUS_MM:.3f} mm"
    )
    return stripped_bus


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
