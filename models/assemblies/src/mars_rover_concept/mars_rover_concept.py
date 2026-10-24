from __future__ import annotations

from cadgen import model
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state
from cadgen.gltf import animation

import math
from collections.abc import Sequence

import build123d as bd


DISPLAY_NAME = "Mars rover concept vehicle"

# Coordinate convention:
# - millimeters
# - +X forward (drive direction), +Y left, +Z up
# - terrain top surface is Z=0; wheel contact patches sit on Z=0
# - the vehicle is modeled in its display pose: suspension neutral, arm in a
#   sampling hover, mast head level, solar wings deployed, HGA at 35 deg
#
# The mechanism is build123d joints on the top-level groups (`_connect` below)
# and the joints the clips need (`_clip_joints`), with the differential's
# coupling, the configurations and the four old clips as motions in the model's
# body. Joint axes are built from the SAME derived constants the geometry uses,
# so re-deriving the layout re-derives the pivots.

# ---------------------------------------------------------------------------
# Source parameters (geometry contract; snake_case names are part of the
# public model contract requested for this concept)
# ---------------------------------------------------------------------------

rover_scale = 1.0            # uniform display scale applied to every solid
body_length = 2100.0         # warm-body X extent
body_width = 1300.0          # warm-body Y extent
body_height = 620.0          # warm-body Z extent (belly to deck)
ground_clearance = 560.0     # terrain top to belly pan underside
wheel_diameter = 520.0       # overall diameter including grousers
wheel_width = 320.0          # axial rim width
wheelbase_length = 2500.0    # front axle to rear axle X distance
track_width = 1980.0         # left/right wheel center Y distance
wheel_grouser_count = 20     # grouser bars per wheel
wheel_grouser_height = 8.0   # radial grouser standoff above rim skin
wheel_rib_density = 3        # internal stiffening rings per wheel (0..5)
mast_height = 950.0          # deck top to mast column top
camera_head_scale = 1.0      # remote-sensing head proportional scale
antenna_count = 3            # low-gain/whip antennas (LGA + extra whips, 1..5)
science_payload_density = 0.7  # 0..1, drives payload module + deck instrument count
terrain_rock_height = 120.0  # characteristic rock size on the terrain diorama
terrain_slope_angle = 0.0    # deg, tilts the terrain diorama about the Y axis

# ---------------------------------------------------------------------------
# Derived layout (all mm)
# ---------------------------------------------------------------------------

wheel_r = wheel_diameter / 2.0                      # 260
axle_z = wheel_r                                    # wheel centers
belly_z = ground_clearance                          # 560
deck_z = ground_clearance + body_height             # 1180
half_len = body_length / 2.0                        # 1050
half_wid = body_width / 2.0                         # 650

x_front = wheelbase_length / 2.0                    # +1250
x_rear = -wheelbase_length / 2.0                    # -1250
x_mid = -150.0                                      # bogie forward wheel
y_wheel = track_width / 2.0                         # 990
y_susp = half_wid + 110.0                           # 760 suspension link plane

ROCKER_PIVOT = (150.0, y_susp, belly_z + 240.0)     # (150, 760, 800) left side
BOGIE_PIVOT = (-700.0, y_susp, 430.0)
STEER_TOP_Z = axle_z + 440.0                        # 700 actuator top
STEER_BOT_Z = axle_z + 300.0                        # 560 actuator bottom

MAST_XY = (780.0, -380.0)
MAST_TOP_Z = deck_z + mast_height                   # 2130
HEAD_PIVOT_Z = MAST_TOP_Z + 70.0                    # 2200 neck top / pitch pivot

# Robotic arm chain, sampling-hover display pose, all in the y=+200 plane.
ARM_Y = 200.0
ARM_AZIMUTH_XY = (1160.0, ARM_Y)
ARM_SHOULDER = (1160.0, ARM_Y, 760.0)
_upper_dir = (math.cos(math.radians(-20.0)), 0.0, math.sin(math.radians(-20.0)))
_fore_dir = (math.cos(math.radians(-25.0)), 0.0, math.sin(math.radians(-25.0)))
_wrist_dir = (math.cos(math.radians(-60.0)), 0.0, math.sin(math.radians(-60.0)))
ARM_UPPER_LEN = 640.0
ARM_FORE_LEN = 560.0
ARM_WRIST_LEN = 150.0
ARM_ELBOW = (
    ARM_SHOULDER[0] + _upper_dir[0] * ARM_UPPER_LEN,
    ARM_Y,
    ARM_SHOULDER[2] + _upper_dir[2] * ARM_UPPER_LEN,
)
ARM_WRIST = (
    ARM_ELBOW[0] + _fore_dir[0] * ARM_FORE_LEN,
    ARM_Y,
    ARM_ELBOW[2] + _fore_dir[2] * ARM_FORE_LEN,
)
ARM_TURRET = (
    ARM_WRIST[0] + _wrist_dir[0] * ARM_WRIST_LEN,
    ARM_Y,
    ARM_WRIST[2] + _wrist_dir[2] * ARM_WRIST_LEN,
)

HGA_BASE = (-520.0, 420.0)
HGA_ELEV_PIVOT = (-520.0, 420.0, 1360.0)
HGA_BORESIGHT = (-math.sin(math.radians(35.0)), 0.0, math.cos(math.radians(35.0)))

SOLAR_HINGE_Z = deck_z + 6.0
SOLAR_DEPLOY_DEG = 102.0                            # display pose deploy angle
SOLAR_SPAN = 620.0
SOLAR_CHORD = 1000.0

RTG_MOUNT = (-1060.0, 0.0, 1060.0)
RTG_DIR = (-math.cos(math.radians(8.0)), 0.0, -math.sin(math.radians(8.0)))

COLORS = {
    "ivory_panel": "#e7e3da",
    "graphite_panel": "#3c3f42",
    "satin_titanium": "#adafaa",
    "brushed_steel": "#bcbfc2",
    "pale_aluminum": "#d4d7d4",
    "fastener_steel": "#76797c",
    "wheel_graphite": "#424446",
    "grouser_steel": "#696a6c",
    "jpl_orange": "#ff953f",
    "copper_band": "#d38b59",
    "gold_mli": "#edc461",
    "avionics_blue": "#4b6fad",
    "solar_cell": "#213865",
    "science_teal": "#30a099",
    "white_thermal": "#f1f3f6",
    "black_cable": "#212123",
    "battery_orange": "#f9a627",
    "mars_regolith": "#ad6f4b",
    "mars_rock": "#6f4d3c",
    "dust_tan": "#cb996f",
    "boot_rubber": "#303032",
    "dish_white": "#f3f3f1",
    "rtg_core": "#595b5d",
    "rtg_fin": "#e5e7ea",
    "camera_lens": "#27303f",
}


Vector3 = tuple[float, float, float]


def v_add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a: Vector3, scalar: float) -> Vector3:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def v_dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_len(a: Vector3) -> float:
    return math.sqrt(v_dot(a, a))


def v_norm(a: Vector3) -> Vector3:
    length = v_len(a)
    if length <= 1e-9:
        raise ValueError("zero-length vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _apply_rover_scale(shape: bd.Shape) -> bd.Shape:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    if abs(rover_scale - 1.0) < 1e-9:
        return shape
    trsf = gp_Trsf()
    trsf.SetScale(gp_Pnt(0.0, 0.0, 0.0), rover_scale)
    return bd.Shape(obj=BRepBuilderAPI_Transform(shape.wrapped, trsf, True).Shape())


def style(shape: bd.Shape, label: str, color_name: str) -> bd.Shape:
    shape = _apply_rover_scale(shape)
    shape.label = label
    shape.color = bd.Color(COLORS[color_name])
    return shape


def group(label: str, children: Sequence[bd.Shape], color_name: str | None = None) -> bd.Compound:
    compound = bd.Compound(obj=list(children), children=list(children), label=label)
    if color_name is not None:
        compound.color = bd.Color(COLORS[color_name])
    return compound


def transformed(shape: bd.Shape, center: Vector3, axis_x: Vector3, axis_y: Vector3, axis_z: Vector3) -> bd.Shape:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
    x_dir = v_norm(axis_x)
    y_dir = v_norm(axis_y)
    z_dir = v_norm(axis_z)
    trsf = gp_Trsf()
    trsf.SetValues(
        x_dir[0], y_dir[0], z_dir[0], center[0],
        x_dir[1], y_dir[1], z_dir[1], center[1],
        x_dir[2], y_dir[2], z_dir[2], center[2],
    )
    return bd.Shape(obj=BRepBuilderAPI_Transform(shape.wrapped, trsf, True).Shape())


def oriented_box(
    label: str,
    center: Vector3,
    size_x: float,
    size_y: float,
    size_z: float,
    axis_x: Vector3 = (1.0, 0.0, 0.0),
    axis_y: Vector3 = (0.0, 1.0, 0.0),
    axis_z: Vector3 = (0.0, 0.0, 1.0),
    color_name: str = "pale_aluminum",
    fillet_radius: float = 0.0,
) -> bd.Shape:
    shape = transformed(bd.Box(size_x, size_y, size_z), center, axis_x, axis_y, axis_z)
    if fillet_radius > 0.0:
        shape = softened(shape, fillet_radius)
    return style(shape, label, color_name)


def cylinder_between(label: str, p1: Vector3, p2: Vector3, radius: float, color_name: str) -> bd.Shape:
    axis = v_sub(p2, p1)
    length = v_len(axis)
    if length <= 1e-6:
        return style(bd.Sphere(radius).moved(bd.Location(p1)), label, color_name)
    direction = v_norm(axis)
    cylinder = bd.Cylinder(radius, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return style(cylinder.moved(bd.Plane(origin=p1, z_dir=direction).location), label, color_name)


def cylinder_x(label: str, center: Vector3, radius: float, length: float, color_name: str) -> bd.Shape:
    return style(bd.Cylinder(radius, length, rotation=(0, 90, 0)).moved(bd.Location(center)), label, color_name)


def cylinder_y(label: str, center: Vector3, radius: float, length: float, color_name: str) -> bd.Shape:
    return style(bd.Cylinder(radius, length, rotation=(90, 0, 0)).moved(bd.Location(center)), label, color_name)


def cylinder_z(label: str, center: Vector3, radius: float, length: float, color_name: str) -> bd.Shape:
    return style(bd.Cylinder(radius, length).moved(bd.Location(center)), label, color_name)


def ball(label: str, center: Vector3, radius: float, color_name: str) -> bd.Shape:
    return style(bd.Sphere(radius).moved(bd.Location(center)), label, color_name)


def softened(shape: bd.Shape, radius: float) -> bd.Shape:
    # Large panels and machined housings get true BREP fillets; the hundreds of
    # small grousers, bolts, tubes, and cells keep crisp edges so the export
    # stays fast and robust.
    if radius < 0.95:
        return shape
    try:
        return bd.fillet(shape.edges(), radius=radius)
    except Exception:
        try:
            return bd.chamfer(shape.edges(), length=radius * 0.35)
        except Exception:
            return shape


def annular_y(label: str, center: Vector3, outer_radius: float, inner_radius: float, length: float, color_name: str) -> bd.Shape:
    outer = bd.Cylinder(outer_radius, length, rotation=(90, 0, 0)).moved(bd.Location(center))
    inner = bd.Cylinder(inner_radius, length + 4.0, rotation=(90, 0, 0)).moved(bd.Location(center))
    return style(outer - inner, label, color_name)


def rock(label: str, center_xy: tuple[float, float], size: float, squash: float, yaw_deg: float, color_name: str = "mars_rock") -> bd.Shape:
    body = bd.scale(bd.Sphere(size), by=(1.0, 0.82, squash))
    body = body.rotate(bd.Axis.Z, yaw_deg)
    body = body.moved(bd.Location((center_xy[0], center_xy[1], size * squash * 0.42)))
    return style(body, label, color_name)


# ---------------------------------------------------------------------------
# Terrain diorama
# ---------------------------------------------------------------------------

def terrain() -> bd.Compound:
    with bd.BuildPart() as slab_part:
        with bd.BuildSketch(bd.Plane.XY):
            bd.RectangleRounded(5200.0, 3600.0, 300.0)
        bd.extrude(amount=-90.0)
    slab = slab_part.part.moved(bd.Location((150.0, 0.0, 0.0)))
    parts: list[bd.Shape] = [style(slab, "terrain_regolith_slab", "mars_regolith")]

    rk = terrain_rock_height / 120.0
    rock_table = [
        ((1900.0, 990.0), 138.0, 0.60, 15.0),   # climb target ahead of front-left wheel
        ((2050.0, -600.0), 120.0, 0.55, 40.0),
        ((1750.0, -1350.0), 90.0, 0.62, 75.0),
        ((600.0, 1500.0), 72.0, 0.58, 10.0),
        ((-400.0, -1650.0), 156.0, 0.52, 55.0),
        ((-1800.0, 1300.0), 102.0, 0.60, 20.0),
        ((-2050.0, -800.0), 78.0, 0.65, 65.0),
        ((1200.0, 1650.0), 60.0, 0.62, 30.0),
        ((-900.0, 1750.0), 132.0, 0.55, 85.0),
        ((2500.0, 300.0), 54.0, 0.66, 50.0),
    ]
    for index, (xy, size, squash, yaw) in enumerate(rock_table, start=1):
        parts.append(rock(f"terrain_rock_{index:02d}", xy, size * rk, squash, yaw))

    parts.append(style(
        bd.Cylinder(260.0, 6.0).moved(bd.Location((900.0, 1050.0, 3.0))),
        "terrain_wheel_track_apron_left", "dust_tan"))
    parts.append(style(
        bd.Cylinder(230.0, 6.0).moved(bd.Location((-800.0, -1080.0, 3.0))),
        "terrain_wheel_track_apron_right", "dust_tan"))

    compound = group("terrain", parts, "mars_regolith")
    if abs(terrain_slope_angle) > 1e-6:
        rotated = bd.Compound(
            obj=list(compound.children), children=list(compound.children), label="terrain"
        ).rotate(bd.Axis((150.0, 0.0, 0.0), (0.0, 1.0, 0.0)), terrain_slope_angle)
        rotated.label = "terrain"
        rotated.color = bd.Color(COLORS["mars_regolith"])
        return rotated
    return compound


# ---------------------------------------------------------------------------
# Chassis structure and warm-body shell
# ---------------------------------------------------------------------------

def chassis_frame() -> bd.Compound:
    parts: list[bd.Shape] = []
    for z, tier in ((belly_z + 40.0, "lower"), (deck_z - 30.0, "upper")):
        for s, side in ((1.0, "left"), (-1.0, "right")):
            parts.append(oriented_box(
                f"chassis_{tier}_rail_{side}", (0.0, s * (half_wid - 90.0), z),
                body_length - 40.0, 56.0, 40.0, color_name="satin_titanium"))
    for x, station in ((-850.0, "aft"), (0.0, "mid"), (850.0, "forward")):
        parts.append(oriented_box(
            f"chassis_cross_tube_{station}", (x, 0.0, belly_z + 40.0),
            40.0, body_width - 180.0, 40.0, color_name="satin_titanium"))
    for sx, sy, corner in ((1, 1, "front_left"), (1, -1, "front_right"), (-1, 1, "rear_left"), (-1, -1, "rear_right")):
        parts.append(oriented_box(
            f"chassis_corner_post_{corner}", (sx * (half_len - 60.0), sy * (half_wid - 90.0), belly_z + body_height / 2.0),
            46.0, 46.0, body_height - 60.0, color_name="satin_titanium"))
    for s, side in ((1.0, "left"), (-1.0, "right")):
        parts.append(cylinder_y(
            f"rocker_pivot_boss_{side}", (ROCKER_PIVOT[0], s * (half_wid + 31.0), ROCKER_PIVOT[2]),
            80.0, 62.0, "pale_aluminum"))
        parts.append(oriented_box(
            f"rocker_boss_gusset_upper_{side}", (ROCKER_PIVOT[0], s * (half_wid + 6.0), ROCKER_PIVOT[2] + 105.0),
            150.0, 26.0, 150.0, color_name="pale_aluminum"))
        parts.append(oriented_box(
            f"rocker_boss_gusset_lower_{side}", (ROCKER_PIVOT[0], s * (half_wid + 6.0), ROCKER_PIVOT[2] - 105.0),
            150.0, 26.0, 150.0, color_name="pale_aluminum"))
    parts.append(oriented_box(
        "arm_mount_bracket", (half_len + 42.0, ARM_Y, 730.0),
        90.0, 140.0, 170.0, color_name="pale_aluminum", fillet_radius=4.0))
    parts.append(oriented_box(
        "arm_mount_gusset_left", (half_len + 30.0, ARM_Y + 62.0, 700.0),
        60.0, 18.0, 120.0, color_name="pale_aluminum"))
    parts.append(oriented_box(
        "arm_mount_gusset_right", (half_len + 30.0, ARM_Y - 62.0, 700.0),
        60.0, 18.0, 120.0, color_name="pale_aluminum"))
    parts.append(oriented_box(
        "differential_pedestal", (430.0, 0.0, deck_z + 30.0),
        90.0, 90.0, 60.0, color_name="pale_aluminum"))
    parts.append(oriented_box(
        "rear_tow_lug", (-half_len - 15.0, 0.0, belly_z + 60.0),
        60.0, 120.0, 40.0, color_name="satin_titanium"))
    return group("chassis_frame", parts, "satin_titanium")


def body_core() -> bd.Compound:
    parts = [
        oriented_box("equipment_floor_plate", (0.0, 0.0, belly_z + 28.0),
                     body_length - 60.0, body_width - 80.0, 16.0, color_name="pale_aluminum"),
        oriented_box("equipment_rail_left", (0.0, 350.0, belly_z + 44.0),
                     1900.0, 30.0, 20.0, color_name="brushed_steel"),
        oriented_box("equipment_rail_right", (0.0, -350.0, belly_z + 44.0),
                     1900.0, 30.0, 20.0, color_name="brushed_steel"),
        oriented_box("bay_bulkhead", (100.0, 0.0, belly_z + 190.0),
                     16.0, body_width - 80.0, 300.0, color_name="pale_aluminum"),
    ]
    return group("body_core", parts, "pale_aluminum")


def body_shell() -> bd.Compound:
    parts = [
        oriented_box("belly_pan", (0.0, 0.0, belly_z + 9.0),
                     body_length - 20.0, body_width - 40.0, 18.0,
                     color_name="graphite_panel", fillet_radius=4.0),
        oriented_box("front_panel", (half_len - 10.0, 0.0, belly_z + body_height / 2.0),
                     20.0, body_width, body_height, color_name="ivory_panel", fillet_radius=5.0),
        oriented_box("rear_panel", (-half_len + 10.0, 0.0, belly_z + body_height / 2.0),
                     20.0, body_width, body_height, color_name="ivory_panel", fillet_radius=5.0),
        oriented_box("side_panel_right", (0.0, -half_wid + 12.0, belly_z + body_height / 2.0),
                     body_length - 20.0, 24.0, body_height, color_name="graphite_panel", fillet_radius=5.0),
        oriented_box("deck_plate_rear", (-470.0, 0.0, deck_z - 11.0),
                     1140.0, body_width - 20.0, 22.0, color_name="ivory_panel", fillet_radius=5.0),
        oriented_box("deck_plate_front_right", (575.0, -385.0, deck_z - 11.0),
                     920.0, 510.0, 22.0, color_name="ivory_panel", fillet_radius=5.0),
        oriented_box("deck_trim_rail_left", (0.0, half_wid - 8.0, deck_z + 6.0),
                     body_length - 20.0, 16.0, 10.0, color_name="copper_band"),
        oriented_box("deck_trim_rail_right", (0.0, -half_wid + 8.0, deck_z + 6.0),
                     body_length - 20.0, 16.0, 10.0, color_name="copper_band"),
    ]
    return group("body_shell", parts, "ivory_panel")


def deck_lid() -> bd.Compound:
    # Front-left deck plate: the cutaway lid `lid_lift` raises to reveal the
    # avionics/power/science bays. The dust patch rides on the lid
    # (`deck_lid_dust_patch`).
    parts = [
        oriented_box("deck_lid_plate", (575.0, 255.0, deck_z - 11.0),
                     920.0, 770.0, 22.0, color_name="ivory_panel", fillet_radius=5.0),
        oriented_box("deck_lid_stiffener_fore", (820.0, 255.0, deck_z - 30.0),
                     30.0, 700.0, 16.0, color_name="pale_aluminum"),
        oriented_box("deck_lid_stiffener_aft", (330.0, 255.0, deck_z - 30.0),
                     30.0, 700.0, 16.0, color_name="pale_aluminum"),
        oriented_box("deck_lid_handle", (575.0, 560.0, deck_z + 12.0),
                     140.0, 24.0, 20.0, color_name="jpl_orange"),
    ]
    for index, (bx, by) in enumerate(
        [(160.0, -85.0), (990.0, -85.0), (160.0, 595.0), (990.0, 595.0)], start=1
    ):
        parts.append(cylinder_z(f"deck_lid_bolt_{index}", (bx, by, deck_z + 2.0), 9.0, 8.0, "fastener_steel"))
    parts.append(style(
        bd.Cylinder(150.0, 4.0).moved(bd.Location((600.0, 350.0, deck_z + 2.0))),
        "deck_lid_dust_patch", "dust_tan"))
    return group("deck_lid", parts, "ivory_panel")


def side_panel_left() -> bd.Compound:
    parts = [
        oriented_box("side_panel_left_plate", (0.0, half_wid - 12.0, belly_z + body_height / 2.0),
                     body_length - 20.0, 24.0, body_height, color_name="graphite_panel", fillet_radius=5.0),
        oriented_box("side_panel_left_emblem", (350.0, half_wid + 2.0, belly_z + body_height / 2.0 + 90.0),
                     260.0, 6.0, 150.0, color_name="ivory_panel"),
        oriented_box("side_panel_left_stripe", (0.0, half_wid + 1.0, belly_z + 90.0),
                     body_length - 120.0, 5.0, 44.0, color_name="jpl_orange"),
    ]
    return group("side_panel_left", parts, "graphite_panel")


def access_panels() -> bd.Compound:
    parts: list[bd.Shape] = []
    panel_specs = [
        ("access_panel_right_forward", (450.0, -half_wid - 4.0, 860.0), (300.0, 8.0, 220.0), "y"),
        ("access_panel_right_aft", (-350.0, -half_wid - 4.0, 860.0), (300.0, 8.0, 220.0), "y"),
        ("access_panel_rear", (-half_len - 4.0, -280.0, 900.0), (8.0, 260.0, 200.0), "x"),
    ]
    for label, center, size, normal in panel_specs:
        parts.append(oriented_box(label, center, *size, color_name="pale_aluminum"))
        dx = size[0] / 2.0 - 24.0 if normal == "y" else 0.0
        dy = size[1] / 2.0 - 24.0 if normal == "x" else 0.0
        dz = size[2] / 2.0 - 24.0
        for index, (su, sv) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)], start=1):
            if normal == "y":
                bolt_center = (center[0] + su * dx, center[1] - 5.0, center[2] + sv * dz)
                parts.append(cylinder_y(f"{label}_bolt_{index}", bolt_center, 5.0, 8.0, "fastener_steel"))
            else:
                bolt_center = (center[0] - 5.0, center[1] + su * dy, center[2] + sv * dz)
                parts.append(cylinder_x(f"{label}_bolt_{index}", bolt_center, 5.0, 8.0, "fastener_steel"))
    return group("access_panels", parts, "pale_aluminum")


def thermal_control() -> bd.Compound:
    parts: list[bd.Shape] = []
    for index in range(8):
        parts.append(oriented_box(
            f"thermal_louver_fin_{index + 1:02d}", (-700.0, -half_wid - 8.0, 690.0 + index * 42.0),
            220.0, 30.0, 8.0, color_name="white_thermal"))
    parts.append(oriented_box(
        "radiator_plate_forward", (700.0, -385.0, deck_z + 5.0),
        360.0, 300.0, 10.0, color_name="white_thermal"))
    parts.append(oriented_box(
        "mli_gold_blanket_left", (-700.0, 300.0, deck_z + 4.0),
        300.0, 360.0, 8.0, color_name="gold_mli"))
    parts.append(oriented_box(
        "mli_gold_blanket_right", (-700.0, -300.0, deck_z + 4.0),
        300.0, 360.0, 8.0, color_name="gold_mli"))
    parts.append(oriented_box(
        "mli_rtg_mount_wrap", (-half_len + 4.0, 0.0, 1000.0),
        12.0, 420.0, 260.0, color_name="gold_mli"))
    return group("thermal_control", parts, "white_thermal")


# ---------------------------------------------------------------------------
# Internal packaging (revealed by the cutaway)
# ---------------------------------------------------------------------------

def internals_avionics() -> bd.Compound:
    parts = [
        oriented_box("avionics_stack_primary", (500.0, 180.0, 705.0),
                     300.0, 260.0, 230.0, color_name="avionics_blue", fillet_radius=3.0),
        oriented_box("avionics_stack_secondary", (500.0, -120.0, 685.0),
                     240.0, 220.0, 190.0, color_name="avionics_blue", fillet_radius=3.0),
        oriented_box("flight_computer_vault", (230.0, 260.0, 665.0),
                     190.0, 170.0, 150.0, color_name="gold_mli", fillet_radius=3.0),
        oriented_box("radio_transponder", (230.0, 80.0, 655.0),
                     160.0, 140.0, 120.0, color_name="brushed_steel", fillet_radius=3.0),
        oriented_box("power_distribution_block", (390.0, 30.0, 640.0),
                     110.0, 90.0, 80.0, color_name="copper_band"),
    ]
    return group("internals_avionics", parts, "avionics_blue")


def internals_power() -> bd.Compound:
    parts = [
        oriented_box("battery_module_a", (230.0, -150.0, 675.0),
                     260.0, 140.0, 170.0, color_name="battery_orange", fillet_radius=3.0),
        oriented_box("battery_module_b", (230.0, -310.0, 675.0),
                     260.0, 140.0, 170.0, color_name="battery_orange", fillet_radius=3.0),
        oriented_box("battery_bus_bar", (230.0, -230.0, 770.0),
                     200.0, 240.0, 20.0, color_name="copper_band"),
    ]
    return group("internals_power", parts, "battery_orange")


def science_payloads() -> bd.Compound:
    parts: list[bd.Shape] = []
    module_count = max(0, min(6, round(science_payload_density * 6.0)))
    module_positions = [
        (-250.0, 320.0), (-250.0, 120.0), (-250.0, -80.0),
        (-250.0, -280.0), (-520.0, 220.0), (-520.0, 0.0),
    ]
    for index in range(module_count):
        px, py = module_positions[index]
        parts.append(oriented_box(
            f"science_module_{index + 1:02d}", (px, py, 670.0),
            180.0, 160.0, 140.0, color_name="science_teal", fillet_radius=3.0))

    deck_count = max(0, min(3, round(science_payload_density * 3.0)))
    if deck_count >= 1:
        parts.append(cylinder_z("weather_boom_mast", (-150.0, 560.0, deck_z + 210.0), 12.0, 420.0, "pale_aluminum"))
        parts.append(oriented_box("weather_sensor_pod", (-150.0, 560.0, deck_z + 430.0),
                                  90.0, 60.0, 50.0, color_name="brushed_steel"))
    if deck_count >= 2:
        parts.append(cylinder_z("calibration_target_disc", (-870.0, -350.0, deck_z + 6.0), 46.0, 12.0, "ivory_panel"))
        for index in range(5):
            parts.append(cylinder_z(
                f"sample_tube_{index + 1}", (-870.0 + (index - 2) * 34.0, -480.0, deck_z + 46.0),
                10.0, 92.0, "brushed_steel"))
    if deck_count >= 3:
        parts.append(oriented_box("spectrometer_deck_unit", (-560.0, -480.0, deck_z + 60.0),
                                  160.0, 120.0, 120.0, color_name="science_teal", fillet_radius=3.0))
    return group("science_payloads", parts, "science_teal")


def cable_harness() -> bd.Compound:
    parts: list[bd.Shape] = []
    trunk = [
        ((620.0, 180.0, 615.0), (300.0, 180.0, 615.0)),
        ((300.0, 180.0, 615.0), (300.0, -150.0, 615.0)),
        ((300.0, 180.0, 615.0), (-150.0, 180.0, 615.0)),
        ((-150.0, 180.0, 615.0), (-150.0, -300.0, 615.0)),
        ((-150.0, 180.0, 615.0), (-700.0, 180.0, 615.0)),
        ((-700.0, 180.0, 615.0), (-980.0, 60.0, 900.0)),
        ((620.0, 180.0, 615.0), (620.0, -380.0, 615.0)),
        ((620.0, -380.0, 615.0), (760.0, -380.0, 615.0)),
        ((760.0, -380.0, 615.0), (760.0, -380.0, 1160.0)),
        ((620.0, 180.0, 615.0), (980.0, 200.0, 640.0)),
        ((980.0, 200.0, 640.0), (1040.0, 200.0, 700.0)),
    ]
    for index, (p1, p2) in enumerate(trunk, start=1):
        parts.append(cylinder_between(f"harness_trunk_{index:02d}", p1, p2, 16.0, "black_cable"))
    band_points = [
        (460.0, 180.0, 615.0), (300.0, 20.0, 615.0), (-150.0, -60.0, 615.0),
        (-420.0, 180.0, 615.0), (760.0, -380.0, 900.0),
    ]
    for index, center in enumerate(band_points, start=1):
        parts.append(cylinder_between(
            f"harness_band_{index}", v_add(center, (-11.0, 0.0, 0.0)) if abs(center[2] - 615.0) < 1.0 else v_add(center, (0.0, 0.0, -11.0)),
            v_add(center, (11.0, 0.0, 0.0)) if abs(center[2] - 615.0) < 1.0 else v_add(center, (0.0, 0.0, 11.0)),
            19.0, "jpl_orange"))
    for s, side in ((1.0, "left"), (-1.0, "right")):
        parts.append(cylinder_between(
            f"rocker_service_loop_{side}_a", (100.0, s * (half_wid + 2.0), 830.0),
            (120.0, s * (half_wid + 40.0), 810.0), 9.0, "black_cable"))
        parts.append(cylinder_between(
            f"rocker_service_loop_{side}_b", (120.0, s * (half_wid + 40.0), 810.0),
            (ROCKER_PIVOT[0], s * (half_wid + 62.0), ROCKER_PIVOT[2]), 9.0, "black_cable"))
    return group("cable_harness", parts, "black_cable")


def dust_covers() -> bd.Compound:
    parts: list[bd.Shape] = []
    for s, side in ((1.0, "left"), (-1.0, "right")):
        parts.append(cylinder_y(
            f"rocker_pivot_boot_{side}", (ROCKER_PIVOT[0], s * (y_susp - 34.0), ROCKER_PIVOT[2]),
            95.0, 46.0, "boot_rubber"))
        parts.append(cylinder_y(
            f"bogie_pivot_boot_{side}", (BOGIE_PIVOT[0], s * (y_susp - 34.0), BOGIE_PIVOT[2]),
            70.0, 40.0, "boot_rubber"))
    mast_x, mast_y = MAST_XY
    for index, (radius, z) in enumerate([(78.0, deck_z + 12.0), (66.0, deck_z + 28.0), (78.0, deck_z + 44.0)], start=1):
        parts.append(cylinder_z(f"mast_bellows_ring_{index}", (mast_x, mast_y, z), radius, 16.0, "boot_rubber"))
    parts.append(style(
        bd.Cone(80.0, 50.0, 60.0).moved(bd.Location((ARM_AZIMUTH_XY[0], ARM_AZIMUTH_XY[1], 830.0))),
        "arm_shoulder_boot", "boot_rubber"))
    return group("dust_covers", parts, "boot_rubber")


def dust_layer() -> bd.Compound:
    parts = [
        style(bd.Cylinder(180.0, 4.0).moved(bd.Location((-600.0, 150.0, deck_z + 2.0))),
              "deck_dust_patch_aft", "dust_tan"),
        style(bd.Cylinder(140.0, 4.0).moved(bd.Location((-350.0, -280.0, deck_z + 2.0))),
              "deck_dust_patch_mid", "dust_tan"),
        style(bd.Cylinder(120.0, 4.0).moved(bd.Location((400.0, -300.0, deck_z + 2.0))),
              "deck_dust_patch_forward", "dust_tan"),
        oriented_box("deck_dust_streak", (-850.0, 420.0, deck_z + 2.0),
                     400.0, 120.0, 4.0, color_name="dust_tan"),
        oriented_box("rear_panel_dust_film", (-half_len - 21.0, 100.0, 760.0),
                     6.0, 500.0, 240.0, color_name="dust_tan"),
    ]
    return group("dust_layer", parts, "dust_tan")


# ---------------------------------------------------------------------------
# Rocker-bogie suspension
# ---------------------------------------------------------------------------

def rocker(s: float, side: str) -> bd.Compound:
    pivot = (ROCKER_PIVOT[0], s * ROCKER_PIVOT[1], ROCKER_PIVOT[2])
    front_elbow = (1150.0, s * y_susp, 660.0)
    steer_mount = (x_front, s * y_wheel, STEER_TOP_Z)
    bogie_pt = (BOGIE_PIVOT[0], s * BOGIE_PIVOT[1], BOGIE_PIVOT[2])
    parts = [
        # the accent hub cap, named for its accent colour
        cylinder_y(f"rocker_{side}_pivot_accent_cap", (pivot[0], s * (y_susp + 52.0), pivot[2]), 48.0, 14.0, "jpl_orange"),
        cylinder_y(f"rocker_{side}_pivot_hub", pivot, 70.0, 90.0, "satin_titanium"),
        cylinder_between(f"rocker_{side}_front_tube", pivot, front_elbow, 34.0, "satin_titanium"),
        ball(f"rocker_{side}_front_elbow", front_elbow, 42.0, "satin_titanium"),
        cylinder_between(f"rocker_{side}_steer_diagonal", front_elbow, steer_mount, 30.0, "satin_titanium"),
        ball(f"rocker_{side}_steer_elbow", steer_mount, 42.0, "satin_titanium"),
        oriented_box(f"rocker_{side}_steer_mount_plate", (steer_mount[0], steer_mount[1], steer_mount[2] + 8.0),
                     100.0, 100.0, 16.0, color_name="pale_aluminum"),
        cylinder_between(f"rocker_{side}_rear_tube", pivot, bogie_pt, 34.0, "satin_titanium"),
        ball(f"rocker_{side}_bogie_end", bogie_pt, 40.0, "satin_titanium"),
        cylinder_between(f"rocker_{side}_differential_post", (150.0, s * y_susp, 860.0),
                         (150.0, s * 700.0, 985.0), 15.0, "brushed_steel"),
        ball(f"rocker_{side}_differential_ball", (150.0, s * 700.0, 985.0), 20.0, "brushed_steel"),
    ]
    return group(f"rocker_{side}", parts, "satin_titanium")


def mid_wheel_fork(parts: list[bd.Shape], s: float, side: str) -> None:
    yw = s * y_wheel
    parts.append(cylinder_between(f"bogie_{side}_fork_support", (x_mid, s * y_susp, 480.0),
                                  (x_mid, yw, 620.0), 26.0, "satin_titanium"))
    parts.append(cylinder_z(f"bogie_{side}_fork_boss", (x_mid, yw, 615.0), 40.0, 50.0, "satin_titanium"))
    parts.append(cylinder_between(f"bogie_{side}_fork_over_arm", (x_mid, yw, 590.0),
                                  (x_mid, s * 790.0, 590.0), 26.0, "satin_titanium"))
    parts.append(cylinder_between(f"bogie_{side}_fork_drop_tube", (x_mid, s * 790.0, 590.0),
                                  (x_mid, s * 790.0, axle_z), 28.0, "satin_titanium"))
    parts.append(cylinder_between(f"bogie_{side}_axle_housing", (x_mid, s * 790.0, axle_z),
                                  (x_mid, s * 855.0, axle_z), 30.0, "satin_titanium"))
    parts.append(cylinder_y(f"bogie_{side}_drive_motor", (x_mid, s * 910.0, axle_z), 64.0, 100.0, "brushed_steel"))
    parts.append(cylinder_y(f"bogie_{side}_motor_band", (x_mid, s * 868.0, axle_z), 66.0, 14.0, "copper_band"))


def bogie(s: float, side: str) -> bd.Compound:
    pivot = (BOGIE_PIVOT[0], s * BOGIE_PIVOT[1], BOGIE_PIVOT[2])
    front_elbow = (x_mid, s * y_susp, 480.0)
    rear_elbow = (-1150.0, s * y_susp, 560.0)
    rear_mount = (x_rear, s * y_wheel, STEER_TOP_Z)
    parts: list[bd.Shape] = [
        cylinder_y(f"bogie_{side}_pivot_accent_cap", (pivot[0], s * (y_susp + 42.0), pivot[2]), 40.0, 12.0, "jpl_orange"),
        cylinder_y(f"bogie_{side}_pivot_hub", pivot, 55.0, 70.0, "satin_titanium"),
        cylinder_between(f"bogie_{side}_front_arm", pivot, front_elbow, 30.0, "satin_titanium"),
        ball(f"bogie_{side}_front_elbow", front_elbow, 38.0, "satin_titanium"),
        cylinder_between(f"bogie_{side}_rear_arm", pivot, rear_elbow, 30.0, "satin_titanium"),
        ball(f"bogie_{side}_rear_elbow", rear_elbow, 38.0, "satin_titanium"),
        cylinder_between(f"bogie_{side}_rear_diagonal", rear_elbow, rear_mount, 28.0, "satin_titanium"),
        ball(f"bogie_{side}_rear_mount_elbow", rear_mount, 40.0, "satin_titanium"),
        oriented_box(f"bogie_{side}_rear_mount_plate", (rear_mount[0], rear_mount[1], rear_mount[2] + 8.0),
                     100.0, 100.0, 16.0, color_name="pale_aluminum"),
    ]
    mid_wheel_fork(parts, s, side)
    return group(f"bogie_{side}", parts, "satin_titanium")


def differential() -> bd.Compound:
    parts = [
        cylinder_z("differential_accent_cap", (430.0, 0.0, 1262.0), 30.0, 14.0, "jpl_orange"),
        oriented_box("differential_bar", (430.0, 0.0, 1235.0), 64.0, 1120.0, 44.0,
                     color_name="satin_titanium", fillet_radius=4.0),
        cylinder_z("differential_center_boss", (430.0, 0.0, 1240.0), 42.0, 40.0, "pale_aluminum"),
        ball("differential_end_ball_left", (430.0, 560.0, 1235.0), 26.0, "brushed_steel"),
        ball("differential_end_ball_right", (430.0, -560.0, 1235.0), 26.0, "brushed_steel"),
        cylinder_between("differential_link_left", (430.0, 560.0, 1225.0), (150.0, 700.0, 990.0), 13.0, "brushed_steel"),
        cylinder_between("differential_link_right", (430.0, -560.0, 1225.0), (150.0, -700.0, 990.0), 13.0, "brushed_steel"),
    ]
    return group("differential", parts, "satin_titanium")


def steering_fork(x0: float, s: float, label: str) -> bd.Compound:
    yw = s * y_wheel
    parts = [
        cylinder_z(f"{label}_accent_band", (x0, yw, 690.0), 60.0, 16.0, "jpl_orange"),
        cylinder_z(f"{label}_steer_actuator", (x0, yw, (STEER_TOP_Z + STEER_BOT_Z) / 2.0), 55.0,
                   STEER_TOP_Z - STEER_BOT_Z, "pale_aluminum"),
        cylinder_between(f"{label}_over_arm", (x0, yw, 590.0), (x0, s * 790.0, 590.0), 26.0, "pale_aluminum"),
        cylinder_between(f"{label}_drop_tube", (x0, s * 790.0, 590.0), (x0, s * 790.0, axle_z), 28.0, "pale_aluminum"),
        cylinder_between(f"{label}_axle_housing", (x0, s * 790.0, axle_z), (x0, s * 855.0, axle_z), 30.0, "pale_aluminum"),
        cylinder_y(f"{label}_drive_motor", (x0, s * 910.0, axle_z), 64.0, 100.0, "brushed_steel"),
        cylinder_y(f"{label}_motor_band", (x0, s * 868.0, axle_z), 66.0, 14.0, "copper_band"),
        oriented_box(f"{label}_steer_horn", (x0 + 60.0, yw, 640.0), 70.0, 36.0, 24.0, color_name="pale_aluminum"),
    ]
    return group(label, parts, "pale_aluminum")


def wheel(x0: float, s: float, label: str) -> bd.Compound:
    y0 = s * y_wheel
    center = (x0, y0, axle_z)
    rim_outer = wheel_r - wheel_grouser_height
    rim_inner = rim_outer - 12.0
    parts: list[bd.Shape] = [
        cylinder_y(f"{label}_hub_accent_cap", (x0, y0 + s * 142.0, axle_z), 62.0, 14.0, "gold_mli"),
        annular_y(f"{label}_rim", center, rim_outer, rim_inner, wheel_width, "wheel_graphite"),
    ]
    # Grouser tips land exactly on wheel_diameter: center radius puts the bar
    # 6 mm into the rim skin and (wheel_grouser_height) proud of it.
    grouser_radial = wheel_grouser_height + 6.0
    grouser_center_r = rim_outer + grouser_radial / 2.0 - 6.0
    for index in range(wheel_grouser_count):
        theta = 2.0 * math.pi * index / wheel_grouser_count
        normal = (math.cos(theta), 0.0, math.sin(theta))
        tangent = (-math.sin(theta), 0.0, math.cos(theta))
        g_center = v_add(center, v_mul(normal, grouser_center_r))
        parts.append(oriented_box(
            f"{label}_grouser_{index + 1:02d}", g_center,
            24.0, wheel_width + 14.0, grouser_radial,
            tangent, (0.0, 1.0, 0.0), normal, "grouser_steel"))
    rib_offsets = [10.0, 70.0, 130.0, 40.0, 100.0][: max(0, min(5, wheel_rib_density))]
    for index, offset in enumerate(rib_offsets, start=1):
        parts.append(annular_y(
            f"{label}_stiffener_ring_{index}", (x0, y0 + s * offset, axle_z),
            rim_inner, rim_inner - 26.0, 12.0, "wheel_graphite"))
    for index in range(6):
        phi = 2.0 * math.pi * index / 6.0
        phi2 = phi + math.radians(14.0 if index % 2 == 0 else -14.0)
        p1 = (x0 + math.cos(phi) * 84.0, y0 + s * 112.0, axle_z + math.sin(phi) * 84.0)
        p2 = (x0 + math.cos(phi2) * (rim_inner - 4.0), y0 + s * 136.0, axle_z + math.sin(phi2) * (rim_inner - 4.0))
        parts.append(cylinder_between(f"{label}_spoke_{index + 1}", p1, p2, 15.0, "wheel_graphite"))
    parts.append(cylinder_y(f"{label}_hub_disc", (x0, y0 + s * 126.0, axle_z), 84.0, 26.0, "wheel_graphite"))
    parts.append(cylinder_y(f"{label}_center_cap", (x0, y0 + s * 152.0, axle_z), 28.0, 12.0, "fastener_steel"))
    for index in range(6):
        theta = 2.0 * math.pi * index / 6.0
        bolt_center = (x0 + math.cos(theta) * 46.0, y0 + s * 150.0, axle_z + math.sin(theta) * 46.0)
        parts.append(cylinder_y(f"{label}_hub_bolt_{index + 1}", bolt_center, 9.0, 10.0, "fastener_steel"))
    parts.append(cylinder_y(f"{label}_drive_shaft", (x0, y0 + s * 41.0, axle_z), 20.0, 140.0, "brushed_steel"))
    return group(label, parts, "wheel_graphite")


# ---------------------------------------------------------------------------
# Remote sensing mast
# ---------------------------------------------------------------------------

def mast_base() -> bd.Compound:
    mx, my = MAST_XY
    parts = [
        cylinder_z("mast_collar_accent", (mx, my, deck_z + 490.0), 60.0, 18.0, "jpl_orange"),
        cylinder_z("mast_pedestal", (mx, my, deck_z + 35.0), 90.0, 70.0, "pale_aluminum"),
        cylinder_z("mast_column_lower", (mx, my, deck_z + 240.0), 56.0, 480.0, "pale_aluminum"),
        cylinder_z("mast_column_upper", (mx, my, deck_z + 715.0), 46.0, 470.0, "pale_aluminum"),
        cylinder_x("mast_rems_boom", (mx + 120.0, my, 1840.0), 10.0, 240.0, "brushed_steel"),
        ball("mast_rems_sensor", (mx + 245.0, my, 1840.0), 16.0, "brushed_steel"),
        oriented_box("mast_junction_box", (mx - 70.0, my, deck_z + 90.0), 70.0, 50.0, 40.0,
                     color_name="graphite_panel"),
        cylinder_between("mast_cable_loop_a", (mx - 40.0, my + 80.0, deck_z + 4.0),
                         (mx - 20.0, my + 30.0, deck_z + 60.0), 8.0, "black_cable"),
        cylinder_between("mast_cable_loop_b", (mx - 20.0, my + 30.0, deck_z + 60.0),
                         (mx - 8.0, my + 8.0, deck_z + 120.0), 8.0, "black_cable"),
    ]
    return group("mast_base", parts, "pale_aluminum")


def mast_head() -> bd.Compound:
    mx, my = MAST_XY
    k = camera_head_scale
    pivot_z = HEAD_PIVOT_Z
    head_c = (mx, my, pivot_z + 90.0 * k)
    parts = [
        oriented_box("mast_head_accent_visor", (mx + 106.0 * k, my, head_c[2] + 30.0 * k),
                     6.0 * k, 320.0 * k, 26.0 * k, color_name="jpl_orange"),
        cylinder_z("mast_head_neck", (mx, my, pivot_z - 35.0), 38.0, 70.0, "pale_aluminum"),
        oriented_box("mast_head_housing", head_c, 210.0 * k, 320.0 * k, 180.0 * k,
                     color_name="ivory_panel", fillet_radius=6.0),
        cylinder_x("stereo_camera_left", (mx + 120.0 * k, my + 105.0 * k, head_c[2] + 20.0 * k),
                   34.0 * k, 60.0 * k, "graphite_panel"),
        cylinder_x("stereo_camera_right", (mx + 120.0 * k, my - 105.0 * k, head_c[2] + 20.0 * k),
                   34.0 * k, 60.0 * k, "graphite_panel"),
        cylinder_x("stereo_lens_left", (mx + 152.0 * k, my + 105.0 * k, head_c[2] + 20.0 * k),
                   26.0 * k, 6.0 * k, "camera_lens"),
        cylinder_x("stereo_lens_right", (mx + 152.0 * k, my - 105.0 * k, head_c[2] + 20.0 * k),
                   26.0 * k, 6.0 * k, "camera_lens"),
        cylinder_x("laser_spectrometer_aperture", (mx + 135.0 * k, my, head_c[2] + 62.0 * k),
                   16.0 * k, 90.0 * k, "brushed_steel"),
        cylinder_x("navcam_left", (mx + 112.0 * k, my + 48.0 * k, head_c[2] - 52.0 * k),
                   13.0 * k, 30.0 * k, "camera_lens"),
        cylinder_x("navcam_right", (mx + 112.0 * k, my - 48.0 * k, head_c[2] - 52.0 * k),
                   13.0 * k, 30.0 * k, "camera_lens"),
        oriented_box("mast_head_radiator_fin", (mx - 100.0 * k, my, head_c[2] + 40.0 * k),
                     16.0 * k, 240.0 * k, 60.0 * k, color_name="white_thermal"),
    ]
    return group("mast_head", parts, "ivory_panel")


# ---------------------------------------------------------------------------
# Robotic arm (azimuth -> shoulder -> elbow -> wrist -> instrument turret)
# ---------------------------------------------------------------------------

def arm_azimuth() -> bd.Compound:
    ax, ay = ARM_AZIMUTH_XY
    parts = [
        cylinder_z("arm_azimuth_accent_cap", (ax, ay, 806.0), 64.0, 12.0, "jpl_orange"),
        cylinder_z("arm_azimuth_housing", (ax, ay, 715.0), 62.0, 170.0, "pale_aluminum"),
        cylinder_z("arm_azimuth_flange", (ax, ay, 636.0), 70.0, 16.0, "pale_aluminum"),
        oriented_box("arm_shoulder_clevis_left", (ax, ay + 38.0, 770.0), 70.0, 16.0, 90.0,
                     color_name="pale_aluminum"),
        oriented_box("arm_shoulder_clevis_right", (ax, ay - 38.0, 770.0), 70.0, 16.0, 90.0,
                     color_name="pale_aluminum"),
    ]
    return group("arm_azimuth", parts, "pale_aluminum")


def _arm_link(label: str, start: Vector3, end: Vector3, tube_r: float, act_r: float,
              rib_width: float) -> list[bd.Shape]:
    direction = v_norm(v_sub(end, start))
    mid = v_mul(v_add(start, end), 0.5)
    up = v_norm(v_cross((0.0, 1.0, 0.0), direction))
    length = v_len(v_sub(end, start))
    return [
        cylinder_y(f"{label}_joint_accent_cap", (start[0], start[1] + 52.0, start[2]), act_r - 6.0, 12.0, "jpl_orange"),
        cylinder_y(f"{label}_joint_actuator", start, act_r, 90.0, "brushed_steel"),
        cylinder_between(f"{label}_main_tube", start, end, tube_r, "pale_aluminum"),
        oriented_box(f"{label}_stiffener_rib", v_add(mid, v_mul(up, tube_r + 10.0)),
                     length - 120.0, rib_width, 22.0,
                     direction, (0.0, 1.0, 0.0), up, "pale_aluminum"),
        cylinder_between(f"{label}_cable_run",
                         v_add(v_add(start, v_mul(direction, 60.0)), v_mul(up, tube_r + 26.0)),
                         v_add(v_add(end, v_mul(direction, -60.0)), v_mul(up, tube_r + 26.0)),
                         9.0, "black_cable"),
    ]


def arm_shoulder() -> bd.Compound:
    return group("arm_shoulder", _arm_link("arm_shoulder", ARM_SHOULDER, ARM_ELBOW, 44.0, 56.0, 60.0), "pale_aluminum")


def arm_elbow() -> bd.Compound:
    return group("arm_elbow", _arm_link("arm_elbow", ARM_ELBOW, ARM_WRIST, 36.0, 48.0, 48.0), "pale_aluminum")


def arm_wrist() -> bd.Compound:
    parts = [
        cylinder_y("arm_wrist_accent_cap", (ARM_WRIST[0], ARM_WRIST[1] + 46.0, ARM_WRIST[2]), 34.0, 12.0, "jpl_orange"),
        cylinder_y("arm_wrist_actuator", ARM_WRIST, 40.0, 70.0, "brushed_steel"),
        cylinder_between("arm_wrist_link_tube", ARM_WRIST, ARM_TURRET, 28.0, "pale_aluminum"),
    ]
    return group("arm_wrist", parts, "pale_aluminum")


def arm_turret() -> bd.Compound:
    n = _wrist_dir
    u1 = v_norm(v_cross((0.0, 1.0, 0.0), n))
    u2 = (0.0, 1.0, 0.0)
    t = ARM_TURRET
    face = v_add(t, v_mul(n, 45.0))
    parts = [
        cylinder_between("turret_accent_ring", v_add(t, v_mul(n, 38.0)), v_add(t, v_mul(n, 52.0)), 92.0, "jpl_orange"),
        cylinder_between("turret_hub_disc", v_add(t, v_mul(n, -45.0)), v_add(t, v_mul(n, 45.0)), 150.0, "pale_aluminum"),
        cylinder_between("turret_drill",
                         v_add(v_add(t, v_mul(u1, 85.0)), v_mul(n, 20.0)),
                         v_add(v_add(t, v_mul(u1, 85.0)), v_mul(n, 115.0)), 30.0, "brushed_steel"),
        oriented_box("turret_spectrometer", v_add(v_add(t, v_mul(u1, -85.0)), v_mul(n, 70.0)),
                     90.0, 70.0, 80.0, u1, u2, n, "science_teal"),
        cylinder_between("turret_abrasion_brush",
                         v_add(v_add(t, v_mul(u2, 85.0)), v_mul(n, 30.0)),
                         v_add(v_add(t, v_mul(u2, 85.0)), v_mul(n, 120.0)), 22.0, "fastener_steel"),
        oriented_box("turret_close_up_camera", v_add(v_add(t, v_mul(u2, -85.0)), v_mul(n, 62.0)),
                     60.0, 50.0, 55.0, u1, u2, n, "graphite_panel"),
        ball("turret_drill_bit_tip", v_add(v_add(t, v_mul(u1, 85.0)), v_mul(n, 120.0)), 12.0, "fastener_steel"),
    ]
    _ = face
    return group("arm_turret", parts, "pale_aluminum")


# ---------------------------------------------------------------------------
# Antennas and power
# ---------------------------------------------------------------------------

def antenna_hga_mast() -> bd.Compound:
    hx, hy = HGA_BASE
    parts = [
        cylinder_z("hga_accent_band", (hx, hy, 1318.0), 54.0, 12.0, "jpl_orange"),
        cylinder_z("hga_pedestal", (hx, hy, 1240.0), 60.0, 120.0, "pale_aluminum"),
        cylinder_z("hga_azimuth_drum", (hx, hy, 1330.0), 52.0, 60.0, "brushed_steel"),
    ]
    return group("antenna_hga_mast", parts, "pale_aluminum")


def antenna_hga_dish() -> bd.Compound:
    pivot = HGA_ELEV_PIVOT
    b = HGA_BORESIGHT
    dish_base = v_add(pivot, v_mul(b, 70.0))
    dish_open = v_add(pivot, v_mul(b, 120.0))
    up_ref = v_norm(v_cross(b, (0.0, 1.0, 0.0)))
    parts = [
        oriented_box("hga_yoke_left", (pivot[0], pivot[1] + 60.0, pivot[2]), 90.0, 16.0, 120.0,
                     color_name="pale_aluminum"),
        oriented_box("hga_yoke_right", (pivot[0], pivot[1] - 60.0, pivot[2]), 90.0, 16.0, 120.0,
                     color_name="pale_aluminum"),
        cylinder_y("hga_elevation_hub", pivot, 34.0, 140.0, "brushed_steel"),
        style(transformed(bd.Cone(30.0, 210.0, 50.0).moved(bd.Location((0.0, 0.0, 25.0))), dish_base,
                          (0.0, 1.0, 0.0), up_ref, b), "hga_dish_reflector", "dish_white"),
        style(transformed(bd.Cylinder(210.0, 12.0).moved(bd.Location((0.0, 0.0, -6.0))), dish_open,
                          (0.0, 1.0, 0.0), up_ref, b), "hga_dish_backing", "dish_white"),
        cylinder_between("hga_feed_rod", v_add(pivot, v_mul(b, 115.0)), v_add(pivot, v_mul(b, 265.0)),
                         8.0, "brushed_steel"),
        cylinder_between("hga_feed_horn", v_add(pivot, v_mul(b, 265.0)), v_add(pivot, v_mul(b, 285.0)),
                         22.0, "copper_band"),
    ]
    return group("antenna_hga_dish", parts, "dish_white")


def antenna_uhf() -> bd.Compound:
    ux, uy = -700.0, -430.0
    parts: list[bd.Shape] = [
        cylinder_z("uhf_ground_plane", (ux, uy, deck_z + 7.0), 95.0, 14.0, "pale_aluminum"),
        cylinder_z("uhf_core_mast", (ux, uy, deck_z + 145.0), 10.0, 270.0, "brushed_steel"),
    ]
    turns = 2.75
    segments = 22
    helix_r = 42.0
    z0 = deck_z + 20.0
    z1 = deck_z + 260.0
    prev = (ux + helix_r, uy, z0)
    for index in range(1, segments + 1):
        frac = index / segments
        angle = 2.0 * math.pi * turns * frac
        current = (ux + math.cos(angle) * helix_r, uy + math.sin(angle) * helix_r, z0 + (z1 - z0) * frac)
        parts.append(cylinder_between(f"uhf_helix_segment_{index:02d}", prev, current, 9.0, "copper_band"))
        prev = current
    parts.append(ball("uhf_helix_cap", prev, 12.0, "copper_band"))
    return group("antenna_uhf", parts, "copper_band")


def antenna_whips() -> bd.Compound:
    parts = [
        cylinder_z("lga_body", (-300.0, -480.0, deck_z + 85.0), 24.0, 150.0, "pale_aluminum"),
        style(bd.Cone(24.0, 10.0, 40.0).moved(bd.Location((-300.0, -480.0, deck_z + 180.0))),
              "lga_tip_cone", "pale_aluminum"),
        cylinder_z("lga_accent_ring", (-300.0, -480.0, deck_z + 24.0), 27.0, 10.0, "jpl_orange"),
    ]
    whip_count = max(0, min(4, antenna_count - 2))
    for index in range(whip_count):
        wx = -900.0
        wy = -520.0 + index * 90.0
        parts.append(cylinder_z(f"whip_antenna_rod_{index + 1}", (wx, wy, deck_z + 155.0), 7.0, 310.0, "brushed_steel"))
        parts.append(ball(f"whip_antenna_tip_{index + 1}", (wx, wy, deck_z + 315.0), 10.0, "brushed_steel"))
    return group("antenna_whips", parts, "pale_aluminum")


def solar_wing(s: float, side: str) -> bd.Compound:
    # Modeled at the display deploy angle; `solar_<side>` turns it about the hinge
    # axis (X-parallel line at y=±half_wid, z=deck+6) by the deploy delta.
    alpha = math.radians(SOLAR_DEPLOY_DEG)
    o = (0.0, s * math.sin(alpha), -math.cos(alpha))          # outward span direction
    n = v_norm(v_cross((s, 0.0, 0.0), o))                     # panel normal (sun side)
    if n[2] < 0.0:
        n = v_mul(n, -1.0)
    hinge = (-150.0, s * half_wid, SOLAR_HINGE_Z)
    panel_c = v_add(hinge, v_mul(o, SOLAR_SPAN / 2.0))
    parts: list[bd.Shape] = [
        oriented_box(f"solar_{side}_tip_accent_strip", v_add(hinge, v_add(v_mul(o, SOLAR_SPAN - 6.0), v_mul(n, 11.0))),
                     SOLAR_CHORD, 20.0, 8.0, (1.0, 0.0, 0.0), o, n, "jpl_orange"),
        oriented_box(f"solar_{side}_panel", panel_c, SOLAR_CHORD, SOLAR_SPAN, 18.0,
                     (1.0, 0.0, 0.0), o, n, "ivory_panel", fillet_radius=4.0),
        oriented_box(f"solar_{side}_spar_root", v_add(hinge, v_add(v_mul(o, 10.0), v_mul(n, 4.0))),
                     SOLAR_CHORD, 24.0, 22.0, (1.0, 0.0, 0.0), o, n, "pale_aluminum"),
        oriented_box(f"solar_{side}_spar_tip", v_add(hinge, v_add(v_mul(o, SOLAR_SPAN - 14.0), v_mul(n, 4.0))),
                     SOLAR_CHORD, 24.0, 22.0, (1.0, 0.0, 0.0), o, n, "pale_aluminum"),
    ]
    for index, gx in enumerate([-525.0, -275.0, -25.0, 225.0], start=1):
        for jndex, span_off in enumerate([155.0, 465.0], start=1):
            cell_c = v_add((gx, hinge[1], hinge[2]), v_add(v_mul(o, span_off), v_mul(n, 13.0)))
            parts.append(oriented_box(
                f"solar_{side}_cell_{index}{jndex}", cell_c, 225.0, 282.0, 6.0,
                (1.0, 0.0, 0.0), o, n, "solar_cell"))
    for index, kx in enumerate([-550.0, -150.0, 250.0], start=1):
        parts.append(cylinder_x(f"solar_{side}_hinge_knuckle_{index}", (kx, s * half_wid, SOLAR_HINGE_Z),
                                26.0, 60.0, "pale_aluminum"))
    return group(f"solar_wing_{side}", parts, "ivory_panel")


def power_rtg() -> bd.Compound:
    m = RTG_MOUNT
    d = RTG_DIR
    u = (0.0, 1.0, 0.0)
    v = v_norm(v_cross(d, u))
    parts: list[bd.Shape] = [
        cylinder_between("rtg_accent_collar", v_add(m, v_mul(d, 10.0)), v_add(m, v_mul(d, 40.0)), 185.0, "jpl_orange"),
        cylinder_between("rtg_core_housing", v_add(m, v_mul(d, 20.0)), v_add(m, v_mul(d, 560.0)), 165.0, "rtg_core"),
        cylinder_between("rtg_end_cap", v_add(m, v_mul(d, 560.0)), v_add(m, v_mul(d, 590.0)), 120.0, "rtg_core"),
    ]
    for index in range(8):
        theta = 2.0 * math.pi * index / 8.0
        rk = v_add(v_mul(u, math.cos(theta)), v_mul(v, math.sin(theta)))
        tangent = v_norm(v_cross(d, rk))
        fin_c = v_add(v_add(m, v_mul(d, 300.0)), v_mul(rk, 165.0 + 65.0))
        parts.append(oriented_box(
            f"rtg_radiator_fin_{index + 1}", fin_c, 460.0, 10.0, 130.0,
            d, tangent, rk, "rtg_fin"))
    parts.append(cylinder_between("rtg_mount_strut_left", (-half_len, 140.0, 1000.0),
                                  v_add(m, (30.0, 120.0, -10.0)), 18.0, "satin_titanium"))
    parts.append(cylinder_between("rtg_mount_strut_right", (-half_len, -140.0, 1000.0),
                                  v_add(m, (30.0, -120.0, -10.0)), 18.0, "satin_titanium"))
    return group("power_rtg", parts, "rtg_core")




# ---------------------------------------------------------------------------
# Kinematics: build123d joints on the top-level groups.
#
# ZERO IS THE MODEL AS BUILT. The rover is modeled in its display pose --
# suspension neutral, arm in a sampling hover, mast level, wings deployed at
# SOLAR_DEPLOY_DEG, HGA at 35 deg -- so every joint is connected at 0 there and
# the limits are offsets FROM that pose, not absolute machine angles.
#
# Every axis is built from the derived layout constants above rather than
# retyped, so the pivots cannot drift from the geometry. A joint on a group
# carries its whole subtree, which is what makes the rocker-bogie chain three
# joints instead of three hundred.
#
# What did NOT become kinematics, deliberately: the accent palette, the shell
# X-ray / emissive styling, the dust and RTG visibility toggles, and the
# chassis pitch/roll. The four old clips are motions (`_clip_joints` and the
# clips below): the chassis heaves on a prismatic joint of the terrain, and
# every group slides off on a prismatic joint of its own for the explode.
# ---------------------------------------------------------------------------

_Y_AXIS = (0.0, 1.0, 0.0)
_Z_AXIS = (0.0, 0.0, 1.0)
_X_AXIS = (1.0, 0.0, 0.0)


def _mirror_y(point: Vector3) -> Vector3:
    return (point[0], -point[1], point[2])


# Left is +Y; every right-hand pivot is its left twin mirrored in Y.
_SIDE_SIGN = {"left": 1.0, "right": -1.0}
# (mate name, wheel group label, axle x, side, steering mate or None)
_WHEEL_STATIONS = (
    ("wheel_front_left", "wheel_front_left", x_front, "left", "steer_front_left"),
    ("wheel_front_right", "wheel_front_right", x_front, "right", "steer_front_right"),
    ("wheel_middle_left", "wheel_middle_left", x_mid, "left", None),
    ("wheel_middle_right", "wheel_middle_right", x_mid, "right", None),
    ("wheel_rear_left", "wheel_rear_left", x_rear, "left", "steer_rear_left"),
    ("wheel_rear_right", "wheel_rear_right", x_rear, "right", "steer_rear_right"),
)
# (mate name, fork group label, axle x, side, rides the bogie not the rocker)
_STEER_STATIONS = (
    ("steer_front_left", "steering_front_left", x_front, "left", False),
    ("steer_front_right", "steering_front_right", x_front, "right", False),
    ("steer_rear_left", "steering_rear_left", x_rear, "left", True),
    ("steer_rear_right", "steering_rear_right", x_rear, "right", True),
)

# The panel that swings clear for the cutaway hinges on its lower outboard
# edge, where the side plate meets the belly pan.
_PANEL_HINGE = (0.0, half_wid, belly_z + 10.0)
# The differential bar's pivot on the deck, and the Ackermann-ish steer gearing
# with the front-left fork as the unit.
_DIFFERENTIAL_PIVOT = (430.0, 0.0, 1235.0)
_STEER_GEARS = {"steer_front_left": 1.0, "steer_front_right": 0.79,
                "steer_rear_left": -1.0, "steer_rear_right": -0.79}
# Wheel revolutions in one `driveAround` lap.
_DRIVE_TURNS = 4


def _mate(fixed: bd.Shape, moving: bd.Shape, label: str, origin: Vector3, direction: Vector3,
          limits: tuple[float, float], *, linear: bool = False) -> None:
    """``moving`` turns (or, ``linear``, slides) about the axis on ``fixed``: build123d's
    revolute or linear joint, the moving side's rigid joint on the joint's own frame,
    connected at 0 where the parts stand."""
    axis = bd.Axis(origin, direction)
    if linear:
        bd.LinearJoint(label, fixed, axis=axis, linear_range=limits)
    else:
        bd.RevoluteJoint(label, fixed, axis=axis, angular_range=limits)
    bd.RigidJoint(label, moving, fixed.location * fixed.joints[label].relative_axis.location)
    if linear:
        fixed.joints[label].connect_to(moving.joints[label], position=0.0)
    else:
        fixed.joints[label].connect_to(moving.joints[label], angle=0.0)


def _connect(groups: dict[str, bd.Shape]) -> None:
    """The rover's 27 joints, on its top-level groups by label."""
    chassis = groups["chassis_frame"]

    # -- rocker-bogie suspension -------------------------------------------
    # The rocker hangs off the chassis, the bogie off the rocker, and the
    # differential bar splits the two rockers (the ratio lives in the
    # `rocker_split` coupling).
    for side, sign in _SIDE_SIGN.items():
        rocker_pivot = ROCKER_PIVOT if sign > 0 else _mirror_y(ROCKER_PIVOT)
        bogie_pivot = BOGIE_PIVOT if sign > 0 else _mirror_y(BOGIE_PIVOT)
        _mate(chassis, groups[f"rocker_{side}"], f"rocker_{side}", rocker_pivot, _Y_AXIS, (-12, 12))
        _mate(groups[f"rocker_{side}"], groups[f"bogie_{side}"], f"bogie_{side}", bogie_pivot, _Y_AXIS, (-15, 15))
    _mate(chassis, groups["differential"], "differential", _DIFFERENTIAL_PIVOT, _Z_AXIS, (-6, 6))

    # -- steering and drive --------------------------------------------------
    # Each corner fork steers about the vertical through its own wheel center,
    # riding whichever suspension member carries it; the wheel then spins about
    # the transverse axle through the same point. Middle wheels do not steer,
    # so they hang straight off their bogie.
    for mate_name, group_label, x0, side, on_bogie in _STEER_STATIONS:
        center = (x0, _SIDE_SIGN[side] * y_wheel, axle_z)
        carrier = groups[f"bogie_{side}" if on_bogie else f"rocker_{side}"]
        _mate(carrier, groups[group_label], mate_name, center, _Z_AXIS, (-60, 60))
    # Four turns each way: `driveAround` rolls the wheels four revolutions
    # unwrapped (the old clip wrapped its angle at 360, a jump a joint's
    # curve cannot take).
    for mate_name, group_label, x0, side, steer in _WHEEL_STATIONS:
        center = (x0, _SIDE_SIGN[side] * y_wheel, axle_z)
        carrier = groups[f"steering_{steer.removeprefix('steer_')}"] if steer else groups[f"bogie_{side}"]
        _mate(carrier, groups[group_label], mate_name, center, _Y_AXIS, (-_DRIVE_TURNS * 360, _DRIVE_TURNS * 360))

    # -- remote sensing mast -------------------------------------------------
    # Azimuth turns the column (the head rides it); elevation pitches the head.
    mast_x, mast_y = MAST_XY
    _mate(chassis, groups["mast_base"], "mast_yaw", (mast_x, mast_y, deck_z), _Z_AXIS, (-170, 170))
    _mate(groups["mast_base"], groups["mast_head"], "mast_pitch", (mast_x, mast_y, HEAD_PIVOT_Z), _Y_AXIS,
          (-60, 25))

    # -- robotic arm: azimuth -> shoulder -> elbow -> wrist -> turret --------
    _mate(chassis, groups["arm_azimuth"], "arm_azim", (ARM_AZIMUTH_XY[0], ARM_AZIMUTH_XY[1], 715.0), _Z_AXIS,
          (-45, 45))
    _mate(groups["arm_azimuth"], groups["arm_shoulder"], "arm_shoulder", ARM_SHOULDER, _Y_AXIS, (-60, 35))
    _mate(groups["arm_shoulder"], groups["arm_elbow"], "arm_elbow", ARM_ELBOW, _Y_AXIS, (-75, 45))
    _mate(groups["arm_elbow"], groups["arm_wrist"], "arm_wrist", ARM_WRIST, _Y_AXIS, (-70, 60))
    _mate(groups["arm_wrist"], groups["arm_turret"], "arm_turret", ARM_TURRET, _wrist_dir, (-180, 180))

    # -- antennas and solar wings -------------------------------------------
    _mate(groups["antenna_hga_mast"], groups["antenna_hga_dish"], "hga_elev", HGA_ELEV_PIVOT, _Y_AXIS, (-15, 55))
    for side, sign in _SIDE_SIGN.items():
        hinge = (-150.0, sign * half_wid, SOLAR_HINGE_Z)
        # Modeled at SOLAR_DEPLOY_DEG, so 0 is deployed: stowing is -82 deg on
        # the left wing and +82 on the right (mirrored hinges, one X axis).
        limits = (-82, 13) if sign > 0 else (-13, 82)
        _mate(chassis, groups[f"solar_wing_{side}"], f"solar_{side}", hinge, _X_AXIS, limits)

    # -- cutaway hardware: the lid lifts, the left side panel swings clear ----
    _mate(chassis, groups["deck_lid"], "lid_lift", (575.0, 255.0, deck_z), _Z_AXIS, (0, 420), linear=True)
    _mate(chassis, groups["side_panel_left"], "panel_swing", _PANEL_HINGE, _X_AXIS, (-75, 0))


# ---------------------------------------------------------------------------
# The heave: the chassis on the terrain.
#
# `driveAround` heaves the whole body over the terrain, which stays put: the
# chassis rides a prismatic joint of the terrain (`heave`), the rover on the
# ground, so the terrain is the ground, and everything the chassis carries heaves
# with it -- the jointed groups through their joints, the static ones (body,
# internals, payloads, harness, dust, antennas, RTG) fastened to it.
#
# `explodedAssembly` is a GLB animation: every group but the chassis and the
# terrain moves along its own world vector, the jointed ones too, by its own
# vector, not its holder's plus its own (the rover's groups are siblings in its
# tree, so each translation is its group's alone).
# ---------------------------------------------------------------------------

_HEAVE_RANGE = (-40.0, 40.0)
# Each group's direction and length per mm of the explode's 520 mm peak, the old
# clip's vectors.
_EXPLODE_VECTORS = {
    "body_core": (0, 0, 0.35), "body_shell": (0, 0, 0.5),
    "deck_lid": (0, 0, 1.15), "side_panel_left": (0, 0.9, 0.15),
    "access_panels": (0, -0.8, 0.1), "thermal_control": (0, -0.35, 0.75),
    "internals_avionics": (0, 0, 0.85), "internals_power": (0.15, -0.2, 0.75),
    "science_payloads": (-0.2, 0.15, 0.95), "cable_harness": (0, 0, 0.3),
    "dust_covers": (0, 0, -0.4), "dust_layer": (0, 0, 1.35),
    "rocker_left": (0, 0.45, 0), "rocker_right": (0, -0.45, 0),
    "bogie_left": (0, 0.6, 0), "bogie_right": (0, -0.6, 0),
    "differential": (0, 0, 0.9),
    "steering_front_left": (0.15, 0.75, 0.1), "steering_front_right": (0.15, -0.75, 0.1),
    "steering_rear_left": (-0.15, 0.75, 0.1), "steering_rear_right": (-0.15, -0.75, 0.1),
    "wheel_front_left": (0.15, 1, 0), "wheel_front_right": (0.15, -1, 0),
    "wheel_middle_left": (0, 1, 0), "wheel_middle_right": (0, -1, 0),
    "wheel_rear_left": (-0.15, 1, 0), "wheel_rear_right": (-0.15, -1, 0),
    "mast_base": (0, 0, 0.7), "mast_head": (0, 0, 1.25),
    "arm_azimuth": (0.5, 0, 0.35), "arm_shoulder": (0.8, 0, 0.5),
    "arm_elbow": (1.05, 0, 0.6), "arm_wrist": (1.25, 0, 0.68),
    "arm_turret": (1.45, 0, 0.78),
    "antenna_hga_mast": (-0.3, 0.5, 0.5), "antenna_hga_dish": (-0.45, 0.75, 0.85),
    "antenna_uhf": (-0.35, -0.6, 0.6), "antenna_whips": (-0.5, -0.8, 0.45),
    "solar_wing_left": (0, 0.85, 0.3), "solar_wing_right": (0, -0.85, 0.3),
    "power_rtg": (-0.95, 0, 0.15),
}
_EXPLODE_PEAK = 520.0
# The groups no joint moves: each fastened to the chassis.
_STATIC_GROUPS = (
    "body_core", "body_shell", "access_panels", "thermal_control", "internals_avionics", "internals_power",
    "science_payloads", "cable_harness", "dust_covers", "dust_layer", "antenna_uhf", "antenna_whips", "power_rtg",
)


def _fasten(label: str, holder: bd.Shape, rider: bd.Shape) -> None:
    """``rider`` fastened to ``holder`` where both stand: a rigid pair of one label."""
    for part in (holder, rider):
        if not hasattr(part, "joints"):  # `transformed` makes a plain bd.Shape: no joints of its own
            part.joints = {}
        bd.RigidJoint(label, part, bd.Location())


def _ride_joints(groups: dict[str, bd.Shape]) -> None:
    """``heave`` (the chassis on the terrain), and the groups no joint moves fastened to the
    chassis, the HGA mast (which holds the dish's joint) with them, so they heave with it."""
    terrain, chassis = groups["terrain"], groups["chassis_frame"]
    bd.LinearJoint("heave", terrain, axis=bd.Axis((0.0, 0.0, 0.0), _Z_AXIS), linear_range=_HEAVE_RANGE)
    bd.RigidJoint("heave", chassis, bd.Location())
    for label in (*_STATIC_GROUPS, "antenna_hga_mast"):
        _fasten(f"{label}_rides", chassis, groups[label])


# ---------------------------------------------------------------------------
# The clips: motions of time over the joints
# ---------------------------------------------------------------------------

def _sine(u: float) -> float:
    return 0.5 - 0.5 * math.cos(math.tau * u)


def _smooth(u: float) -> float:
    c = min(1.0, max(0.0, u))
    return c * c * (3 - 2 * c)


def _bump(u: float, start: float, end: float) -> float:
    """0 -> 1 -> 0 across ``start``..``end`` of the master ramp."""
    return 0.0 if u <= start or u >= end else _sine((u - start) / (end - start))


def _drive_around(t: float) -> dict:
    """A lap: the body heaves over the terrain, the rockers split, the bogies pitch, the
    corners steer (`_steer`, the old Ackermann gearing), every wheel rolls four turns,
    and the mast looks into the turn."""
    u = t / 18
    steer = 34 * math.sin(u * math.tau * 2)
    bogie = 8 * math.sin(u * math.tau * 5 + 1.1)
    values = {
        "heave": 18 * math.sin(u * math.tau * 10),
        "rocker_split": 6 * math.sin(u * math.tau * 5),
        "bogie_left": bogie,
        "bogie_right": bogie,
        **_steer(steer),
        "mast_yaw": -1.6 * steer,
        "mast_pitch": 8 * math.sin(u * math.tau),
    }
    for name, *_rest in _WHEEL_STATIONS:
        values[name] = u * _DRIVE_TURNS * 360
    return values


def _arm(azim: float, shoulder: float, elbow: float, wrist: float, turret: float) -> dict:
    return {"arm_azim": azim, "arm_shoulder": shoulder, "arm_elbow": elbow, "arm_wrist": wrist,
            "arm_turret": turret}


def _arm_cycle(t: float) -> dict:
    """Reach out, dwell over the target while the turret indexes tools, come back; the
    mast watches. Angles are deltas from the modelled sampling hover."""
    u = t / 12
    reach = _bump(u, 0, 0.86)
    turret = 90 * _smooth((u - 0.3) / 0.25) - 90 * _smooth((u - 0.62) / 0.2)
    return {**_arm(-18 * reach, -30 * reach, 40 * reach, -25 * reach, turret),
            "mast_yaw": -14 * reach, "mast_pitch": 22 * reach}


def _deploy_sequence(t: float) -> dict:
    """Staged the way the real thing would come alive: wings out, HGA up, mast raised and
    panned, arm checked out, deck opened."""
    u = t / 20
    wings = _smooth(u / 0.22)
    hga = _smooth((u - 0.2) / 0.18)
    mast = _smooth((u - 0.36) / 0.18)
    arm = _bump(u, 0.5, 0.78)
    cutaway = _bump(u, 0.74, 1)
    return {
        # folded (-82 deg on the left hinge) out to the modelled deploy angle, this model's zero
        **_solar(-82 * (1 - wings)),
        "hga_elev": -15 + 50 * hga,
        "mast_yaw": 150 * mast * math.sin(u * math.tau),
        "mast_pitch": -60 * (1 - mast),
        **_arm(-12 * arm, -22 * arm, 30 * arm, -18 * arm, 180 * arm),
        # the deck lid lifts clear and the port panel swings out
        **_cutaway(cutaway),
    }


def _exploded_assembly(rover: bd.Compound) -> None:
    """`explodedAssembly`, a GLB animation: one ramp out and back over 12 s, each group along
    its own vector, at the 520 mm peak."""
    show = animation(rover, "explodedAssembly", duration=12)
    for label, vector in _EXPLODE_VECTORS.items():
        out = tuple(v * _EXPLODE_PEAK for v in vector)
        show.translation(label, by=out, start=0, end=6)
        show.translation(label, by=tuple(-v for v in out), start=6, end=12)


# One control each, driving several joints by ratio: name -> (range, ratios).
# The one real linkage: the differential bar makes the rockers counter-rotate,
# taking half the split itself. A constraint: the rockers and the bar move only
# through it, its range the rockers' limits (+-12 deg).
_COUPLINGS = {
    "rocker_split": {"rocker_left": 1.0, "rocker_right": -1.0, "differential": 0.5},
}


def _steer(heading: float) -> dict:
    """The four corners' Ackermann-ish steer at ``heading`` on the front-left fork (the old
    `steer` coupling's gearing, now set joint by joint)."""
    return {name: ratio * heading for name, ratio in _STEER_GEARS.items()}


def _solar(deploy: float) -> dict:
    """Both wings at ``deploy`` on the left hinge (mirrored hinges: the right takes -deploy)."""
    return {"solar_left": deploy, "solar_right": -deploy}


def _cutaway(open_: float) -> dict:
    """The deck lid lifted and the left side panel swung out, ``open_`` of the way (0..1)."""
    return {"lid_lift": 420.0 * open_, "panel_swing": -75.0 * open_}


_POSES = {
    # Cruise stage / launch configuration: wings folded in, arm tucked,
    # mast down, HGA parked.
    "stowed": {**_solar(-82), "arm_shoulder": 35, "arm_elbow": -75,
               "arm_wrist": 60, "mast_pitch": -60, "hga_elev": -15},
    # On-surface science attitude: HGA on Earth, mast scanning off to port.
    "deployed": {"hga_elev": 35, "mast_yaw": -60, "mast_pitch": 12},
    # Arm out over a target ahead of the front-left wheel, turret presenting
    # the drill.
    "arm_reach": {"arm_azim": -18, "arm_shoulder": -30, "arm_elbow": 40,
                  "arm_wrist": -25, "arm_turret": 90},
    # Deck open for the internals.
    "cutaway_open": _cutaway(1),
}


@model
def mars_rover_concept():
    # Top-level children, in order (the joints address them by label):
    #  1 terrain            2 chassis_frame     3 body_core        4 body_shell
    #  5 deck_lid           6 side_panel_left   7 access_panels    8 thermal_control
    #  9 internals_avionics 10 internals_power  11 science_payloads 12 cable_harness
    # 13 dust_covers        14 dust_layer       15 rocker_left     16 rocker_right
    # 17 bogie_left         18 bogie_right      19 differential    20 steering_front_left
    # 21 steering_front_right 22 steering_rear_left 23 steering_rear_right
    # 24 wheel_front_left   25 wheel_front_right 26 wheel_middle_left
    # 27 wheel_middle_right 28 wheel_rear_left  29 wheel_rear_right
    # 30 mast_base          31 mast_head        32 arm_azimuth     33 arm_shoulder
    # 34 arm_elbow          35 arm_wrist        36 arm_turret      37 antenna_hga_mast
    # 38 antenna_hga_dish   39 antenna_uhf      40 antenna_whips   41 solar_wing_left
    # 42 solar_wing_right   43 power_rtg
    children: list[bd.Shape] = [
        terrain(),
        chassis_frame(),
        body_core(),
        body_shell(),
        deck_lid(),
        side_panel_left(),
        access_panels(),
        thermal_control(),
        internals_avionics(),
        internals_power(),
        science_payloads(),
        cable_harness(),
        dust_covers(),
        dust_layer(),
        rocker(1.0, "left"),
        rocker(-1.0, "right"),
        bogie(1.0, "left"),
        bogie(-1.0, "right"),
        differential(),
        steering_fork(x_front, 1.0, "steering_front_left"),
        steering_fork(x_front, -1.0, "steering_front_right"),
        steering_fork(x_rear, 1.0, "steering_rear_left"),
        steering_fork(x_rear, -1.0, "steering_rear_right"),
        wheel(x_front, 1.0, "wheel_front_left"),
        wheel(x_front, -1.0, "wheel_front_right"),
        wheel(x_mid, 1.0, "wheel_middle_left"),
        wheel(x_mid, -1.0, "wheel_middle_right"),
        wheel(x_rear, 1.0, "wheel_rear_left"),
        wheel(x_rear, -1.0, "wheel_rear_right"),
        mast_base(),
        mast_head(),
        arm_azimuth(),
        arm_shoulder(),
        arm_elbow(),
        arm_wrist(),
        arm_turret(),
        antenna_hga_mast(),
        antenna_hga_dish(),
        antenna_uhf(),
        antenna_whips(),
        solar_wing(1.0, "left"),
        solar_wing(-1.0, "right"),
        power_rtg(),
    ]
    by_label = {child.label: child for child in children}
    _connect(by_label)
    _ride_joints(by_label)
    rover = group("mars_rover_concept", children)
    for name, ratios in _COUPLINGS.items():
        gear_pair(rover, name, **ratios)
    for name, values in _POSES.items():
        mechanism_state(rover, name, **values)
    configuration_sequence(rover, "driveAround", _drive_around, duration=18)
    configuration_sequence(rover, "armCycle", _arm_cycle, duration=12)
    configuration_sequence(rover, "deploySequence", _deploy_sequence, duration=20)
    _exploded_assembly(rover)
    return rover


if __name__ == "__main__":
    mars_rover_concept()
