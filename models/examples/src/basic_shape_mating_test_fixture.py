from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties


from cadgen import model

from math import sqrt

import build123d as bd


# Units: millimeters.
# Origin: base plate center, XY on plate center plane, +Z upward.
# The cone uses a shallow visible seat because it is taller than the 10 mm base.
# The triangular prism uses a full-depth V-groove so the matching angled faces
# visibly nest while the part remains a separate component.
# Two seats are intentionally over-inserted to exercise the viewer's collision
# analysis overlay. The square block is exactly seated to exercise contact
# surface highlighting.

BASE_LENGTH = 120.0
BASE_WIDTH = 70.0
BASE_THICKNESS = 10.0
BASE_TOP_Z = BASE_THICKNESS / 2
CLEARANCE = 0.2

PEG_DIAMETER = 16.0
PEG_HEIGHT = 25.0
BLOCK_SIZE = 18.0
CONE_BASE_DIAMETER = 22.0
CONE_HEIGHT = 25.0
SPHERE_DIAMETER = 20.0
PRISM_LENGTH = 35.0
PRISM_SIDE = 18.0
PRISM_HEIGHT = sqrt(3.0) * PRISM_SIDE / 2.0

POCKET_DEPTH = 3.0
CONE_SEAT_DEPTH = 5.0
SPHERE_CUP_RADIUS = SPHERE_DIAMETER / 2.0 + CLEARANCE / 2.0
V_GROOVE_DEPTH = BASE_THICKNESS
V_GROOVE_SIDE_CLEARANCE = CLEARANCE / 2.0
V_GROOVE_BOTTOM_WIDTH = 4.0 * V_GROOVE_SIDE_CLEARANCE / sqrt(3.0)
V_GROOVE_TOP_WIDTH = 2.0 * (V_GROOVE_DEPTH + 2.0 * V_GROOVE_SIDE_CLEARANCE) / sqrt(3.0)
PEG_COLLISION_DEPTH = 0.8
PRISM_COLLISION_DEPTH = 1.0
BLOCK_CONTACT_OFFSET = 0.0

CUBE_TOP_PAD_SIZE = 14.0
CUBE_TOP_PAD_HEIGHT = 2.5
CUBE_TOP_POST_RADIUS = 1.8
CUBE_TOP_POST_HEIGHT = 7.0
CUBE_TOP_POST_SPACING = 8.0
CUBE_TOP_CAP_LENGTH = 13.0
CUBE_TOP_CAP_WIDTH = 4.5
CUBE_TOP_CAP_HEIGHT = 2.5
CUBE_TOP_BEAD_DIAMETER = 4.5

STATIONS = {
    "cylindrical_peg": (-48.0, 0.0),
    "square_block": (-24.0, 0.0),
    "cone": (0.0, 0.0),
    "sphere": (24.0, 0.0),
    "triangular_prism": (48.0, 0.0),
}


def _triangular_prism(side: float, length: float):
    height = sqrt(3.0) * side / 2.0
    with bd.BuildPart() as prism:
        with bd.BuildSketch(bd.Plane.XZ):
            bd.Polygon(
                (-side / 2.0, height / 2.0),
                (side / 2.0, height / 2.0),
                (0.0, -height / 2.0),
            )
        bd.extrude(amount=length)
    return prism.part.moved(bd.Location((0.0, length / 2.0, 0.0)))


def _v_groove_tool(depth: float, length: float, side_clearance: float):
    top_half_width = (depth + 2.0 * side_clearance) / sqrt(3.0)
    bottom_half_width = 2.0 * side_clearance / sqrt(3.0)
    with bd.BuildPart() as groove:
        with bd.BuildSketch(bd.Plane.XZ):
            bd.Polygon(
                (-top_half_width, 0.0),
                (top_half_width, 0.0),
                (bottom_half_width, -depth),
                (-bottom_half_width, -depth),
            )
        bd.extrude(amount=length)
    return groove.part.moved(bd.Location((0.0, length / 2.0, 0.0)))


def _make_base():
    base = bd.Box(BASE_LENGTH, BASE_WIDTH, BASE_THICKNESS)

    peg_x, peg_y = STATIONS["cylindrical_peg"]
    peg_pocket = bd.Cylinder(
        radius=(PEG_DIAMETER + CLEARANCE) / 2.0,
        height=POCKET_DEPTH + 0.4,
    ).moved(bd.Location((peg_x, peg_y, BASE_TOP_Z - POCKET_DEPTH / 2.0 + 0.2)))
    base = base - peg_pocket

    block_x, block_y = STATIONS["square_block"]
    block_pocket = bd.Box(
        BLOCK_SIZE + CLEARANCE,
        BLOCK_SIZE + CLEARANCE,
        POCKET_DEPTH + 0.4,
    ).moved(bd.Location((block_x, block_y, BASE_TOP_Z - POCKET_DEPTH / 2.0 + 0.2)))
    base = base - block_pocket

    cone_x, cone_y = STATIONS["cone"]
    cone_seat = bd.Cone(
        0.0,
        (CONE_BASE_DIAMETER + CLEARANCE) / 2.0,
        CONE_SEAT_DEPTH,
    ).moved(bd.Location((cone_x, cone_y, BASE_TOP_Z - CONE_SEAT_DEPTH / 2.0)))
    base = base - cone_seat

    sphere_x, sphere_y = STATIONS["sphere"]
    sphere_cup = bd.Sphere(SPHERE_CUP_RADIUS).moved(bd.Location((sphere_x, sphere_y, BASE_TOP_Z)))
    base = base - sphere_cup

    prism_x, prism_y = STATIONS["triangular_prism"]
    groove = _v_groove_tool(
        V_GROOVE_DEPTH,
        PRISM_LENGTH + CLEARANCE,
        V_GROOVE_SIDE_CLEARANCE,
    ).moved(bd.Location((prism_x, prism_y, 0.0)))
    base = base - groove

    base.label = "base_plate"
    base.color = bd.Color("#c8ced4")
    return base


def _make_peg():
    peg = bd.Cylinder(radius=PEG_DIAMETER / 2.0, height=PEG_HEIGHT)
    peg.label = "cylindrical_peg"
    peg.color = bd.Color("#ef867c")
    return peg


def _make_block():
    block = bd.Box(BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
    block.label = "square_block"
    block.color = bd.Color("#76c0f1")
    return block


def _make_cone():
    cone = bd.Cone(0.0, CONE_BASE_DIAMETER / 2.0, CONE_HEIGHT)
    cone.label = "cone"
    cone.color = bd.Color("#f9d16f")
    return cone


def _make_sphere():
    sphere = bd.Sphere(SPHERE_DIAMETER / 2.0)
    sphere.label = "sphere"
    sphere.color = bd.Color("#b3dd9e")
    return sphere


def _make_prism():
    prism = _triangular_prism(PRISM_SIDE, PRISM_LENGTH)
    prism.label = "triangular_prism"
    prism.color = bd.Color("#c89edf")
    return prism


def _make_cube_top_pad():
    pad = bd.Box(CUBE_TOP_PAD_SIZE, CUBE_TOP_PAD_SIZE, CUBE_TOP_PAD_HEIGHT).moved(
        bd.Location((0.0, 0.0, CUBE_TOP_PAD_HEIGHT / 2.0))
    )
    pad.label = "cube_top_pad"
    pad.color = bd.Color("#59697c")
    return pad


def _make_cube_top_post(x_offset: float, name: str):
    post = bd.Cylinder(radius=CUBE_TOP_POST_RADIUS, height=CUBE_TOP_POST_HEIGHT).moved(
        bd.Location((x_offset, 0.0, CUBE_TOP_PAD_HEIGHT + CUBE_TOP_POST_HEIGHT / 2.0))
    )
    post.label = name
    post.color = bd.Color("#ec95bc")
    return post


def _make_cube_top_cap():
    cap = bd.Box(CUBE_TOP_CAP_LENGTH, CUBE_TOP_CAP_WIDTH, CUBE_TOP_CAP_HEIGHT).moved(
        bd.Location(
            (
                0.0,
                0.0,
                CUBE_TOP_PAD_HEIGHT + CUBE_TOP_POST_HEIGHT + CUBE_TOP_CAP_HEIGHT / 2.0,
            )
        )
    )
    cap.label = "cube_top_bridge_cap"
    cap.color = bd.Color("#61dadf")
    return cap


def _make_cube_top_bead():
    bead_radius = CUBE_TOP_BEAD_DIAMETER / 2.0
    bead = bd.Sphere(bead_radius).moved(
        bd.Location(
            (
                0.0,
                0.0,
                CUBE_TOP_PAD_HEIGHT + CUBE_TOP_POST_HEIGHT + CUBE_TOP_CAP_HEIGHT + bead_radius,
            )
        )
    )
    bead.label = "cube_top_bead"
    bead.color = bd.Color("#fdef7c")
    return bead


def _make_cube_top_subassembly():
    return bd.Compound(
        children=[
            _make_cube_top_pad(),
            _make_cube_top_post(-CUBE_TOP_POST_SPACING / 2.0, "cube_top_left_post"),
            _make_cube_top_post(CUBE_TOP_POST_SPACING / 2.0, "cube_top_right_post"),
            _make_cube_top_cap(),
            _make_cube_top_bead(),
        ],
        label="cube_top_subassembly",
    )


def _mate(fixed, fixed_frame: str, fixed_at: bd.Location, moving, moving_frame: str,
          moving_at: bd.Location, *, offset: float | None = None) -> None:
    """Seat ``moving`` on ``fixed`` (the old ``rigid_frame`` pair + ``face_to_face`` or
    ``coaxial``): a RigidJoint on each part in its own frame, and ``connect_to`` moves
    ``moving`` so the two frames coincide. ``offset`` (mm along the fixed frame's Z)
    seats it from a second fixed joint, ``<fixed_frame>:offset``, as the old helper's
    ``offset=`` did."""
    bd.RigidJoint(fixed_frame, fixed, fixed_at)
    if offset is not None:
        fixed_frame = f"{fixed_frame}:offset"
        bd.RigidJoint(fixed_frame, fixed, fixed_at * bd.Location((0.0, 0.0, offset)))
    bd.RigidJoint(moving_frame, moving, moving_at)
    fixed.joints[fixed_frame].connect_to(moving.joints[moving_frame])


@model
def basic_shape_mating_test_fixture():
    base = _make_base()
    peg = _make_peg()
    block = _make_block()
    cone = _make_cone()
    sphere = _make_sphere()
    prism = _make_prism()
    cube_top_subassembly = _make_cube_top_subassembly()

    peg_x, peg_y = STATIONS["cylindrical_peg"]
    _mate(base, "peg_pocket_floor", bd.Location((peg_x, peg_y, BASE_TOP_Z - POCKET_DEPTH)),
          peg, "bottom_center", bd.Location((0.0, 0.0, -PEG_HEIGHT / 2.0)),
          offset=-PEG_COLLISION_DEPTH)

    block_x, block_y = STATIONS["square_block"]
    _mate(base, "block_pocket_floor", bd.Location((block_x, block_y, BASE_TOP_Z - POCKET_DEPTH)),
          block, "bottom_center", bd.Location((0.0, 0.0, -BLOCK_SIZE / 2.0)),
          offset=BLOCK_CONTACT_OFFSET)

    bd.RigidJoint("top_center", block, bd.Location((0.0, 0.0, BLOCK_SIZE / 2.0)))
    _mate(base, "cube_top_subassembly_seat",
          bd.Location((block_x, block_y, BASE_TOP_Z - POCKET_DEPTH + BLOCK_CONTACT_OFFSET + BLOCK_SIZE)),
          cube_top_subassembly, "bottom_center", bd.Location((0.0, 0.0, 0.0)))

    cone_x, cone_y = STATIONS["cone"]
    _mate(base, "cone_countersink_tip", bd.Location((cone_x, cone_y, BASE_TOP_Z - CONE_SEAT_DEPTH)),
          cone, "tip", bd.Location((0.0, 0.0, -CONE_HEIGHT / 2.0)), offset=0.1)

    sphere_x, sphere_y = STATIONS["sphere"]
    _mate(base, "sphere_cup_center", bd.Location((sphere_x, sphere_y, BASE_TOP_Z)),
          sphere, "center", bd.Location((0.0, 0.0, 0.0)), offset=0.1)

    prism_x, prism_y = STATIONS["triangular_prism"]
    _mate(base, "v_groove_bottom", bd.Location((prism_x, prism_y, BASE_TOP_Z - V_GROOVE_DEPTH)),
          prism, "bottom_vertex", bd.Location((0.0, 0.0, -PRISM_HEIGHT / 2.0)),
          offset=-PRISM_COLLISION_DEPTH)

    fixture = bd.Compound(
        children=[base, peg, block, cone, sphere, prism, cube_top_subassembly],
        label="basic_shape_mating_test_fixture",
    )
    # One material for every part: bead-blasted aluminium anodised in each part's own colour.
    authored_color = fixture.color
    fixture.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Bead-blasted 6061-T6, colour-anodised', metalness=1.0, roughness=0.6),
    )
    fixture.color = authored_color
    return fixture


if __name__ == "__main__":
    basic_shape_mating_test_fixture()
