from math import cos, radians, sin

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    add,
    extrude,
)

from part_common import rounded_triangle_points, safe_fillet


BASE_LENGTH = 120.0
BASE_WIDTH = 60.0
BASE_THICKNESS = 10.0
BASE_FILLET = 3.0

LUG_X_EXTENT = 36.0
LUG_RADIUS = 18.0
LUG_HEIGHT_ABOVE_BASE = 42.0
LUG_THICKNESS_Y = 18.0
LUG_GAP_Y = 16.0
LUG_FILLET = 2.0

CLEVIS_HOLE_DIAMETER = 14.0
CLEVIS_HOLE_CENTER_Z = 34.0

BASE_HOLE_DIAMETER = 7.0
BASE_HOLE_LOCATIONS = ((-45.0, -20.0), (-45.0, 20.0), (45.0, -20.0), (45.0, 20.0))

CUTOUT_CORNER_RADIUS = 3.0
RIB_THICKNESS_X = 6.0


def _lug_profile_points() -> list[tuple[float, float]]:
    half_x = LUG_X_EXTENT / 2.0
    arc_center_z = BASE_THICKNESS + LUG_HEIGHT_ABOVE_BASE - LUG_RADIUS
    points = [(-half_x, BASE_THICKNESS), (half_x, BASE_THICKNESS), (half_x, arc_center_z)]

    for step in range(1, 12):
        angle = radians(180.0 * step / 12.0)
        points.append((LUG_RADIUS * cos(angle), arc_center_z + LUG_RADIUS * sin(angle)))

    points.append((-half_x, arc_center_z))
    return points


def _make_lug(y_min: float, label: str):
    with BuildPart() as lug:
        with BuildSketch(Plane.XZ):
            Polygon(_lug_profile_points(), align=None)
        extrude(amount=LUG_THICKNESS_Y)

    part = lug.part.moved(Location((0.0, y_min, 0.0)))
    part.label = label
    return part


def _make_rib(sign: float):
    outer_y = sign * (LUG_GAP_Y / 2.0 + LUG_THICKNESS_Y)
    foot_y = sign * (BASE_WIDTH / 2.0)
    top_z = BASE_THICKNESS + 28.0

    with BuildPart() as rib:
        with BuildSketch(Plane.YZ):
            Polygon(
                [
                    (outer_y, BASE_THICKNESS),
                    (foot_y, BASE_THICKNESS),
                    (outer_y, top_z),
                ],
                align=None,
            )
        extrude(amount=RIB_THICKNESS_X)

    part = rib.part.moved(Location((-RIB_THICKNESS_X / 2.0, 0.0, 0.0)))
    part.label = "positive_y_diagonal_rib" if sign > 0.0 else "negative_y_diagonal_rib"
    return part


def _outer_base_edges(part):
    edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        center = bbox.center()
        on_outer_x = abs(abs(center.X) - BASE_LENGTH / 2.0) < 0.05
        on_outer_y = abs(abs(center.Y) - BASE_WIDTH / 2.0) < 0.05
        on_top_or_bottom = abs(center.Z - 0.0) < 0.05 or abs(center.Z - BASE_THICKNESS) < 0.05
        if (on_outer_x or on_outer_y) and on_top_or_bottom:
            edges.append(edge)
    return edges


def _lug_base_edges(part):
    edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        center = bbox.center()
        if abs(center.Z - BASE_THICKNESS) > 0.05:
            continue
        if abs(abs(center.Y) - LUG_GAP_Y / 2.0) < 0.05 and bbox.size.X > LUG_X_EXTENT - 1.0:
            edges.append(edge)
    return edges


def _subtract_rounded_triangle(vertices: list[tuple[float, float]]):
    with BuildSketch(Plane.XY) as cutout:
        Polygon(
            rounded_triangle_points(vertices, radius=CUTOUT_CORNER_RADIUS, segments=5),
            align=None,
        )
    extrude(cutout.sketch, amount=BASE_THICKNESS + 2.0, mode=Mode.SUBTRACT)


def gen_step():
    """Return the clevis bracket model in millimeters."""
    positive_lug_y_min = LUG_GAP_Y / 2.0 + LUG_THICKNESS_Y
    negative_lug_y_min = -LUG_GAP_Y / 2.0

    with BuildPart() as bracket:
        Box(BASE_LENGTH, BASE_WIDTH, BASE_THICKNESS, align=(Align.CENTER, Align.CENTER, Align.MIN))

    base = safe_fillet(bracket.part, _outer_base_edges(bracket.part), radius=BASE_FILLET)

    with BuildPart() as bracket:
        add(base, mode=Mode.ADD)
        add(_make_lug(positive_lug_y_min, "positive_y_clevis_lug"), mode=Mode.ADD)
        add(_make_lug(negative_lug_y_min, "negative_y_clevis_lug"), mode=Mode.ADD)
        add(_make_rib(1.0), mode=Mode.ADD)
        add(_make_rib(-1.0), mode=Mode.ADD)

        with Locations(Location((0.0, 0.0, CLEVIS_HOLE_CENTER_Z))):
            Cylinder(
                radius=CLEVIS_HOLE_DIAMETER / 2.0,
                height=BASE_WIDTH + 8.0,
                rotation=(90.0, 0.0, 0.0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )

        for x_pos, y_pos in BASE_HOLE_LOCATIONS:
            with Locations(Location((x_pos, y_pos, -1.0))):
                Cylinder(
                    radius=BASE_HOLE_DIAMETER / 2.0,
                    height=BASE_THICKNESS + 2.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        _subtract_rounded_triangle([(-54.0, -13.0), (-25.0, 0.0), (-54.0, 13.0)])
        _subtract_rounded_triangle([(54.0, -13.0), (25.0, 0.0), (54.0, 13.0)])

    part = bracket.part
    part = safe_fillet(part, _lug_base_edges(part), radius=LUG_FILLET)
    part.label = "aerospace_clevis_bracket_lightening_cutouts"
    return part
