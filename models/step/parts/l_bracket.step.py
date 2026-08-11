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

from part_common import safe_fillet


BASE_LENGTH = 80.0
BASE_WIDTH = 50.0
BASE_THICKNESS = 8.0

BACK_LENGTH = 80.0
BACK_THICKNESS = 8.0
BACK_HEIGHT = 50.0
BACK_CENTER_Y = BASE_WIDTH / 2.0 - BACK_THICKNESS / 2.0

HOLE_DIAMETER = 6.0
BASE_HOLE_LOCATIONS = ((-25.0, -10.0), (25.0, -10.0))
BACK_HOLE_LOCATIONS = ((-25.0, 30.0), (25.0, 30.0))

GUSSET_X_THICKNESS = 8.0
GUSSET_X_LOCATIONS = (-20.0, 20.0)
GUSSET_DEPTH = 30.0
GUSSET_HEIGHT = 30.0
TRANSITION_FILLET = 2.0


def _make_gusset(x_center: float):
    back_front_y = BACK_CENTER_Y - BACK_THICKNESS / 2.0
    front_y = back_front_y - GUSSET_DEPTH
    top_z = BASE_THICKNESS + GUSSET_HEIGHT

    with BuildPart() as gusset:
        with BuildSketch(Plane.YZ):
            Polygon(
                [
                    (back_front_y, BASE_THICKNESS),
                    (front_y, BASE_THICKNESS),
                    (back_front_y, top_z),
                ],
                align=None,
            )
        extrude(amount=GUSSET_X_THICKNESS)

    part = gusset.part.moved(Location((x_center - GUSSET_X_THICKNESS / 2.0, 0.0, 0.0)))
    part.label = f"gusset_x_{x_center:.0f}"
    return part


def _transition_edges(part):
    edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        if str(edge.geom_type).endswith("LINE"):
            if abs(bbox.min.Z - BASE_THICKNESS) < 0.05 and abs(bbox.max.Z - BASE_THICKNESS) < 0.05:
                center_y = bbox.center().Y
                if BACK_CENTER_Y - BACK_THICKNESS / 2.0 - 0.05 <= center_y <= BASE_WIDTH / 2.0 + 0.05:
                    if bbox.size.X > 20.0:
                        edges.append(edge)
    return edges


def gen_step():
    """Return the L-bracket model in millimeters."""
    with BuildPart() as bracket:
        Box(BASE_LENGTH, BASE_WIDTH, BASE_THICKNESS, align=(Align.CENTER, Align.CENTER, Align.MIN))

        with Locations(Location((0.0, BACK_CENTER_Y, BASE_THICKNESS))):
            Box(
                BACK_LENGTH,
                BACK_THICKNESS,
                BACK_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD,
            )

        for x_pos, y_pos in BASE_HOLE_LOCATIONS:
            with Locations(Location((x_pos, y_pos, -1.0))):
                Cylinder(
                    radius=HOLE_DIAMETER / 2.0,
                    height=BASE_THICKNESS + 2.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        for x_pos, z_pos in BACK_HOLE_LOCATIONS:
            with Locations(Location((x_pos, BACK_CENTER_Y, z_pos))):
                Cylinder(
                    radius=HOLE_DIAMETER / 2.0,
                    height=BACK_THICKNESS + 2.0,
                    rotation=(90.0, 0.0, 0.0),
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.SUBTRACT,
                )

        for x_center in GUSSET_X_LOCATIONS:
            add(_make_gusset(x_center), mode=Mode.ADD)

    part = bracket.part
    part = safe_fillet(part, _transition_edges(part), radius=TRANSITION_FILLET)
    part.label = "l_bracket_gussets_two_hole_directions"
    return part
