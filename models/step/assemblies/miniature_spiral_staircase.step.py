from math import cos, radians, sin

from build123d import (
    Align,
    BuildLine,
    BuildPart,
    BuildSketch,
    CenterArc,
    Circle,
    Color,
    Compound,
    Cylinder,
    Edge,
    Line,
    Location,
    Plane,
    extrude,
    make_face,
    sweep,
)


# Units: millimeters.
# Origin: centered on the staircase axis; base/column bottom starts at Z=0.
# XY: plan view. +Z: staircase rise direction.

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
HANDRAIL_TUBE_DIAMETER = 5.0
HANDRAIL_START_Z = 14.0
HANDRAIL_END_Z = 130.0

BALUSTER_DIAMETER = 3.0

def _polar_point(radius: float, angle_degrees: float) -> tuple[float, float]:
    angle_radians = radians(angle_degrees)
    return (radius * cos(angle_radians), radius * sin(angle_radians))


def _make_base():
    with BuildPart() as base:
        Cylinder(
            radius=BASE_DIAMETER / 2.0,
            height=BASE_THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    part = base.part
    part.label = "circular_base_disk_diameter_90mm_thickness_5mm"
    part.color = Color(0.42, 0.43, 0.45, 1.0)
    return part


def _make_column():
    with BuildPart() as column:
        Cylinder(
            radius=COLUMN_DIAMETER / 2.0,
            height=COLUMN_HEIGHT,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    part = column.part
    part.label = "central_column_diameter_14mm_height_140mm"
    part.color = Color(0.70, 0.72, 0.74, 1.0)
    return part


def _make_tread_profile():
    half_sweep = TREAD_SWEEP_DEGREES / 2.0
    start_angle = -half_sweep
    end_angle = half_sweep

    with BuildPart() as tread:
        with BuildSketch(Plane.XY):
            with BuildLine():
                CenterArc((0.0, 0.0), TREAD_OUTER_RADIUS, start_angle, TREAD_SWEEP_DEGREES)
                Line(
                    _polar_point(TREAD_OUTER_RADIUS, end_angle),
                    _polar_point(TREAD_INNER_RADIUS, end_angle),
                )
                CenterArc((0.0, 0.0), TREAD_INNER_RADIUS, end_angle, -TREAD_SWEEP_DEGREES)
                Line(
                    _polar_point(TREAD_INNER_RADIUS, start_angle),
                    _polar_point(TREAD_OUTER_RADIUS, start_angle),
                )
            make_face()
        extrude(amount=TREAD_THICKNESS)

    part = tread.part
    part.label = "tread_profile_inner_10mm_outer_62mm_sweep_24deg"
    part.color = Color(0.78, 0.58, 0.35, 1.0)
    return part


def _make_tread(index: int):
    angle_degrees = index * TREAD_ROTATION_DEGREES
    bottom_z = TREAD_FIRST_BOTTOM_Z + index * TREAD_RISE
    tread_profile = _make_tread_profile()
    tread = tread_profile.moved(Location((0.0, 0.0, bottom_z), (0.0, 0.0, angle_degrees)))
    tread.label = f"tread_{index + 1:02d}_bottom_z_{bottom_z:.0f}mm_angle_{angle_degrees:.0f}deg"
    return tread


def _handrail_center_z(angle_degrees: float) -> float:
    rail_rise = HANDRAIL_END_Z - HANDRAIL_START_Z
    return HANDRAIL_START_Z + rail_rise * angle_degrees / 360.0


def _make_handrail():
    rail_height = HANDRAIL_END_Z - HANDRAIL_START_Z
    path = Edge.make_helix(
        pitch=rail_height,
        height=rail_height,
        radius=HANDRAIL_RADIUS,
        center=(0.0, 0.0, HANDRAIL_START_Z),
    )
    start_tangent = path.tangent_at(0.0)
    profile_plane = Plane(
        origin=(HANDRAIL_RADIUS, 0.0, HANDRAIL_START_Z),
        x_dir=(1.0, 0.0, 0.0),
        z_dir=start_tangent,
    )

    with BuildPart() as rail:
        with BuildSketch(profile_plane):
            Circle(HANDRAIL_TUBE_DIAMETER / 2.0)
        sweep(path=path, is_frenet=True)

    part = rail.part
    part.label = "helical_outer_handrail_radius_66mm_diameter_5mm"
    part.color = Color(0.22, 0.28, 0.34, 1.0)
    return part


def _make_baluster(index: int):
    angle_degrees = index * TREAD_ROTATION_DEGREES
    tread_top_z = TREAD_FIRST_BOTTOM_Z + index * TREAD_RISE + TREAD_THICKNESS
    rail_center_z = _handrail_center_z(angle_degrees)
    x_pos, y_pos = _polar_point(TREAD_OUTER_RADIUS, angle_degrees)
    height = rail_center_z - tread_top_z

    with BuildPart() as baluster:
        Cylinder(
            radius=BALUSTER_DIAMETER / 2.0,
            height=height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    part = baluster.part.moved(Location((x_pos, y_pos, tread_top_z)))
    part.label = f"baluster_{index + 1:02d}_diameter_3mm"
    part.color = Color(0.30, 0.33, 0.36, 1.0)
    return part


def gen_step():
    """Return a labeled miniature spiral staircase STEP compound in millimeters."""
    parts = [
        _make_base(),
        _make_column(),
    ]

    for index in range(TREAD_COUNT):
        parts.append(_make_tread(index))

    parts.append(_make_handrail())

    for index in range(TREAD_COUNT):
        parts.append(_make_baluster(index))

    assembly = Compound(
        obj=parts,
        children=parts,
        label="miniature_spiral_staircase",
    )
    return assembly
