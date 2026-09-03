from __future__ import annotations
from cadgen import step
from math import cos, radians, sin

from cadgen import build123d as bd


BASE_DIAMETER = 90.0
BASE_THICKNESS = 5.0
COLUMN_DIAMETER = 14.0
COLUMN_HEIGHT = 140.0

TREAD_COUNT = 20
TREAD_THICKNESS = 4.0
TREAD_INNER_RADIUS = 10.0
TREAD_OUTER_RADIUS = 62.0
TREAD_SWEEP_DEGREES = 24.0
TREAD_FIRST_BOTTOM_Z = 4.0
TREAD_RISE = 6.0
TREAD_ROTATION_DEGREES = 18.0

HANDRAIL_RADIUS = 66.0
HANDRAIL_DIAMETER = 5.0
HANDRAIL_START_Z = 14.0
HANDRAIL_END_Z = 130.0
BALUSTER_DIAMETER = 3.0


def _polar_point(radius: float, angle_degrees: float) -> tuple[float, float]:
    angle = radians(angle_degrees)
    return (radius * cos(angle), radius * sin(angle))


def _make_base():
    with bd.BuildPart() as base:
        bd.Cylinder(
            radius=BASE_DIAMETER / 2.0,
            height=BASE_THICKNESS,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
        )
    part = base.part
    part.label = "base_disk"
    part.color = bd.Color(0.42, 0.43, 0.45, 1.0)
    return part


def _make_column():
    with bd.BuildPart() as column:
        bd.Cylinder(
            radius=COLUMN_DIAMETER / 2.0,
            height=COLUMN_HEIGHT,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
        )
    part = column.part
    part.label = "central_column"
    part.color = bd.Color(0.70, 0.72, 0.74, 1.0)
    return part


def _make_tread_profile():
    half_sweep = TREAD_SWEEP_DEGREES / 2.0
    with bd.BuildPart() as tread:
        with bd.BuildSketch(bd.Plane.XY):
            with bd.BuildLine():
                bd.CenterArc((0.0, 0.0), TREAD_OUTER_RADIUS, -half_sweep, TREAD_SWEEP_DEGREES)
                bd.Line(_polar_point(TREAD_OUTER_RADIUS, half_sweep), _polar_point(TREAD_INNER_RADIUS, half_sweep))
                bd.CenterArc((0.0, 0.0), TREAD_INNER_RADIUS, half_sweep, -TREAD_SWEEP_DEGREES)
                bd.Line(_polar_point(TREAD_INNER_RADIUS, -half_sweep), _polar_point(TREAD_OUTER_RADIUS, -half_sweep))
            bd.make_face()
        bd.extrude(amount=TREAD_THICKNESS)
    return tread.part


def _make_tread(index: int):
    angle = index * TREAD_ROTATION_DEGREES
    bottom_z = TREAD_FIRST_BOTTOM_Z + index * TREAD_RISE
    part = _make_tread_profile().moved(bd.Location((0.0, 0.0, bottom_z), (0.0, 0.0, angle)))
    part.label = f"helical_tread_{index + 1:02d}"
    part.color = bd.Color(0.78, 0.58, 0.35, 1.0)
    return part


def _handrail_center_z(angle_degrees: float) -> float:
    return HANDRAIL_START_Z + (HANDRAIL_END_Z - HANDRAIL_START_Z) * angle_degrees / 360.0


def _make_handrail():
    rail_height = HANDRAIL_END_Z - HANDRAIL_START_Z
    path = bd.Edge.make_helix(
        pitch=rail_height,
        height=rail_height,
        radius=HANDRAIL_RADIUS,
        center=(0.0, 0.0, HANDRAIL_START_Z),
    )
    profile_plane = bd.Plane(
        origin=(HANDRAIL_RADIUS, 0.0, HANDRAIL_START_Z),
        x_dir=(1.0, 0.0, 0.0),
        z_dir=path.tangent_at(0.0),
    )

    with bd.BuildPart() as rail:
        with bd.BuildSketch(profile_plane):
            bd.Circle(HANDRAIL_DIAMETER / 2.0)
        bd.sweep(path=path, is_frenet=True)
    part = rail.part
    part.label = "helical_handrail"
    part.color = bd.Color(0.22, 0.28, 0.34, 1.0)
    return part


def _make_baluster(index: int):
    angle = index * TREAD_ROTATION_DEGREES
    tread_top_z = TREAD_FIRST_BOTTOM_Z + index * TREAD_RISE + TREAD_THICKNESS
    rail_center_z = _handrail_center_z(angle)
    x_pos, y_pos = _polar_point(TREAD_OUTER_RADIUS, angle)
    with bd.BuildPart() as baluster:
        bd.Cylinder(
            radius=BALUSTER_DIAMETER / 2.0,
            height=rail_center_z - tread_top_z,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
        )
    part = baluster.part.moved(bd.Location((x_pos, y_pos, tread_top_z)))
    part.label = f"baluster_{index + 1:02d}"
    part.color = bd.Color(0.30, 0.33, 0.36, 1.0)
    return part


@step(out="../STEP/spiral_staircase.step")
def spiral_staircase():
    """Return the miniature spiral staircase model in millimeters."""
    parts = [_make_base(), _make_column()]
    parts.extend(_make_tread(index) for index in range(TREAD_COUNT))
    parts.append(_make_handrail())
    parts.extend(_make_baluster(index) for index in range(TREAD_COUNT))
    return bd.Compound(obj=parts, children=parts, label="spiral_staircase_helical_handrail")


if __name__ == "__main__":
    spiral_staircase()
