from __future__ import annotations
from cadgen import step
from math import cos, radians, sin, tau

from cadgen import build123d as bd

from lib.part_common import circular_edges, polar_point, safe_fillet


BARREL_DIAMETER = 36.0
BARREL_HEIGHT = 70.0

FIN_COUNT = 12
FIN_DIAMETER = 62.0
FIN_THICKNESS = 2.0
FIN_Z_VALUES = tuple(10.0 + 5.0 * index for index in range(FIN_COUNT))

BASE_FLANGE_DIAMETER = 70.0
BASE_FLANGE_THICKNESS = 8.0
MOUNT_HOLE_COUNT = 6
MOUNT_HOLE_DIAMETER = 5.0
MOUNT_BOLT_CIRCLE_DIAMETER = 56.0

TOP_CAP_DIAMETER = 44.0
TOP_CAP_BOTTOM_Z = 70.0
TOP_CAP_HEIGHT = 8.0

BOSS_DIAMETER = 12.0
BOSS_LENGTH = 24.0
BOSS_ANGLE_DEGREES = 35.0
BOSS_BORE_DIAMETER = 5.0

EDGE_FILLET = 0.95


def _boss_center() -> tuple[float, float, float]:
    angle = radians(BOSS_ANGLE_DEGREES)
    start = (TOP_CAP_DIAMETER / 2.0 - 1.0, 0.0, TOP_CAP_BOTTOM_Z + TOP_CAP_HEIGHT / 2.0)
    direction = (cos(angle), 0.0, sin(angle))
    return (
        start[0] + direction[0] * BOSS_LENGTH / 2.0,
        0.0,
        start[2] + direction[2] * BOSS_LENGTH / 2.0,
    )


def _edge_fillets(part):
    edges = []
    for z_pos in FIN_Z_VALUES:
        edges.extend(circular_edges(part, radius=FIN_DIAMETER / 2.0, axis="z", coordinate=z_pos))
        edges.extend(circular_edges(part, radius=FIN_DIAMETER / 2.0, axis="z", coordinate=z_pos + FIN_THICKNESS))
    edges.extend(circular_edges(part, radius=BASE_FLANGE_DIAMETER / 2.0, axis="z", coordinate=0.0))
    edges.extend(circular_edges(part, radius=BASE_FLANGE_DIAMETER / 2.0, axis="z", coordinate=BASE_FLANGE_THICKNESS))
    return edges


@step(out="../STEP/radial_engine_cylinder.step")
def radial_engine_cylinder():
    """Return the radial-engine-style cylinder model in millimeters."""
    boss_rotation_y = 90.0 - BOSS_ANGLE_DEGREES
    boss_center = _boss_center()

    with bd.BuildPart() as cylinder:
        bd.Cylinder(
            radius=BARREL_DIAMETER / 2.0,
            height=BARREL_HEIGHT,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
        )

        bd.Cylinder(
            radius=BASE_FLANGE_DIAMETER / 2.0,
            height=BASE_FLANGE_THICKNESS,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
            mode=bd.Mode.ADD,
        )

        for z_pos in FIN_Z_VALUES:
            with bd.Locations(bd.Location((0.0, 0.0, z_pos))):
                bd.Cylinder(
                    radius=FIN_DIAMETER / 2.0,
                    height=FIN_THICKNESS,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.ADD,
                )

        with bd.Locations(bd.Location((0.0, 0.0, TOP_CAP_BOTTOM_Z))):
            bd.Cylinder(
                radius=TOP_CAP_DIAMETER / 2.0,
                height=TOP_CAP_HEIGHT,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.ADD,
            )

        with bd.Locations(bd.Location(boss_center)):
            bd.Cylinder(
                radius=BOSS_DIAMETER / 2.0,
                height=BOSS_LENGTH,
                rotation=(0.0, boss_rotation_y, 0.0),
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER),
                mode=bd.Mode.ADD,
            )

        for index in range(MOUNT_HOLE_COUNT):
            x_pos, y_pos = polar_point(MOUNT_BOLT_CIRCLE_DIAMETER / 2.0, tau * index / MOUNT_HOLE_COUNT)
            with bd.Locations(bd.Location((x_pos, y_pos, -1.0))):
                bd.Cylinder(
                    radius=MOUNT_HOLE_DIAMETER / 2.0,
                    height=BASE_FLANGE_THICKNESS + 2.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.SUBTRACT,
                )

        with bd.Locations(bd.Location(boss_center)):
            bd.Cylinder(
                radius=BOSS_BORE_DIAMETER / 2.0,
                height=BOSS_LENGTH + 6.0,
                rotation=(0.0, boss_rotation_y, 0.0),
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER),
                mode=bd.Mode.SUBTRACT,
            )

    part = cylinder.part
    part = safe_fillet(part, _edge_fillets(part), radius=EDGE_FILLET)
    part.label = "radial_engine_cylinder_cooling_fins"
    return part


if __name__ == "__main__":
    radial_engine_cylinder()
