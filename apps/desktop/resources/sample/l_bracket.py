"""An L-bracket with two gussets and mounting holes in both directions.

Hardcore's sample project. Change a size below and run `python l_bracket.py`
(or ask the agent to) to rebuild l_bracket.step.
"""
from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step


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

    with bd.BuildPart() as gusset:
        with bd.BuildSketch(bd.Plane.YZ):
            bd.Polygon(
                [
                    (back_front_y, BASE_THICKNESS),
                    (front_y, BASE_THICKNESS),
                    (back_front_y, top_z),
                ],
                align=None,
            )
        bd.extrude(amount=GUSSET_X_THICKNESS)

    part = gusset.part.moved(bd.Location((x_center - GUSSET_X_THICKNESS / 2.0, 0.0, 0.0)))
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


def _fillet(part, edges, radius: float):
    # A fillet that cannot be made leaves the part as it was rather than failing the build.
    if not edges:
        return part
    try:
        return bd.fillet(edges, radius=radius)
    except Exception:
        return part


@step(out="l_bracket.step")
def l_bracket():
    """Return the L-bracket model in millimeters."""
    with bd.BuildPart() as bracket:
        bd.Box(BASE_LENGTH, BASE_WIDTH, BASE_THICKNESS, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))

        with bd.Locations(bd.Location((0.0, BACK_CENTER_Y, BASE_THICKNESS))):
            bd.Box(
                BACK_LENGTH,
                BACK_THICKNESS,
                BACK_HEIGHT,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.ADD,
            )

        for x_pos, y_pos in BASE_HOLE_LOCATIONS:
            with bd.Locations(bd.Location((x_pos, y_pos, -1.0))):
                bd.Cylinder(
                    radius=HOLE_DIAMETER / 2.0,
                    height=BASE_THICKNESS + 2.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.SUBTRACT,
                )

        for x_pos, z_pos in BACK_HOLE_LOCATIONS:
            with bd.Locations(bd.Location((x_pos, BACK_CENTER_Y, z_pos))):
                bd.Cylinder(
                    radius=HOLE_DIAMETER / 2.0,
                    height=BACK_THICKNESS + 2.0,
                    rotation=(90.0, 0.0, 0.0),
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER),
                    mode=bd.Mode.SUBTRACT,
                )

        for x_center in GUSSET_X_LOCATIONS:
            bd.add(_make_gusset(x_center), mode=bd.Mode.ADD)

    part = bracket.part
    part = _fillet(part, _transition_edges(part), radius=TRANSITION_FILLET)
    part.label = "l_bracket"
    return part


if __name__ == "__main__":
    l_bracket()
