"""GD01-inspired manned transformable mecha concept.

A generative CAD homage to the publicly visible design language of the
Unitree GD01 pilotable mecha: a ~2.7 m tall open-cockpit biped walker with a
silver tubular roll cage around the pilot, glossy red armor shells over a
black structural understructure, large articulated legs, arm modules that
double as front limbs in quadruped mode, compact foot pads, exposed joint
actuator pods, cooling vents, service seams, and visible cable routing.

Units: millimeters. Origin: ground center between the feet. +X forward
(facing direction), +Y left, +Z up. The model is exported in a neutral
upright stance (legs straight, arms hanging); all posing, the
biped-to-quadruped transformation, walking, cockpit access, actuator demos,
and the exploded reveal are driven at viewer time by the declared JS
parameter sidecar (gd01_mecha_concept.params.js), which reads joint pivots
from the actuator feature centers of this exact structure.

Every top-level child of the root compound is one rigid animation group; the
sidecar targets groups by child order (#o1.N), so keep FEATURE_ORDER in sync
with the list built in gen_step().
"""

from __future__ import annotations

import colorsys
from math import atan2, cos, degrees, radians, sin

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Circle,
    Color,
    Compound,
    Cone,
    Cylinder,
    Edge,
    Location,
    Locations,
    Mode,
    Plane,
    RectangleRounded,
    Sphere,
    extrude,
    fillet,
    mirror,
    sweep,
)

# ---------------------------------------------------------------------------
# Named parameters (mm unless noted). Defaults reproduce the GD01-like
# 2.7 m silhouette. Pose parameters (hip/knee/ankle/shoulder/elbow angles,
# biped_quadruped_blend, exploded_distance, style controls) live in the JS
# sidecar because they are viewer-time articulation, not geometry.
# ---------------------------------------------------------------------------
overall_height = 2700.0          # nominal standing height at default ratios
torso_cockpit_width = 920.0      # outer width of the cockpit cage section
roll_cage_tube_diameter = 48.0   # silver protective cage tube OD
cockpit_seat_scale = 1.0         # scales the pilot seat placeholder (0.8-1.2)
pilot_placeholder_visibility = True  # build the seated pilot dummy geometry
limb_length_ratio = 1.0          # scales thigh/shin/arm segment lengths
upper_arm_armor_scale = 1.0      # red upper-arm shell cross-section scale
thigh_armor_scale = 1.0          # red thigh shell cross-section scale
shin_armor_scale = 1.0           # red shin shell cross-section scale
joint_actuator_diameter = 190.0  # hip actuator pod OD; other joints derive
stance_width = 720.0             # hip pivot lateral spacing, center-to-center
foot_pad_size = 1.0              # scales the compact foot pad footprint
sensor_detail_level = 2          # 0 = none, 1 = core sensors, 2 = full suite
red_panel_hue = 356.0            # armor hue in degrees (356 = GD01 red)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


# Derived layout ------------------------------------------------------------
S = _clamp(overall_height, 1800.0, 3600.0) / 2700.0
LIMB = _clamp(limb_length_ratio, 0.8, 1.25)
W = _clamp(torso_cockpit_width, 700.0, 1200.0) * S
HALF_W = W / 2.0
CAGE_R = _clamp(roll_cage_tube_diameter, 30.0, 80.0) * S / 2.0
ACT_R = _clamp(joint_actuator_diameter, 120.0, 260.0) * S / 2.0
HIP_Y = _clamp(stance_width, 520.0, 980.0) * S / 2.0
PAD_SCALE = _clamp(foot_pad_size, 0.7, 1.4)
SENSORS = int(_clamp(sensor_detail_level, 0, 2))
SEAT_SCALE = _clamp(cockpit_seat_scale, 0.75, 1.3)

PAD_LEN = 430.0 * S * PAD_SCALE
PAD_WID = 270.0 * S * PAD_SCALE
PAD_TH = 62.0 * S
ANKLE_Z = 190.0 * S
SHIN_LEN = 640.0 * S * LIMB
KNEE_Z = ANKLE_Z + SHIN_LEN
THIGH_LEN = 680.0 * S * LIMB
HIP_Z = KNEE_Z + THIGH_LEN

CAGE_TOP = HIP_Z + 1050.0 * S
SHOULDER_X = -200.0 * S
SHOULDER_Z = HIP_Z + 780.0 * S
SHOULDER_Y = HALF_W + 130.0 * S
ARM_Y = SHOULDER_Y + 30.0 * S
UPPER_LEN = 520.0 * S * LIMB
ELBOW_Z = SHOULDER_Z - UPPER_LEN
FORE_LEN = 560.0 * S * LIMB
WRIST_Z = ELBOW_Z - FORE_LEN

SEAT_X = -40.0 * S
SEAT_Z = HIP_Z + 320.0 * S
GATE_HINGE = (180.0 * S, HIP_Z + 760.0 * S)  # (x, z), axis along Y

# Colors ---------------------------------------------------------------------
_hue = (_clamp(red_panel_hue, 0.0, 360.0) % 360.0) / 360.0
_arm_rgb = colorsys.hsv_to_rgb(_hue, 0.93, 0.66)
GLOSS_RED = Color(*_arm_rgb, 1.0)
DEEP_RED = Color(*(c * 0.62 for c in _arm_rgb), 1.0)
MATTE_BLACK = Color(0.030, 0.032, 0.036, 1.0)
GRAPHITE = Color(0.085, 0.09, 0.10, 1.0)
DARK_STEEL = Color(0.16, 0.17, 0.185, 1.0)
SILVER = Color(0.76, 0.78, 0.80, 1.0)
BRIGHT_SILVER = Color(0.86, 0.87, 0.89, 1.0)
RUBBER = Color(0.05, 0.05, 0.055, 1.0)
PILOT_GRAY = Color(0.30, 0.31, 0.33, 1.0)
SEAT_BLACK = Color(0.07, 0.07, 0.08, 1.0)
LENS_BLUE = Color(0.25, 0.48, 0.85, 0.55)
LENS_AMBER = Color(0.95, 0.55, 0.12, 0.55)
VISOR_TINT = Color(0.62, 0.78, 0.92, 0.30)

# Root child order; the sidecar feature map indexes #o1.N by this list.
FEATURE_ORDER = (
    "pelvis_core",
    "pelvis_armor",
    "torso_frame",
    "torso_armor",
    "cockpit_module",
    "pilot_placeholder",
    "cockpit_gate",
    "cockpit_gate_hinge",
    "sensor_head",
    "left_hip_actuator",
    "right_hip_actuator",
    "left_thigh_core",
    "left_thigh_armor",
    "right_thigh_core",
    "right_thigh_armor",
    "left_knee_actuator",
    "right_knee_actuator",
    "left_shin_core",
    "left_shin_armor",
    "right_shin_core",
    "right_shin_armor",
    "left_ankle_joint",
    "right_ankle_joint",
    "left_foot_pad",
    "right_foot_pad",
    "left_shoulder_actuator",
    "right_shoulder_actuator",
    "left_upper_arm_core",
    "left_upper_arm_armor",
    "right_upper_arm_core",
    "right_upper_arm_armor",
    "left_elbow_actuator",
    "right_elbow_actuator",
    "left_forearm_core",
    "left_forearm_armor",
    "right_forearm_core",
    "right_forearm_armor",
    "left_hand_pad",
    "right_hand_pad",
)


def _style(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _safe_fillet(edges, radius: float) -> None:
    selected = list(edges)
    if not selected or radius <= 0.0:
        return
    try:
        fillet(selected, radius=radius)
    except Exception:
        pass


def _rounded_box(
    label: str,
    color: Color,
    size: tuple[float, float, float],
    center: tuple[float, float, float],
    radius: float = 0.0,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
):
    with BuildPart() as builder:
        Box(*size, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        if radius > 0.0:
            _safe_fillet(builder.edges(), radius)
    return _style(builder.part.moved(Location(center, rotation)), label, color)


_AXIS_ROT = {"x": (0.0, 90.0, 0.0), "y": (90.0, 0.0, 0.0), "z": (0.0, 0.0, 0.0)}


def _axis_cylinder(
    label: str,
    color: Color,
    axis: str,
    center: tuple[float, float, float],
    radius: float,
    length: float,
    fillet_radius: float = 0.0,
):
    with BuildPart() as builder:
        Cylinder(radius=radius, height=length, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        if fillet_radius > 0.0:
            _safe_fillet(builder.edges(), fillet_radius)
    return _style(builder.part.moved(Location(center, _AXIS_ROT[axis])), label, color)


def _tube(label: str, color: Color, points: list[tuple[float, float, float]], radius: float):
    path = Edge.make_spline(points)
    tangent = (
        points[1][0] - points[0][0],
        points[1][1] - points[0][1],
        points[1][2] - points[0][2],
    )
    profile_plane = Plane(origin=points[0], x_dir=(0.0, 0.0, 1.0), z_dir=tangent)
    with BuildPart() as builder:
        with BuildSketch(profile_plane):
            Circle(radius)
        sweep(path=path, is_frenet=True)
    return _style(builder.part, label, color)


def _group(label: str, parts: list) -> Compound:
    return Compound(obj=list(parts), children=list(parts), label=label)


def _mirror_part(part):
    label = str(part.label or "")
    color = part.color
    flipped = mirror(part, about=Plane.XZ)
    swapped = (
        label.replace("left_", "@@").replace("right_", "left_").replace("@@", "right_")
        if ("left_" in label or "right_" in label)
        else label
    )
    return _style(flipped, swapped, color)


def _mirror_group(group_label: str, parts: list) -> Compound:
    return _group(group_label, [_mirror_part(part) for part in parts])


# ---------------------------------------------------------------------------
# Pelvis
# ---------------------------------------------------------------------------
def _pelvis_core_parts() -> list:
    parts = [
        _rounded_box(
            "pelvis_hip_crossmember_black_structural_beam",
            GRAPHITE,
            (320.0 * S, HIP_Y * 2.0 - 60.0 * S, 240.0 * S),
            (0.0, 0.0, HIP_Z + 80.0 * S),
            18.0 * S,
        ),
        _rounded_box(
            "pelvis_spine_riser_black_column_to_torso",
            MATTE_BLACK,
            (220.0 * S, 280.0 * S, 340.0 * S),
            (-110.0 * S, 0.0, HIP_Z + 260.0 * S),
            14.0 * S,
        ),
        _rounded_box(
            "pelvis_rear_battery_pack_graphite_module",
            GRAPHITE,
            (220.0 * S, 420.0 * S, 200.0 * S),
            (-250.0 * S, 0.0, HIP_Z + 150.0 * S),
            12.0 * S,
        ),
        _rounded_box(
            "pelvis_battery_silver_service_band",
            SILVER,
            (226.0 * S, 428.0 * S, 26.0 * S),
            (-250.0 * S, 0.0, HIP_Z + 150.0 * S),
            4.0 * S,
        ),
    ]
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _rounded_box(
                f"pelvis_{side_name}_hip_yoke_plate_dark_steel",
                DARK_STEEL,
                (280.0 * S, 34.0 * S, 280.0 * S),
                (0.0, side * (HIP_Y - 140.0 * S), HIP_Z),
                10.0 * S,
            )
        )
        parts.append(
            _tube(
                f"pelvis_{side_name}_power_cable_loom_to_hip_actuator",
                MATTE_BLACK,
                [
                    (-330.0 * S, side * 140.0 * S, HIP_Z + 190.0 * S),
                    (-260.0 * S, side * (HIP_Y - 200.0 * S), HIP_Z + 120.0 * S),
                    (-120.0 * S, side * (HIP_Y - 90.0 * S), HIP_Z + 40.0 * S),
                    (-20.0 * S, side * (HIP_Y - 40.0 * S), HIP_Z + 10.0 * S),
                ],
                15.0 * S,
            )
        )
    return parts


def _pelvis_armor_parts() -> list:
    parts = []
    with BuildPart() as front:
        Box(58.0 * S, HIP_Y * 2.0 - 160.0 * S, 260.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        # horizontal service seam groove across the plate face
        with Locations(Location((26.0 * S, 0.0, 30.0 * S))):
            Box(10.0 * S, HIP_Y * 2.0 - 150.0 * S, 5.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        _safe_fillet(front.edges(), 14.0 * S)
    parts.append(
        _style(
            front.part.moved(Location((200.0 * S, 0.0, HIP_Z + 80.0 * S))),
            "pelvis_front_glossy_red_armor_plate_with_service_seam",
            GLOSS_RED,
        )
    )
    parts.append(
        _rounded_box(
            "pelvis_rear_glossy_red_fairing_plate",
            GLOSS_RED,
            (46.0 * S, HIP_Y * 2.0 - 260.0 * S, 220.0 * S),
            (-380.0 * S, 0.0, HIP_Z + 70.0 * S),
            12.0 * S,
        )
    )
    return parts


# ---------------------------------------------------------------------------
# Torso frame: silver roll cage + black structural beams
# ---------------------------------------------------------------------------
def _cage_hoop_points(side: float) -> list[tuple[float, float, float]]:
    y = side * (HALF_W - CAGE_R)
    return [
        (300.0 * S, y, HIP_Z + 110.0 * S),
        (385.0 * S, y, HIP_Z + 460.0 * S),
        (330.0 * S, y, HIP_Z + 760.0 * S),
        (170.0 * S, y, CAGE_TOP - 60.0 * S),
        (-60.0 * S, y, CAGE_TOP),
        (-280.0 * S, y, CAGE_TOP - 130.0 * S),
        (-360.0 * S, y, HIP_Z + 480.0 * S),
        (-290.0 * S, y, HIP_Z + 110.0 * S),
    ]


def _torso_frame_parts() -> list:
    parts = []
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _tube(
                f"torso_{side_name}_silver_roll_cage_side_hoop_tube",
                SILVER,
                _cage_hoop_points(side),
                CAGE_R,
            )
        )
        parts.append(
            _tube(
                f"torso_{side_name}_silver_roll_cage_diagonal_brace_tube",
                SILVER,
                [
                    (-290.0 * S, side * (HALF_W - CAGE_R), HIP_Z + 150.0 * S),
                    (-120.0 * S, side * (HALF_W - CAGE_R - 30.0 * S), HIP_Z + 560.0 * S),
                    (150.0 * S, side * (HALF_W - CAGE_R), CAGE_TOP - 90.0 * S),
                ],
                CAGE_R * 0.72,
            )
        )
        parts.append(
            _rounded_box(
                f"torso_{side_name}_black_cockpit_side_rail_beam",
                MATTE_BLACK,
                (620.0 * S, 64.0 * S, 90.0 * S),
                (30.0 * S, side * (HALF_W - 120.0 * S), HIP_Z + 220.0 * S),
                10.0 * S,
            )
        )
        parts.append(
            _rounded_box(
                f"torso_{side_name}_shoulder_pod_mount_plate",
                DARK_STEEL,
                (240.0 * S, 60.0 * S, 240.0 * S),
                (SHOULDER_X, side * (HALF_W + 15.0 * S), SHOULDER_Z),
                10.0 * S,
            )
        )
    cross_specs = (
        ("torso_front_top_silver_cross_tube", (170.0 * S, CAGE_TOP - 60.0 * S)),
        ("torso_mid_top_silver_cross_tube", (-60.0 * S, CAGE_TOP)),
        ("torso_rear_top_silver_cross_tube", (-280.0 * S, CAGE_TOP - 130.0 * S)),
        ("torso_front_low_silver_cross_tube", (300.0 * S, HIP_Z + 110.0 * S)),
    )
    for label, (x_pos, z_pos) in cross_specs:
        parts.append(
            _axis_cylinder(label, SILVER, "y", (x_pos, 0.0, z_pos), CAGE_R, W - 2.0 * CAGE_R)
        )
    parts.append(
        _rounded_box(
            "torso_shoulder_black_crossbeam_structure",
            GRAPHITE,
            (230.0 * S, SHOULDER_Y * 2.0 - 80.0 * S, 190.0 * S),
            (SHOULDER_X, 0.0, SHOULDER_Z),
            16.0 * S,
        )
    )
    parts.append(
        _tube(
            "torso_rear_black_cable_loom_battery_to_shoulder_beam",
            MATTE_BLACK,
            [
                (-330.0 * S, 90.0 * S, HIP_Z + 260.0 * S),
                (-370.0 * S, 60.0 * S, HIP_Z + 560.0 * S),
                (-330.0 * S, 20.0 * S, SHOULDER_Z - 60.0 * S),
                (SHOULDER_X - 60.0 * S, 0.0, SHOULDER_Z),
            ],
            17.0 * S,
        )
    )
    return parts


def _torso_armor_parts() -> list:
    parts = []
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        with BuildPart() as panel:
            Box(430.0 * S, 70.0 * S, 540.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            # cooling vent louvers cut into the upper half of the chest cheek
            for index in range(4):
                with Locations(Location((-120.0 * S + index * 62.0 * S, 0.0, 170.0 * S))):
                    Box(30.0 * S, 90.0 * S, 90.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
            # vertical service seam
            with Locations(Location((90.0 * S, side * 32.0 * S, -120.0 * S))):
                Box(9.0 * S, 8.0 * S, 300.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
            _safe_fillet(panel.edges(), 16.0 * S)
        parts.append(
            _style(
                panel.part.moved(Location((60.0 * S, side * (HALF_W + 36.0 * S), HIP_Z + 560.0 * S))),
                f"torso_{side_name}_glossy_red_chest_cheek_panel_with_vents",
                GLOSS_RED,
            )
        )
        parts.append(
            _rounded_box(
                f"torso_{side_name}_silver_trim_strip_on_chest_panel",
                BRIGHT_SILVER,
                (360.0 * S, 12.0 * S, 34.0 * S),
                (40.0 * S, side * (HALF_W + 74.0 * S), HIP_Z + 700.0 * S),
                4.0 * S,
            )
        )
    with BuildPart() as back:
        Box(140.0 * S, W - 180.0 * S, 720.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        for index in range(6):
            with Locations(Location((-40.0 * S, 0.0, -240.0 * S + index * 96.0 * S))):
                Box(90.0 * S, W - 320.0 * S, 30.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        _safe_fillet(back.edges(), 20.0 * S)
    parts.append(
        _style(
            back.part.moved(Location((-430.0 * S, 0.0, HIP_Z + 520.0 * S))),
            "torso_rear_glossy_red_back_shell_with_cooling_louvers",
            GLOSS_RED,
        )
    )
    parts.append(
        _rounded_box(
            "torso_top_glossy_red_cowl_behind_sensor_mast",
            GLOSS_RED,
            (300.0 * S, 380.0 * S, 80.0 * S),
            (-260.0 * S, 0.0, CAGE_TOP - 40.0 * S),
            18.0 * S,
        )
    )
    parts.append(
        _rounded_box(
            "torso_front_tinted_polycarbonate_visor_deflector",
            VISOR_TINT,
            (20.0 * S, 480.0 * S, 280.0 * S),
            (330.0 * S, 0.0, CAGE_TOP - 90.0 * S),
            8.0 * S,
            rotation=(0.0, -50.0, 0.0),
        )
    )
    return parts


# ---------------------------------------------------------------------------
# Cockpit module: floor, seat placeholder, harness, controls
# ---------------------------------------------------------------------------
def _cockpit_module_parts() -> list:
    q = SEAT_SCALE
    parts = [
        _rounded_box(
            "cockpit_black_floor_plate",
            MATTE_BLACK,
            (560.0 * S, W - 280.0 * S, 30.0 * S),
            (80.0 * S, 0.0, HIP_Z + 170.0 * S),
            8.0 * S,
        ),
        _rounded_box(
            "cockpit_pilot_seat_pan_placeholder",
            SEAT_BLACK,
            (360.0 * S * q, 400.0 * S * q, 60.0 * S * q),
            (SEAT_X, 0.0, SEAT_Z),
            16.0 * S,
        ),
        _rounded_box(
            "cockpit_pilot_seat_backrest_placeholder",
            SEAT_BLACK,
            (74.0 * S * q, 380.0 * S * q, 540.0 * S * q),
            (SEAT_X - 165.0 * S * q, 0.0, SEAT_Z + 270.0 * S * q),
            16.0 * S,
            rotation=(0.0, -10.0, 0.0),
        ),
        _rounded_box(
            "cockpit_pilot_seat_headrest_red_accent_pad",
            DEEP_RED,
            (70.0 * S * q, 220.0 * S * q, 150.0 * S * q),
            (SEAT_X - 240.0 * S * q, 0.0, SEAT_Z + 600.0 * S * q),
            18.0 * S,
            rotation=(0.0, -10.0, 0.0),
        ),
    ]
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _rounded_box(
                f"cockpit_{side_name}_harness_strap_over_backrest",
                RUBBER,
                (250.0 * S, 52.0 * S, 16.0 * S),
                (SEAT_X - 90.0 * S, side * 110.0 * S * q, SEAT_Z + 430.0 * S * q),
                5.0 * S,
                rotation=(0.0, -42.0, 0.0),
            )
        )
        parts.append(
            _rounded_box(
                f"cockpit_{side_name}_side_console_box",
                GRAPHITE,
                (240.0 * S, 90.0 * S, 110.0 * S),
                (140.0 * S, side * (HALF_W - 220.0 * S), HIP_Z + 300.0 * S),
                8.0 * S,
            )
        )
        parts.append(
            _axis_cylinder(
                f"cockpit_{side_name}_control_stick_grip",
                MATTE_BLACK,
                "z",
                (170.0 * S, side * (HALF_W - 220.0 * S), HIP_Z + 410.0 * S),
                17.0 * S,
                130.0 * S,
                4.0 * S,
            )
        )
        parts.append(
            _rounded_box(
                f"cockpit_{side_name}_foot_pedal_plate",
                DARK_STEEL,
                (140.0 * S, 110.0 * S, 16.0 * S),
                (300.0 * S, side * 150.0 * S, HIP_Z + 215.0 * S),
                4.0 * S,
                rotation=(0.0, -28.0, 0.0),
            )
        )
    parts.append(
        _rounded_box(
            "cockpit_harness_silver_center_buckle",
            BRIGHT_SILVER,
            (40.0 * S, 90.0 * S, 70.0 * S),
            (SEAT_X + 60.0 * S, 0.0, SEAT_Z + 260.0 * S * q),
            6.0 * S,
        )
    )
    return parts


def _pilot_parts() -> list:
    q = SEAT_SCALE
    pan_top = SEAT_Z + 40.0 * S * q
    parts = [
        _rounded_box(
            "pilot_placeholder_pelvis_block",
            PILOT_GRAY,
            (240.0 * S, 300.0 * S, 160.0 * S),
            (SEAT_X + 10.0 * S, 0.0, pan_top + 80.0 * S),
            30.0 * S,
        ),
        _rounded_box(
            "pilot_placeholder_torso_block",
            PILOT_GRAY,
            (220.0 * S, 340.0 * S, 440.0 * S),
            (SEAT_X - 30.0 * S, 0.0, pan_top + 370.0 * S),
            48.0 * S,
            rotation=(0.0, -8.0, 0.0),
        ),
    ]
    with BuildPart() as head:
        Sphere(100.0 * S)
    parts.append(
        _style(
            head.part.moved(Location((SEAT_X - 10.0 * S, 0.0, pan_top + 640.0 * S))),
            "pilot_placeholder_head_sphere",
            PILOT_GRAY,
        )
    )
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _rounded_box(
                f"pilot_placeholder_{side_name}_thigh_block",
                PILOT_GRAY,
                (400.0 * S, 130.0 * S, 130.0 * S),
                (SEAT_X + 190.0 * S, side * 105.0 * S, pan_top + 60.0 * S),
                34.0 * S,
            )
        )
        parts.append(
            _rounded_box(
                f"pilot_placeholder_{side_name}_calf_block",
                PILOT_GRAY,
                (110.0 * S, 120.0 * S, 330.0 * S),
                (SEAT_X + 350.0 * S, side * 105.0 * S, pan_top - 130.0 * S),
                30.0 * S,
                rotation=(0.0, 12.0, 0.0),
            )
        )
        parts.append(
            _rounded_box(
                f"pilot_placeholder_{side_name}_arm_block",
                PILOT_GRAY,
                (330.0 * S, 90.0 * S, 100.0 * S),
                (SEAT_X + 90.0 * S, side * 215.0 * S, pan_top + 390.0 * S),
                28.0 * S,
                rotation=(0.0, 24.0, 0.0),
            )
        )
    return parts


def _cockpit_gate_parts() -> list:
    hinge_x, hinge_z = GATE_HINGE
    y_reach = HALF_W - 150.0 * S
    parts = [
        _tube(
            "cockpit_gate_silver_lap_bar_restraint_hoop",
            SILVER,
            [
                (hinge_x, y_reach, hinge_z),
                (330.0 * S, y_reach - 10.0 * S, HIP_Z + 660.0 * S),
                (430.0 * S, y_reach - 40.0 * S, HIP_Z + 560.0 * S),
                (460.0 * S, 0.0, HIP_Z + 540.0 * S),
                (430.0 * S, -(y_reach - 40.0 * S), HIP_Z + 560.0 * S),
                (330.0 * S, -(y_reach - 10.0 * S), HIP_Z + 660.0 * S),
                (hinge_x, -y_reach, hinge_z),
            ],
            30.0 * S,
        ),
        _rounded_box(
            "cockpit_gate_glossy_red_latch_pad",
            GLOSS_RED,
            (70.0 * S, 160.0 * S, 90.0 * S),
            (452.0 * S, 0.0, HIP_Z + 542.0 * S),
            14.0 * S,
        ),
    ]
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _axis_cylinder(
                f"cockpit_gate_{side_name}_rubber_grip_sleeve",
                RUBBER,
                "y",
                (395.0 * S, side * (y_reach - 100.0 * S), HIP_Z + 596.0 * S),
                36.0 * S,
                130.0 * S,
                6.0 * S,
            )
        )
    return parts


def _cockpit_gate_hinge_parts() -> list:
    hinge_x, hinge_z = GATE_HINGE
    parts = []
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _axis_cylinder(
                f"cockpit_gate_{side_name}_hinge_drum",
                DARK_STEEL,
                "y",
                (hinge_x, side * (HALF_W - 130.0 * S), hinge_z),
                46.0 * S,
                80.0 * S,
                6.0 * S,
            )
        )
    return parts


def _sensor_head_parts() -> list:
    if SENSORS <= 0:
        return [
            _rounded_box(
                "sensor_mast_blanking_plate_detail_level_zero",
                GRAPHITE,
                (140.0 * S, 200.0 * S, 40.0 * S),
                (-140.0 * S, 0.0, CAGE_TOP + 20.0 * S),
                8.0 * S,
            )
        ]
    parts = [
        _rounded_box(
            "sensor_mast_black_riser_block",
            MATTE_BLACK,
            (150.0 * S, 210.0 * S, 150.0 * S),
            (-140.0 * S, 0.0, CAGE_TOP + 55.0 * S),
            14.0 * S,
        ),
        _axis_cylinder(
            "sensor_lidar_puck_graphite_drum",
            GRAPHITE,
            "z",
            (-140.0 * S, 0.0, CAGE_TOP + 165.0 * S),
            105.0 * S,
            80.0 * S,
            10.0 * S,
        ),
        _axis_cylinder(
            "sensor_lidar_translucent_amber_emitter_band",
            LENS_AMBER,
            "z",
            (-140.0 * S, 0.0, CAGE_TOP + 165.0 * S),
            108.0 * S,
            30.0 * S,
        ),
        _rounded_box(
            "sensor_front_stereo_camera_bar",
            MATTE_BLACK,
            (70.0 * S, 430.0 * S, 90.0 * S),
            (230.0 * S, 0.0, CAGE_TOP - 45.0 * S),
            12.0 * S,
        ),
    ]
    for side_name, side in (("left", 1.0), ("right", -1.0)):
        parts.append(
            _axis_cylinder(
                f"sensor_{side_name}_stereo_camera_lens_translucent",
                LENS_BLUE,
                "x",
                (268.0 * S, side * 150.0 * S, CAGE_TOP - 45.0 * S),
                34.0 * S,
                22.0 * S,
            )
        )
    if SENSORS >= 2:
        for side_name, side in (("left", 1.0), ("right", -1.0)):
            parts.append(
                _axis_cylinder(
                    f"sensor_{side_name}_rear_antenna_whip",
                    MATTE_BLACK,
                    "z",
                    (-250.0 * S, side * 170.0 * S, CAGE_TOP + 160.0 * S),
                    9.0 * S,
                    240.0 * S,
                )
            )
        parts.append(
            _rounded_box(
                "sensor_glossy_red_identity_beacon_fin",
                GLOSS_RED,
                (120.0 * S, 24.0 * S, 110.0 * S),
                (-140.0 * S, 0.0, CAGE_TOP + 250.0 * S),
                8.0 * S,
            )
        )
    return parts


# ---------------------------------------------------------------------------
# Leg (left side; right side is mirrored)
# ---------------------------------------------------------------------------
def _actuator_pod_parts(
    prefix: str,
    center: tuple[float, float, float],
    radius: float,
    length: float,
) -> list:
    with BuildPart() as pod:
        Cylinder(radius=radius, height=length, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        # bolt recesses around both faces for a serviced-joint look
        for face_sign in (1.0, -1.0):
            for index in range(6):
                angle = radians(index * 60.0 + 30.0)
                with Locations(
                    Location(
                        (
                            radius * 0.68 * cos(angle),
                            radius * 0.68 * sin(angle),
                            face_sign * (length / 2.0 - 5.0 * S),
                        )
                    )
                ):
                    Cylinder(
                        radius=radius * 0.075,
                        height=12.0 * S,
                        align=(Align.CENTER, Align.CENTER, Align.CENTER),
                        mode=Mode.SUBTRACT,
                    )
        _safe_fillet(pod.edges(), 8.0 * S)
    housing = _style(
        pod.part.moved(Location(center, _AXIS_ROT["y"])),
        f"{prefix}_graphite_actuator_pod_housing",
        GRAPHITE,
    )
    ring = _axis_cylinder(
        f"{prefix}_silver_rotor_seam_ring",
        BRIGHT_SILVER,
        "y",
        center,
        radius + 4.0 * S,
        length * 0.16,
    )
    covers = [
        _axis_cylinder(
            f"{prefix}_{side}_glossy_red_hinge_cover_disc",
            GLOSS_RED,
            "y",
            (center[0], center[1] + sign * (length / 2.0 + 9.0 * S), center[2]),
            radius * 0.62,
            18.0 * S,
            4.0 * S,
        )
        for side, sign in (("outboard", 1.0 if center[1] >= 0 else -1.0),)
    ]
    return [housing, ring, *covers]


def _left_thigh_core_parts() -> list:
    mid_z = (HIP_Z + KNEE_Z) / 2.0
    parts = [
        _rounded_box(
            "left_thigh_black_structural_column",
            MATTE_BLACK,
            (230.0 * S, 190.0 * S, THIGH_LEN - 60.0 * S),
            (10.0 * S, HIP_Y, mid_z),
            22.0 * S,
        ),
    ]
    for side_name, sign in (("inner", -1.0), ("outer", 1.0)):
        parts.append(
            _rounded_box(
                f"left_thigh_{side_name}_hip_fork_plate",
                DARK_STEEL,
                (250.0 * S, 30.0 * S, 340.0 * S),
                (0.0, HIP_Y + sign * 135.0 * S, HIP_Z - 140.0 * S),
                10.0 * S,
            )
        )
    parts.append(
        _tube(
            "left_thigh_outer_cable_conduit",
            RUBBER,
            [
                (-60.0 * S, HIP_Y + 120.0 * S, HIP_Z - 120.0 * S),
                (-95.0 * S, HIP_Y + 128.0 * S, mid_z),
                (-60.0 * S, HIP_Y + 120.0 * S, KNEE_Z + 110.0 * S),
            ],
            15.0 * S,
        )
    )
    # front linear actuator detail: silver rod inside black sleeve
    parts.append(
        _axis_cylinder(
            "left_thigh_front_actuator_sleeve",
            MATTE_BLACK,
            "z",
            (140.0 * S, HIP_Y, mid_z + 90.0 * S),
            33.0 * S,
            THIGH_LEN * 0.42,
            5.0 * S,
        )
    )
    parts.append(
        _axis_cylinder(
            "left_thigh_front_actuator_silver_rod",
            BRIGHT_SILVER,
            "z",
            (140.0 * S, HIP_Y, mid_z - 110.0 * S),
            19.0 * S,
            THIGH_LEN * 0.40,
        )
    )
    return parts


def _left_thigh_armor_parts() -> list:
    mid_z = (HIP_Z + KNEE_Z) / 2.0
    a = _clamp(thigh_armor_scale, 0.7, 1.3)
    parts = []
    with BuildPart() as shell:
        Box(120.0 * S, 250.0 * S * a, THIGH_LEN * 0.76, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        for seam_z in (-THIGH_LEN * 0.16, THIGH_LEN * 0.14):
            with Locations(Location((52.0 * S, 0.0, seam_z))):
                Box(10.0 * S, 260.0 * S * a, 5.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        _safe_fillet(shell.edges(), 26.0 * S)
    parts.append(
        _style(
            shell.part.moved(Location((190.0 * S, HIP_Y, mid_z + 20.0 * S))),
            "left_thigh_front_glossy_red_clamshell_with_service_seams",
            GLOSS_RED,
        )
    )
    parts.append(
        _rounded_box(
            "left_thigh_outer_glossy_red_side_panel",
            GLOSS_RED,
            (250.0 * S, 64.0 * S, THIGH_LEN * 0.62),
            (30.0 * S, HIP_Y + (128.0 * S + 60.0 * S * (a - 1.0)), mid_z + 30.0 * S),
            22.0 * S,
        )
    )
    parts.append(
        _rounded_box(
            "left_thigh_silver_trim_strip",
            BRIGHT_SILVER,
            (200.0 * S, 10.0 * S, 30.0 * S),
            (40.0 * S, HIP_Y + (162.0 * S + 60.0 * S * (a - 1.0)), mid_z + 140.0 * S),
            3.0 * S,
        )
    )
    parts.append(
        _rounded_box(
            "left_thigh_knee_glossy_red_guard_dome",
            GLOSS_RED,
            (110.0 * S, 210.0 * S * a, 150.0 * S),
            (150.0 * S, HIP_Y, KNEE_Z + 130.0 * S),
            34.0 * S,
        )
    )
    return parts


def _left_shin_core_parts() -> list:
    mid_z = (ANKLE_Z + KNEE_Z) / 2.0
    with BuildPart() as column:
        Cone(
            bottom_radius=72.0 * S,
            top_radius=98.0 * S,
            height=SHIN_LEN - 80.0 * S,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        _safe_fillet(column.edges(), 8.0 * S)
    parts = [
        _style(
            column.part.moved(Location((0.0, HIP_Y, mid_z))),
            "left_shin_black_tapered_structural_column",
            MATTE_BLACK,
        )
    ]
    for side_name, sign in (("inner", -1.0), ("outer", 1.0)):
        parts.append(
            _rounded_box(
                f"left_shin_{side_name}_knee_fork_plate",
                DARK_STEEL,
                (220.0 * S, 28.0 * S, 300.0 * S),
                (0.0, HIP_Y + sign * 118.0 * S, KNEE_Z - 130.0 * S),
                10.0 * S,
            )
        )
        parts.append(
            _rounded_box(
                f"left_shin_{side_name}_ankle_fork_plate",
                DARK_STEEL,
                (150.0 * S, 26.0 * S, 250.0 * S),
                (0.0, HIP_Y + sign * 95.0 * S, ANKLE_Z + 105.0 * S),
                9.0 * S,
            )
        )
    # rear calf piston: visible suspension-style actuator
    piston_top = (-125.0 * S, HIP_Y, KNEE_Z - 60.0 * S)
    piston_bot = (-95.0 * S, HIP_Y, ANKLE_Z + 80.0 * S)
    axis_len = (
        (piston_top[0] - piston_bot[0]) ** 2 + (piston_top[2] - piston_bot[2]) ** 2
    ) ** 0.5
    tilt = degrees(atan2(piston_top[0] - piston_bot[0], piston_top[2] - piston_bot[2]))
    upper_center = (
        (piston_top[0] + piston_bot[0]) / 2.0 - (piston_bot[0] - piston_top[0]) * 0.22,
        HIP_Y,
        (piston_top[2] + piston_bot[2]) / 2.0 + axis_len * 0.22,
    )
    lower_center = (
        (piston_top[0] + piston_bot[0]) / 2.0 + (piston_bot[0] - piston_top[0]) * 0.22,
        HIP_Y,
        (piston_top[2] + piston_bot[2]) / 2.0 - axis_len * 0.22,
    )
    parts.append(
        _rounded_box(
            "left_shin_calf_piston_black_sleeve",
            GRAPHITE,
            (66.0 * S, 66.0 * S, axis_len * 0.52),
            upper_center,
            14.0 * S,
            rotation=(0.0, tilt, 0.0),
        )
    )
    parts.append(
        _rounded_box(
            "left_shin_calf_piston_silver_rod",
            BRIGHT_SILVER,
            (34.0 * S, 34.0 * S, axis_len * 0.52),
            lower_center,
            10.0 * S,
            rotation=(0.0, tilt, 0.0),
        )
    )
    return parts


def _left_shin_armor_parts() -> list:
    mid_z = (ANKLE_Z + KNEE_Z) / 2.0
    a = _clamp(shin_armor_scale, 0.7, 1.3)
    parts = []
    with BuildPart() as guard:
        Box(110.0 * S, 230.0 * S * a, SHIN_LEN * 0.78, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        for index in range(4):
            with Locations(Location((48.0 * S, 0.0, -SHIN_LEN * 0.24 + index * 52.0 * S))):
                Box(14.0 * S, 150.0 * S * a, 20.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        with Locations(Location((44.0 * S, 0.0, SHIN_LEN * 0.24))):
            Box(10.0 * S, 240.0 * S * a, 5.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        _safe_fillet(guard.edges(), 24.0 * S)
    parts.append(
        _style(
            guard.part.moved(Location((125.0 * S, HIP_Y, mid_z + 10.0 * S))),
            "left_shin_front_glossy_red_guard_with_vent_slots",
            GLOSS_RED,
        )
    )
    parts.append(
        _rounded_box(
            "left_shin_outer_glossy_red_side_blade",
            GLOSS_RED,
            (170.0 * S, 50.0 * S, SHIN_LEN * 0.55),
            (0.0, HIP_Y + (110.0 * S + 50.0 * S * (a - 1.0)), mid_z),
            18.0 * S,
        )
    )
    return parts


def _left_foot_pad_parts() -> list:
    parts = []
    with BuildPart() as pad:
        Box(PAD_LEN, PAD_WID, PAD_TH, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _safe_fillet(pad.edges(), 22.0 * S)
    parts.append(
        _style(
            pad.part.moved(Location((50.0 * S, HIP_Y, 0.0))),
            "left_foot_compact_rubber_ground_pad",
            RUBBER,
        )
    )
    parts.append(
        _rounded_box(
            "left_foot_black_ankle_riser_block",
            MATTE_BLACK,
            (190.0 * S, 150.0 * S, ANKLE_Z - PAD_TH + 30.0 * S),
            (0.0, HIP_Y, PAD_TH + (ANKLE_Z - PAD_TH) / 2.0 - 5.0 * S),
            14.0 * S,
        )
    )
    parts.append(
        _rounded_box(
            "left_foot_glossy_red_toe_cap",
            GLOSS_RED,
            (130.0 * S, PAD_WID * 0.82, 60.0 * S),
            (50.0 * S + PAD_LEN / 2.0 - 60.0 * S, HIP_Y, PAD_TH + 12.0 * S),
            20.0 * S,
        )
    )
    parts.append(
        _rounded_box(
            "left_foot_glossy_red_heel_bumper",
            GLOSS_RED,
            (90.0 * S, PAD_WID * 0.62, 50.0 * S),
            (50.0 * S - PAD_LEN / 2.0 + 45.0 * S, HIP_Y, PAD_TH + 8.0 * S),
            16.0 * S,
        )
    )
    return parts


# ---------------------------------------------------------------------------
# Arm (left side; right side is mirrored)
# ---------------------------------------------------------------------------
def _left_upper_arm_core_parts() -> list:
    mid_z = (SHOULDER_Z + ELBOW_Z) / 2.0
    parts = [
        _rounded_box(
            "left_upper_arm_black_structural_column",
            MATTE_BLACK,
            (160.0 * S, 140.0 * S, UPPER_LEN - 60.0 * S),
            (SHOULDER_X, ARM_Y, mid_z),
            20.0 * S,
        ),
        _rounded_box(
            "left_upper_arm_shoulder_yoke_plate",
            DARK_STEEL,
            (200.0 * S, 30.0 * S, 260.0 * S),
            (SHOULDER_X, ARM_Y + 95.0 * S, SHOULDER_Z - 110.0 * S),
            9.0 * S,
        ),
    ]
    parts.append(
        _tube(
            "left_upper_arm_cable_conduit",
            RUBBER,
            [
                (SHOULDER_X - 90.0 * S, ARM_Y + 60.0 * S, SHOULDER_Z - 60.0 * S),
                (SHOULDER_X - 110.0 * S, ARM_Y + 70.0 * S, mid_z),
                (SHOULDER_X - 80.0 * S, ARM_Y + 55.0 * S, ELBOW_Z + 90.0 * S),
            ],
            13.0 * S,
        )
    )
    return parts


def _left_upper_arm_armor_parts() -> list:
    mid_z = (SHOULDER_Z + ELBOW_Z) / 2.0
    a = _clamp(upper_arm_armor_scale, 0.7, 1.3)
    parts = [
        _rounded_box(
            "left_shoulder_glossy_red_pauldron_shell",
            GLOSS_RED,
            (240.0 * S * a, 150.0 * S * a, 250.0 * S * a),
            (SHOULDER_X, ARM_Y + 70.0 * S * a, SHOULDER_Z + 60.0 * S),
            42.0 * S,
        ),
    ]
    with BuildPart() as panel:
        Box(90.0 * S, 190.0 * S * a, UPPER_LEN * 0.62, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        with Locations(Location((40.0 * S, 0.0, UPPER_LEN * 0.1))):
            Box(9.0 * S, 200.0 * S * a, 5.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        _safe_fillet(panel.edges(), 20.0 * S)
    parts.append(
        _style(
            panel.part.moved(Location((SHOULDER_X + 120.0 * S, ARM_Y, mid_z - 20.0 * S))),
            "left_upper_arm_front_glossy_red_panel_with_seam",
            GLOSS_RED,
        )
    )
    parts.append(
        _rounded_box(
            "left_upper_arm_silver_trim_strip",
            BRIGHT_SILVER,
            (10.0 * S, 150.0 * S * a, 26.0 * S),
            (SHOULDER_X + 168.0 * S, ARM_Y, mid_z + 80.0 * S),
            3.0 * S,
        )
    )
    return parts


def _left_forearm_core_parts() -> list:
    mid_z = (ELBOW_Z + WRIST_Z) / 2.0
    with BuildPart() as column:
        Cone(
            bottom_radius=58.0 * S,
            top_radius=80.0 * S,
            height=FORE_LEN - 70.0 * S,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        _safe_fillet(column.edges(), 6.0 * S)
    parts = [
        _style(
            column.part.moved(Location((SHOULDER_X, ARM_Y, mid_z))),
            "left_forearm_black_tapered_column",
            MATTE_BLACK,
        ),
        _rounded_box(
            "left_forearm_elbow_fork_plate",
            DARK_STEEL,
            (170.0 * S, 26.0 * S, 240.0 * S),
            (SHOULDER_X, ARM_Y - 92.0 * S, ELBOW_Z - 100.0 * S),
            9.0 * S,
        ),
        _rounded_box(
            "left_forearm_wrist_block",
            GRAPHITE,
            (150.0 * S, 130.0 * S, 120.0 * S),
            (SHOULDER_X, ARM_Y, WRIST_Z + 30.0 * S),
            16.0 * S,
        ),
    ]
    return parts


def _left_forearm_armor_parts() -> list:
    mid_z = (ELBOW_Z + WRIST_Z) / 2.0
    parts = []
    with BuildPart() as shell:
        Box(96.0 * S, 180.0 * S, FORE_LEN * 0.6, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        with Locations(Location((42.0 * S, 0.0, -FORE_LEN * 0.08))):
            Box(9.0 * S, 190.0 * S, 5.0 * S, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        _safe_fillet(shell.edges(), 22.0 * S)
    parts.append(
        _style(
            shell.part.moved(Location((SHOULDER_X + 105.0 * S, ARM_Y, mid_z + 10.0 * S))),
            "left_forearm_front_glossy_red_shell_with_seam",
            GLOSS_RED,
        )
    )
    parts.append(
        _rounded_box(
            "left_forearm_outer_glossy_red_fin",
            GLOSS_RED,
            (130.0 * S, 40.0 * S, FORE_LEN * 0.42),
            (SHOULDER_X - 20.0 * S, ARM_Y + 92.0 * S, mid_z),
            14.0 * S,
        )
    )
    return parts


def _left_hand_pad_parts() -> list:
    pad_center_z = WRIST_Z - 90.0 * S
    parts = [
        _axis_cylinder(
            "left_hand_rubber_contact_pad_sleeve",
            RUBBER,
            "z",
            (SHOULDER_X, ARM_Y, pad_center_z),
            96.0 * S,
            110.0 * S,
            14.0 * S,
        ),
    ]
    with BuildPart() as dome:
        Sphere(94.0 * S)
        Box(
            300.0 * S,
            300.0 * S,
            150.0 * S,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )
    parts.append(
        _style(
            dome.part.moved(Location((SHOULDER_X, ARM_Y, pad_center_z - 40.0 * S))),
            "left_hand_rubber_hemisphere_ground_dome",
            RUBBER,
        )
    )
    parts.append(
        _rounded_box(
            "left_hand_glossy_red_knuckle_guard",
            GLOSS_RED,
            (60.0 * S, 150.0 * S, 90.0 * S),
            (SHOULDER_X + 95.0 * S, ARM_Y, pad_center_z + 40.0 * S),
            18.0 * S,
        )
    )
    return parts


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def gen_step():
    """Return the GD01-inspired mecha as a labeled assembly of rigid groups."""
    knee_r = ACT_R * 0.82
    ankle_r = ACT_R * 0.62
    shoulder_r = ACT_R * 0.88
    elbow_r = ACT_R * 0.72

    left_hip = _actuator_pod_parts("left_hip", (0.0, HIP_Y, HIP_Z), ACT_R, 230.0 * S)
    left_knee = _actuator_pod_parts("left_knee", (0.0, HIP_Y, KNEE_Z), knee_r, 210.0 * S)
    left_ankle = _actuator_pod_parts("left_ankle", (0.0, HIP_Y, ANKLE_Z), ankle_r, 165.0 * S)
    left_shoulder = _actuator_pod_parts(
        "left_shoulder", (SHOULDER_X, SHOULDER_Y, SHOULDER_Z), shoulder_r, 200.0 * S
    )
    left_elbow = _actuator_pod_parts(
        "left_elbow", (SHOULDER_X, ARM_Y, ELBOW_Z), elbow_r, 170.0 * S
    )

    left_thigh_core = _left_thigh_core_parts()
    left_thigh_armor = _left_thigh_armor_parts()
    left_shin_core = _left_shin_core_parts()
    left_shin_armor = _left_shin_armor_parts()
    left_foot = _left_foot_pad_parts()
    left_ua_core = _left_upper_arm_core_parts()
    left_ua_armor = _left_upper_arm_armor_parts()
    left_fa_core = _left_forearm_core_parts()
    left_fa_armor = _left_forearm_armor_parts()
    left_hand = _left_hand_pad_parts()

    groups = {
        "pelvis_core": _group("pelvis_core", _pelvis_core_parts()),
        "pelvis_armor": _group("pelvis_armor", _pelvis_armor_parts()),
        "torso_frame": _group("torso_frame", _torso_frame_parts()),
        "torso_armor": _group("torso_armor", _torso_armor_parts()),
        "cockpit_module": _group("cockpit_module", _cockpit_module_parts()),
        "pilot_placeholder": _group(
            "pilot_placeholder",
            _pilot_parts()
            if pilot_placeholder_visibility
            else [
                _rounded_box(
                    "pilot_placeholder_omitted_marker_plate",
                    PILOT_GRAY,
                    (60.0 * S, 60.0 * S, 8.0 * S),
                    (SEAT_X, 0.0, SEAT_Z + 60.0 * S),
                )
            ],
        ),
        "cockpit_gate": _group("cockpit_gate", _cockpit_gate_parts()),
        "cockpit_gate_hinge": _group("cockpit_gate_hinge", _cockpit_gate_hinge_parts()),
        "sensor_head": _group("sensor_head", _sensor_head_parts()),
        "left_hip_actuator": _group("left_hip_actuator", left_hip),
        "right_hip_actuator": _mirror_group("right_hip_actuator", left_hip),
        "left_thigh_core": _group("left_thigh_core", left_thigh_core),
        "left_thigh_armor": _group("left_thigh_armor", left_thigh_armor),
        "right_thigh_core": _mirror_group("right_thigh_core", left_thigh_core),
        "right_thigh_armor": _mirror_group("right_thigh_armor", left_thigh_armor),
        "left_knee_actuator": _group("left_knee_actuator", left_knee),
        "right_knee_actuator": _mirror_group("right_knee_actuator", left_knee),
        "left_shin_core": _group("left_shin_core", left_shin_core),
        "left_shin_armor": _group("left_shin_armor", left_shin_armor),
        "right_shin_core": _mirror_group("right_shin_core", left_shin_core),
        "right_shin_armor": _mirror_group("right_shin_armor", left_shin_armor),
        "left_ankle_joint": _group("left_ankle_joint", left_ankle),
        "right_ankle_joint": _mirror_group("right_ankle_joint", left_ankle),
        "left_foot_pad": _group("left_foot_pad", left_foot),
        "right_foot_pad": _mirror_group("right_foot_pad", left_foot),
        "left_shoulder_actuator": _group("left_shoulder_actuator", left_shoulder),
        "right_shoulder_actuator": _mirror_group("right_shoulder_actuator", left_shoulder),
        "left_upper_arm_core": _group("left_upper_arm_core", left_ua_core),
        "left_upper_arm_armor": _group("left_upper_arm_armor", left_ua_armor),
        "right_upper_arm_core": _mirror_group("right_upper_arm_core", left_ua_core),
        "right_upper_arm_armor": _mirror_group("right_upper_arm_armor", left_ua_armor),
        "left_elbow_actuator": _group("left_elbow_actuator", left_elbow),
        "right_elbow_actuator": _mirror_group("right_elbow_actuator", left_elbow),
        "left_forearm_core": _group("left_forearm_core", left_fa_core),
        "left_forearm_armor": _group("left_forearm_armor", left_fa_armor),
        "right_forearm_core": _mirror_group("right_forearm_core", left_fa_core),
        "right_forearm_armor": _mirror_group("right_forearm_armor", left_fa_armor),
        "left_hand_pad": _group("left_hand_pad", left_hand),
        "right_hand_pad": _mirror_group("right_hand_pad", left_hand),
    }

    children = [groups[name] for name in FEATURE_ORDER]
    assembly = Compound(
        obj=children,
        children=children,
        label="gd01_inspired_manned_transformable_mecha_concept",
    )
    return {"shape": assembly, "params": "gd01_mecha_concept.params.js"}
