from __future__ import annotations
from cadgen import step, threemf

from math import sqrt

from cadgen import build123d as bd
from cadgen.assembly import AssemblyHelper


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
    base.color = bd.Color(0.58, 0.62, 0.66, 1.0)
    return base


def _make_peg():
    peg = bd.Cylinder(radius=PEG_DIAMETER / 2.0, height=PEG_HEIGHT)
    peg.label = "cylindrical_peg"
    peg.color = bd.Color(0.86, 0.24, 0.20, 1.0)
    return peg


def _make_block():
    block = bd.Box(BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
    block.label = "square_block"
    block.color = bd.Color(0.18, 0.53, 0.88, 1.0)
    return block


def _make_cone():
    cone = bd.Cone(0.0, CONE_BASE_DIAMETER / 2.0, CONE_HEIGHT)
    cone.label = "cone"
    cone.color = bd.Color(0.95, 0.64, 0.16, 1.0)
    return cone


def _make_sphere():
    sphere = bd.Sphere(SPHERE_DIAMETER / 2.0)
    sphere.label = "sphere"
    sphere.color = bd.Color(0.45, 0.72, 0.34, 1.0)
    return sphere


def _make_prism():
    prism = _triangular_prism(PRISM_SIDE, PRISM_LENGTH)
    prism.label = "triangular_prism"
    prism.color = bd.Color(0.58, 0.34, 0.74, 1.0)
    return prism


def _make_cube_top_pad():
    pad = bd.Box(CUBE_TOP_PAD_SIZE, CUBE_TOP_PAD_SIZE, CUBE_TOP_PAD_HEIGHT).moved(
        bd.Location((0.0, 0.0, CUBE_TOP_PAD_HEIGHT / 2.0))
    )
    pad.label = "cube_top_pad"
    pad.color = bd.Color(0.10, 0.14, 0.20, 1.0)
    return pad


def _make_cube_top_post(x_offset: float, name: str):
    post = bd.Cylinder(radius=CUBE_TOP_POST_RADIUS, height=CUBE_TOP_POST_HEIGHT).moved(
        bd.Location((x_offset, 0.0, CUBE_TOP_PAD_HEIGHT + CUBE_TOP_POST_HEIGHT / 2.0))
    )
    post.label = name
    post.color = bd.Color(0.84, 0.30, 0.50, 1.0)
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
    cap.color = bd.Color(0.12, 0.70, 0.74, 1.0)
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
    bead.color = bd.Color(0.98, 0.86, 0.20, 1.0)
    return bead


def _make_cube_top_subassembly():
    subassembly = AssemblyHelper("cube_top_subassembly")
    subassembly.add(_make_cube_top_pad(), "cube_top_pad")
    subassembly.add(
        _make_cube_top_post(-CUBE_TOP_POST_SPACING / 2.0, "cube_top_left_post"),
        "cube_top_left_post",
    )
    subassembly.add(
        _make_cube_top_post(CUBE_TOP_POST_SPACING / 2.0, "cube_top_right_post"),
        "cube_top_right_post",
    )
    subassembly.add(_make_cube_top_cap(), "cube_top_bridge_cap")
    subassembly.add(_make_cube_top_bead(), "cube_top_bead")
    return subassembly.build()


@step(out="../STEP/basic_shape_mating_test_fixture.step")
@threemf(out="../3MF/basic_shape_mating_test_fixture.3mf")
def basic_shape_mating_test_fixture():
    asm = AssemblyHelper("basic_shape_mating_test_fixture")

    base = asm.add(_make_base(), "base_plate")
    peg = asm.add(_make_peg(), "cylindrical_peg")
    block = asm.add(_make_block(), "square_block")
    cone = asm.add(_make_cone(), "cone")
    sphere = asm.add(_make_sphere(), "sphere")
    prism = asm.add(_make_prism(), "triangular_prism")
    cube_top_subassembly = asm.add(
        _make_cube_top_subassembly(),
        "cube_top_subassembly",
    )

    peg_x, peg_y = STATIONS["cylindrical_peg"]
    peg_seat = asm.rigid_frame(base, "peg_pocket_floor", bd.Location((peg_x, peg_y, BASE_TOP_Z - POCKET_DEPTH)))
    peg_bottom = asm.rigid_frame(peg, "bottom_center", bd.Location((0.0, 0.0, -PEG_HEIGHT / 2.0)))
    asm.face_to_face(peg_seat, peg_bottom, offset=-PEG_COLLISION_DEPTH)

    block_x, block_y = STATIONS["square_block"]
    block_seat = asm.rigid_frame(
        base,
        "block_pocket_floor",
        bd.Location((block_x, block_y, BASE_TOP_Z - POCKET_DEPTH)),
    )
    block_bottom = asm.rigid_frame(block, "bottom_center", bd.Location((0.0, 0.0, -BLOCK_SIZE / 2.0)))
    asm.face_to_face(block_seat, block_bottom, offset=BLOCK_CONTACT_OFFSET)

    asm.rigid_frame(block, "top_center", bd.Location((0.0, 0.0, BLOCK_SIZE / 2.0)))
    cube_top_seat = asm.rigid_frame(
        base,
        "cube_top_subassembly_seat",
        bd.Location((block_x, block_y, BASE_TOP_Z - POCKET_DEPTH + BLOCK_CONTACT_OFFSET + BLOCK_SIZE)),
    )
    cube_top_subassembly_bottom = asm.rigid_frame(
        cube_top_subassembly,
        "bottom_center",
        bd.Location((0.0, 0.0, 0.0)),
    )
    asm.face_to_face(
        cube_top_seat,
        cube_top_subassembly_bottom,
        label="cube_top_subassembly_on_square_block",
    )

    cone_x, cone_y = STATIONS["cone"]
    cone_tip_seat = asm.rigid_frame(
        base,
        "cone_countersink_tip",
        bd.Location((cone_x, cone_y, BASE_TOP_Z - CONE_SEAT_DEPTH)),
    )
    cone_tip = asm.rigid_frame(cone, "tip", bd.Location((0.0, 0.0, -CONE_HEIGHT / 2.0)))
    asm.coaxial(cone_tip_seat, cone_tip, offset=0.1)

    sphere_x, sphere_y = STATIONS["sphere"]
    sphere_cup_center = asm.rigid_frame(base, "sphere_cup_center", bd.Location((sphere_x, sphere_y, BASE_TOP_Z)))
    sphere_center = asm.rigid_frame(sphere, "center", bd.Location((0.0, 0.0, 0.0)))
    asm.coaxial(sphere_cup_center, sphere_center, offset=0.1)

    prism_x, prism_y = STATIONS["triangular_prism"]
    prism_v_bottom = asm.rigid_frame(
        base,
        "v_groove_bottom",
        bd.Location((prism_x, prism_y, BASE_TOP_Z - V_GROOVE_DEPTH)),
    )
    prism_bottom_vertex = asm.rigid_frame(
        prism,
        "bottom_vertex",
        bd.Location((0.0, 0.0, -PRISM_HEIGHT / 2.0)),
    )
    asm.face_to_face(prism_v_bottom, prism_bottom_vertex, offset=-PRISM_COLLISION_DEPTH)

    return asm.build()


if __name__ == "__main__":
    basic_shape_mating_test_fixture()
