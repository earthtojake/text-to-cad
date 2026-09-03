"""Original 28-DOF compact humanoid research platform concept.

The model is intentionally designed from a blank parametric brief.  It does
not import or derive geometry from any other model.  STEP is the primary
artifact; every manufactured or articulated visual unit is a labeled child of
the root assembly.

Coordinate convention
---------------------
+X robot-left, +Y forward, +Z up.  The origin is on the floor midway between
the ankle centers.  Dimensions are millimetres.

Actuator accounting
-------------------
Legs: 6 per side.  Upper limbs: 6 per side, including one adaptive hand-close
axis per hand.  Waist: 2.  Neck: 2.  Total: 28 actuated axes.  Finger phalange
pivots are passive differential joints and are not counted as actuators.
"""

from __future__ import annotations

import functools
from cadgen import step

from dataclasses import asdict, dataclass
from math import sqrt
from typing import Iterable, Sequence

from cadgen import build123d as bd

from cadgen.assembly import AssemblyHelper, label_shape


# Restrained industrial palette.  Color carries subsystem meaning; there are
# deliberately no logos, words, decals, or vendor-specific panel motifs.
# Plain RGB(A) tuples / sRGB hex strings, not bd.Color objects: build123d's
# Shape.color setter builds the Color on assignment, and a module-level
# bd.Color(...) would import the CAD kernel before the @step freshness gate.
ALUMINUM = "#C8CDD1"
COMPOSITE = "#292D31"
ARMOR = "#ECEDE8"
GRAPHITE = "#191D21"
SENSOR_GLASS = "#0B1820"
STATUS_BLUE = "#76D7E5"
ELASTOMER = "#343A40"


Point = tuple[float, float, float]


@dataclass(frozen=True)
class JointSpec:
    """One visibly modeled source-level revolute actuator axis."""

    name: str
    region: str
    center: Point
    axis: Point
    limits_deg: tuple[float, float]
    radius: float
    length: float


# Athletic pose skeleton.  Segment distances remain close to the 330 mm thigh,
# 315 mm shank, 235 mm upper-arm, and 220 mm forearm design lengths.
SIDES: dict[str, float] = {"left": 1.0, "right": -1.0}
ANKLES: dict[str, Point] = {
    "left": (122.0, 16.0, 86.0),
    "right": (-122.0, -8.0, 86.0),
}
KNEES: dict[str, Point] = {
    "left": (93.0, 97.0, 390.0),
    "right": (-93.0, 73.0, 390.0),
}
HIPS: dict[str, Point] = {
    "left": (70.0, 12.0, 709.0),
    "right": (-70.0, -12.0, 709.0),
}
SHOULDERS: dict[str, Point] = {
    "left": (175.0, 5.0, 1070.0),
    "right": (-175.0, 5.0, 1070.0),
}
ELBOWS: dict[str, Point] = {
    "left": (210.0, 45.0, 840.0),
    "right": (-210.0, 45.0, 840.0),
}
WRISTS: dict[str, Point] = {
    "left": (225.0, 150.0, 650.0),
    "right": (-225.0, 150.0, 650.0),
}
PALMS: dict[str, Point] = {
    "left": (226.0, 153.0, 575.0),
    "right": (-226.0, 153.0, 575.0),
}


def _v(point: Point | bd.Vector) -> bd.Vector:
    return point if isinstance(point, bd.Vector) else bd.Vector(*point)


def _point(vector: bd.Vector) -> Point:
    return (float(vector.X), float(vector.Y), float(vector.Z))


def _add(point: Point, offset: Point) -> Point:
    return (point[0] + offset[0], point[1] + offset[1], point[2] + offset[2])


def _unit(direction: Point | bd.Vector) -> bd.Vector:
    vector = _v(direction)
    length = vector.length
    if length <= 1e-9:
        raise ValueError("Direction vector must be non-zero")
    return vector / length


def _distance(first: Point, second: Point) -> float:
    vector = _v(second) - _v(first)
    return sqrt(vector.X * vector.X + vector.Y * vector.Y + vector.Z * vector.Z)


def _plane_between(
    start: Point,
    end: Point,
    *,
    preferred_x: Point = (1.0, 0.0, 0.0),
) -> bd.Plane:
    start_v = _v(start)
    end_v = _v(end)
    z_dir = _unit(end_v - start_v)
    preference = _unit(preferred_x)
    x_dir = preference - z_dir * preference.dot(z_dir)
    if x_dir.length <= 1e-6:
        fallback = bd.Vector(0.0, 1.0, 0.0)
        x_dir = fallback - z_dir * fallback.dot(z_dir)
    x_dir = x_dir / x_dir.length
    return bd.Plane(origin=(start_v + end_v) * 0.5, x_dir=x_dir, z_dir=z_dir)


def _soft_box(width: float, depth: float, height: float, radius: float) -> object:
    """Centered box with a robust cosmetic fillet fallback."""

    body = bd.Box(width, depth, height)
    safe_radius = max(0.0, min(radius, width * 0.22, depth * 0.22, height * 0.22))
    if safe_radius <= 0.05:
        return body
    try:
        return bd.fillet(body.edges(), safe_radius)
    except Exception:
        return body


def _tapered_box(
    bottom_width: float,
    bottom_depth: float,
    top_width: float,
    top_depth: float,
    height: float,
    radius: float,
) -> object:
    bottom_radius = min(radius, bottom_width * 0.22, bottom_depth * 0.22)
    top_radius = min(radius, top_width * 0.22, top_depth * 0.22)
    with bd.BuildPart() as part:
        with bd.BuildSketch(bd.Plane.XY.offset(-height * 0.5)):
            bd.RectangleRounded(bottom_width, bottom_depth, bottom_radius)
        with bd.BuildSketch(bd.Plane.XY.offset(height * 0.5)):
            bd.RectangleRounded(top_width, top_depth, top_radius)
        bd.loft()
    return part.part


def _at(shape: object, center: Point, rotation: Point = (0.0, 0.0, 0.0)) -> object:
    return shape.moved(bd.Location(center, rotation))


def _oriented_box(
    start: Point,
    end: Point,
    width: float,
    depth: float,
    radius: float,
    *,
    preferred_x: Point = (1.0, 0.0, 0.0),
    local_offset: Point = (0.0, 0.0, 0.0),
) -> object:
    plane = _plane_between(start, end, preferred_x=preferred_x)
    origin = (
        plane.origin
        + plane.x_dir * local_offset[0]
        + plane.y_dir * local_offset[1]
        + plane.z_dir * local_offset[2]
    )
    placed_plane = bd.Plane(origin=origin, x_dir=plane.x_dir, z_dir=plane.z_dir)
    shape = _soft_box(width, depth, _distance(start, end), radius)
    return shape.moved(placed_plane.location)


def _axis_cylinder(center: Point, axis: Point, radius: float, length: float) -> object:
    plane = bd.Plane(origin=center, z_dir=_unit(axis))
    return bd.Cylinder(radius, length).moved(plane.location)


def _colored(shape: object, name: str, color: bd.Color, *details: object) -> object:
    return label_shape(shape, name, *details, color=color)


def _add_joint_module(assembly: AssemblyHelper, spec: JointSpec) -> object:
    """Create an exposed cartridge and attach its native revolute frame."""

    axis = _unit(spec.axis)
    cap_thickness = max(3.2, spec.length * 0.075)
    cap_radius = spec.radius * 0.72
    end_offset = spec.length * 0.5 + cap_thickness * 0.5
    negative_end = _point(_v(spec.center) - axis * end_offset)
    positive_end = _point(_v(spec.center) + axis * end_offset)
    accent_end = positive_end if spec.center[0] >= 0.0 else negative_end

    children = [
        _colored(
            _axis_cylinder(spec.center, spec.axis, spec.radius, spec.length),
            "cartridge",
            GRAPHITE,
            spec.name,
        ),
        _colored(
            _axis_cylinder(negative_end, spec.axis, cap_radius, cap_thickness),
            "bearing_cap",
            ALUMINUM,
            spec.name,
            "negative",
        ),
        _colored(
            _axis_cylinder(positive_end, spec.axis, cap_radius, cap_thickness),
            "bearing_cap",
            ALUMINUM,
            spec.name,
            "positive",
        ),
        _colored(
            _axis_cylinder(
                accent_end,
                spec.axis,
                cap_radius * 0.94,
                cap_thickness + 1.8,
            ),
            "status_ring",
            STATUS_BLUE,
            spec.name,
        ),
    ]
    module = assembly.add_module(spec.name, children)
    assembly.revolute_frame(
        module,
        spec.name,
        bd.Axis(spec.center, spec.axis),
        angular_range=spec.limits_deg,
    )
    return module


def _add_structural_link(
    assembly: AssemblyHelper,
    name: str,
    start: Point,
    end: Point,
    *,
    width: float,
    depth: float,
    preferred_x: Point = (1.0, 0.0, 0.0),
    armor_fraction: float = 0.56,
) -> object:
    """Twin aluminum spars around a carbon core and floating protective shell."""

    length = _distance(start, end)
    rail_offset = width * 0.31
    rail_width = max(8.0, width * 0.16)
    core_length = length * 0.88
    armor_length = length * armor_fraction
    inset = (length - core_length) * 0.5
    armor_inset = (length - armor_length) * 0.5

    children = [
        _colored(
            _oriented_box(
                start,
                end,
                width * 0.48,
                depth * 0.50,
                min(5.0, depth * 0.15),
                preferred_x=preferred_x,
                local_offset=(0.0, 0.0, inset * 0.1),
            ),
            "composite_spine",
            COMPOSITE,
            name,
        ),
        _colored(
            _oriented_box(
                start,
                end,
                rail_width,
                depth * 0.82,
                min(3.0, rail_width * 0.24),
                preferred_x=preferred_x,
                local_offset=(-rail_offset, 0.0, 0.0),
            ),
            "load_spar",
            ALUMINUM,
            name,
            "negative",
        ),
        _colored(
            _oriented_box(
                start,
                end,
                rail_width,
                depth * 0.82,
                min(3.0, rail_width * 0.24),
                preferred_x=preferred_x,
                local_offset=(rail_offset, 0.0, 0.0),
            ),
            "load_spar",
            ALUMINUM,
            name,
            "positive",
        ),
        _colored(
            _oriented_box(
                start,
                end,
                width * 0.82,
                depth * 1.05,
                min(7.0, depth * 0.19),
                preferred_x=preferred_x,
                local_offset=(0.0, depth * 0.21, armor_inset * 0.15),
            ),
            "protective_fairing",
            ARMOR,
            name,
        ),
    ]

    # Short dark service boot at the proximal end makes the exposed link read as
    # mechanically connected rather than floating between joint cartridges.
    plane = _plane_between(start, end, preferred_x=preferred_x)
    boot_center = _point(_v(start) + plane.z_dir * min(20.0, length * 0.10))
    children.append(
        _colored(
            _axis_cylinder(
                boot_center,
                _point(plane.z_dir),
                min(width, depth) * 0.31,
                min(20.0, length * 0.10),
            ),
            "cable_boot",
            ELASTOMER,
            name,
        )
    )
    return assembly.add_module(name, children)


def _add_foot(assembly: AssemblyHelper, side: str) -> object:
    sign = SIDES[side]
    ankle = ANKLES[side]
    toe_out = 7.0 * sign
    foot_center = (ankle[0], ankle[1] + 17.0, 23.0)
    rotation = (0.0, 0.0, toe_out)
    children = [
        _colored(
            _at(_soft_box(102.0, 235.0, 10.0, 5.0), (foot_center[0], foot_center[1], 5.0), rotation),
            "sole",
            GRAPHITE,
            side,
        ),
        _colored(
            _at(_soft_box(96.0, 148.0, 30.0, 10.0), (foot_center[0], foot_center[1] - 22.0, 24.0), rotation),
            "heel_shell",
            ARMOR,
            side,
        ),
        _colored(
            _at(_tapered_box(92.0, 82.0, 80.0, 68.0, 32.0, 9.0), (foot_center[0], foot_center[1] + 82.0, 26.0), rotation),
            "toe_shell",
            ARMOR,
            side,
        ),
        _colored(
            _at(_soft_box(70.0, 70.0, 18.0, 6.0), (foot_center[0], foot_center[1] + 92.0, 10.5), rotation),
            "toe_bumper",
            ELASTOMER,
            side,
        ),
        _colored(
            _at(_soft_box(12.0, 72.0, 66.0, 4.0), (ankle[0] + sign * 39.0, ankle[1], 76.0), rotation),
            "ankle_clevis",
            ALUMINUM,
            side,
            "outer",
        ),
        _colored(
            _at(_soft_box(12.0, 72.0, 66.0, 4.0), (ankle[0] - sign * 39.0, ankle[1], 76.0), rotation),
            "ankle_clevis",
            ALUMINUM,
            side,
            "inner",
        ),
    ]
    return assembly.add_module("foot", children, side)


def _add_pelvis(assembly: AssemblyHelper) -> object:
    children = [
        _colored(_at(_soft_box(150.0, 102.0, 104.0, 14.0), (0.0, 0.0, 750.0)), "pelvis_core", COMPOSITE),
        _colored(_at(_soft_box(82.0, 138.0, 116.0, 18.0), (68.0, 0.0, 746.0)), "pelvis_fairing", ARMOR, "left"),
        _colored(_at(_soft_box(82.0, 138.0, 116.0, 18.0), (-68.0, 0.0, 746.0)), "pelvis_fairing", ARMOR, "right"),
        _colored(_at(_tapered_box(178.0, 20.0, 205.0, 24.0, 88.0, 8.0), (0.0, 69.0, 754.0)), "pelvis_front_panel", ARMOR),
        _colored(_at(_soft_box(190.0, 22.0, 70.0, 7.0), (0.0, -62.0, 758.0)), "service_panel", GRAPHITE),
        _colored(_at(_soft_box(18.0, 118.0, 76.0, 5.0), (96.0, 0.0, 721.0)), "hip_bridge", ALUMINUM, "left"),
        _colored(_at(_soft_box(18.0, 118.0, 76.0, 5.0), (-96.0, 0.0, 721.0)), "hip_bridge", ALUMINUM, "right"),
    ]
    return assembly.add_module("pelvis", children)


def _add_torso(assembly: AssemblyHelper) -> object:
    children = [
        _colored(_at(_soft_box(168.0, 104.0, 224.0, 18.0), (0.0, -4.0, 953.0)), "torso_core", COMPOSITE),
        _colored(_at(_tapered_box(62.0, 126.0, 88.0, 142.0, 214.0, 16.0), (112.0, 0.0, 956.0)), "rib_shell", ARMOR, "left"),
        _colored(_at(_tapered_box(62.0, 126.0, 88.0, 142.0, 214.0, 16.0), (-112.0, 0.0, 956.0)), "rib_shell", ARMOR, "right"),
        _colored(_at(_tapered_box(170.0, 20.0, 238.0, 24.0, 206.0, 8.0), (0.0, 72.0, 958.0)), "sternum_panel", ARMOR),
        _colored(_at(_soft_box(72.0, 24.0, 218.0, 7.0), (0.0, -66.0, 951.0)), "rear_spine", GRAPHITE),
        _colored(_at(_soft_box(330.0, 50.0, 32.0, 8.0), (0.0, 0.0, 1065.0)), "shoulder_yoke", ALUMINUM),
        _colored(_at(_soft_box(188.0, 118.0, 74.0, 16.0), (0.0, 0.0, 856.0)), "abdomen_shell", ARMOR),
    ]
    for index, z_value in enumerate((900.0, 928.0, 956.0, 984.0), start=1):
        children.append(
            _colored(
                _at(_soft_box(56.0, 8.0, 7.0, 2.2), (0.0, 85.0, z_value)),
                "cooling_slot",
                GRAPHITE,
                index,
            )
        )
    return assembly.add_module("torso", children)


def _add_head(assembly: AssemblyHelper) -> object:
    center = (0.0, 10.0, 1210.0)
    children = [
        _colored(_at(_soft_box(150.0, 122.0, 126.0, 18.0), center, (3.0, 0.0, 0.0)), "head_shell", ARMOR),
        _colored(_at(_soft_box(158.0, 13.0, 70.0, 6.0), (0.0, 76.0, 1223.0), (3.0, 0.0, 0.0)), "sensor_visor", SENSOR_GLASS),
        _colored(_at(_soft_box(72.0, 18.0, 28.0, 7.0), (0.0, 63.0, 1174.0), (3.0, 0.0, 0.0)), "chin_structure", GRAPHITE),
        _colored(_axis_cylinder((82.0, 10.0, 1208.0), (1.0, 0.0, 0.0), 25.0, 16.0), "side_sensor", GRAPHITE, "left"),
        _colored(_axis_cylinder((-82.0, 10.0, 1208.0), (1.0, 0.0, 0.0), 25.0, 16.0), "side_sensor", GRAPHITE, "right"),
        _colored(_axis_cylinder((0.0, 6.0, 1280.0), (0.0, 0.0, 1.0), 29.0, 18.0), "lidar_puck", GRAPHITE),
        _colored(_axis_cylinder((0.0, 6.0, 1290.0), (0.0, 0.0, 1.0), 21.0, 4.0), "lidar_window", SENSOR_GLASS),
        _colored(_at(_soft_box(26.0, 8.0, 18.0, 3.0), (0.0, 85.0, 1214.0)), "depth_window", SENSOR_GLASS),
        _colored(_at(_soft_box(38.0, 7.0, 5.0, 2.0), (38.0, 84.0, 1248.0), (0.0, -7.0, 0.0)), "status_brow", STATUS_BLUE, "left"),
        _colored(_at(_soft_box(38.0, 7.0, 5.0, 2.0), (-38.0, 84.0, 1248.0), (0.0, 7.0, 0.0)), "status_brow", STATUS_BLUE, "right"),
        _colored(_at(_soft_box(54.0, 7.0, 5.0, 2.0), (0.0, 84.0, 1187.0)), "status_slit", STATUS_BLUE),
    ]
    for side, x_value in (("left", 38.0), ("right", -38.0)):
        children.extend(
            [
                _colored(_axis_cylinder((x_value, 83.0, 1225.0), (0.0, 1.0, 0.0), 11.0, 12.0), "stereo_camera", GRAPHITE, side),
                _colored(_axis_cylinder((x_value, 90.0, 1225.0), (0.0, 1.0, 0.0), 6.2, 3.0), "camera_glass", SENSOR_GLASS, side),
            ]
        )
    return assembly.add_module("sensor_head", children)


def _add_hand(assembly: AssemblyHelper, side: str) -> object:
    sign = SIDES[side]
    palm = PALMS[side]
    children: list[object] = [
        _colored(_at(_soft_box(38.0, 78.0, 82.0, 9.0), palm), "palm_frame", COMPOSITE, side),
        _colored(_at(_soft_box(9.0, 68.0, 70.0, 4.0), (palm[0] + sign * 22.0, palm[1], palm[2] + 4.0)), "hand_backplate", ARMOR, side),
        _colored(_axis_cylinder((palm[0], palm[1], palm[2] - 35.0), (1.0, 0.0, 0.0), 15.5, 49.0), "finger_differential", GRAPHITE, side),
    ]

    # Four visibly segmented adaptive fingers.  The second phalanx is shifted
    # forward by 7 mm, a restrained 20%-closed concept pose.
    for index, y_offset in enumerate((-26.0, -9.0, 9.0, 26.0), start=1):
        proximal_start = (palm[0], palm[1] + y_offset, palm[2] - 38.0)
        proximal_end = (palm[0], palm[1] + y_offset, palm[2] - 75.0)
        distal_end = (palm[0] - sign * 5.0, palm[1] + y_offset + 7.0, palm[2] - 111.0)
        children.extend(
            [
                _colored(_oriented_box(proximal_start, proximal_end, 11.0, 12.0, 3.5), "finger_proximal", ARMOR, side, index),
                _colored(_axis_cylinder(proximal_start, (1.0, 0.0, 0.0), 7.0, 15.0), "finger_pivot", GRAPHITE, side, index),
                _colored(_oriented_box(proximal_end, distal_end, 10.0, 11.0, 3.2), "finger_distal", ARMOR, side, index),
                _colored(_at(_soft_box(11.0, 12.0, 8.0, 3.0), distal_end), "fingertip_pad", ELASTOMER, side, index),
            ]
        )

    thumb_start = (palm[0], palm[1] + 42.0, palm[2] + 4.0)
    thumb_mid = (palm[0] - sign * 19.0, palm[1] + 47.0, palm[2] - 22.0)
    thumb_end = (palm[0] - sign * 29.0, palm[1] + 49.0, palm[2] - 51.0)
    children.extend(
        [
            _colored(_axis_cylinder(thumb_start, (0.0, 1.0, 0.0), 8.0, 18.0), "thumb_pivot", GRAPHITE, side),
            _colored(_oriented_box(thumb_start, thumb_mid, 13.0, 14.0, 4.0, preferred_x=(0.0, 1.0, 0.0)), "thumb_proximal", ARMOR, side),
            _colored(_oriented_box(thumb_mid, thumb_end, 11.0, 12.0, 3.5, preferred_x=(0.0, 1.0, 0.0)), "thumb_distal", ARMOR, side),
            _colored(_at(_soft_box(12.0, 14.0, 9.0, 3.0), thumb_end), "thumb_pad", ELASTOMER, side),
        ]
    )
    return assembly.add_module("adaptive_hand", children, side)


@functools.cache
def joint_specs() -> tuple[JointSpec, ...]:
    """The 28 actuated axes. Cached and built on first use: the vector math
    inside touches the CAD kernel, which must stay unloaded at import time."""
    specs: list[JointSpec] = [
        JointSpec("waist_yaw", "waist", (0.0, 0.0, 816.0), (0.0, 0.0, 1.0), (-35.0, 35.0), 48.0, 44.0),
        JointSpec("waist_pitch", "waist", (0.0, 0.0, 848.0), (1.0, 0.0, 0.0), (-20.0, 25.0), 42.0, 112.0),
        JointSpec("neck_yaw", "neck", (0.0, 2.0, 1134.0), (0.0, 0.0, 1.0), (-70.0, 70.0), 34.0, 42.0),
        JointSpec("neck_pitch", "neck", (0.0, 6.0, 1162.0), (1.0, 0.0, 0.0), (-35.0, 40.0), 30.0, 86.0),
    ]

    for side, sign in SIDES.items():
        ankle = ANKLES[side]
        knee = KNEES[side]
        hip = HIPS[side]
        shoulder = SHOULDERS[side]
        elbow = ELBOWS[side]
        wrist = WRISTS[side]
        palm = PALMS[side]
        forearm_axis = _point(_unit(_v(wrist) - _v(elbow)))

        specs.extend(
            [
                JointSpec(f"{side}_hip_yaw", "leg", _add(hip, (0.0, 0.0, 27.0)), (0.0, 0.0, 1.0), (-35.0, 35.0), 43.0, 42.0),
                JointSpec(f"{side}_hip_roll", "leg", _add(hip, (0.0, 0.0, 8.0)), (0.0, 1.0, 0.0), (-30.0, 30.0), 40.0, 58.0),
                JointSpec(f"{side}_hip_pitch", "leg", hip, (1.0, 0.0, 0.0), (-50.0, 85.0), 38.0, 88.0),
                JointSpec(f"{side}_knee_pitch", "leg", knee, (1.0, 0.0, 0.0), (0.0, 125.0), 37.0, 82.0),
                JointSpec(f"{side}_ankle_pitch", "leg", ankle, (1.0, 0.0, 0.0), (-35.0, 35.0), 32.0, 74.0),
                JointSpec(f"{side}_ankle_roll", "leg", _add(ankle, (0.0, 0.0, 23.0)), (0.0, 1.0, 0.0), (-22.0, 22.0), 29.0, 62.0),
                JointSpec(f"{side}_shoulder_pitch", "arm", shoulder, (1.0, 0.0, 0.0), (-130.0, 130.0), 40.0, 88.0),
                JointSpec(f"{side}_shoulder_roll", "arm", _add(shoulder, (0.0, 2.0, -2.0)), (0.0, 1.0, 0.0), (-25.0, 100.0), 37.0, 64.0),
                JointSpec(f"{side}_shoulder_yaw", "arm", _add(shoulder, (0.0, 0.0, -23.0)), (0.0, 0.0, 1.0), (-90.0, 90.0), 34.0, 50.0),
                JointSpec(f"{side}_elbow_pitch", "arm", elbow, (1.0, 0.0, 0.0), (0.0, 135.0), 30.0, 70.0),
                JointSpec(f"{side}_wrist_roll", "arm", wrist, forearm_axis, (-160.0, 160.0), 23.0, 46.0),
                JointSpec(f"{side}_hand_close", "hand", (palm[0], palm[1], palm[2] - 35.0), (1.0, 0.0, 0.0), (0.0, 70.0), 16.0, 50.0),
            ]
        )

    names = [spec.name for spec in specs]
    assert len(specs) == 28, f"Expected 28 actuated axes, got {len(specs)}"
    assert len(set(names)) == len(names), "Joint names must be unique"
    return tuple(specs)


def joint_manifest() -> list[dict[str, object]]:
    """JSON-safe actuator manifest for deterministic review and downstream use."""

    return [asdict(spec) for spec in joint_specs()]


def _build_robot() -> object:
    assembly = AssemblyHelper("compact_humanoid_28")

    _add_pelvis(assembly)
    _add_torso(assembly)
    _add_head(assembly)

    for side in SIDES:
        _add_foot(assembly, side)
        _add_structural_link(
            assembly,
            f"{side}_shank",
            ANKLES[side],
            KNEES[side],
            width=62.0,
            depth=48.0,
            preferred_x=(1.0, 0.0, 0.0),
            armor_fraction=0.60,
        )
        _add_structural_link(
            assembly,
            f"{side}_thigh",
            KNEES[side],
            HIPS[side],
            width=76.0,
            depth=58.0,
            preferred_x=(1.0, 0.0, 0.0),
            armor_fraction=0.62,
        )
        _add_structural_link(
            assembly,
            f"{side}_upper_arm",
            SHOULDERS[side],
            ELBOWS[side],
            width=56.0,
            depth=46.0,
            preferred_x=(0.0, 1.0, 0.0),
            armor_fraction=0.56,
        )
        _add_structural_link(
            assembly,
            f"{side}_forearm",
            ELBOWS[side],
            WRISTS[side],
            width=50.0,
            depth=42.0,
            preferred_x=(0.0, 1.0, 0.0),
            armor_fraction=0.60,
        )
        _add_hand(assembly, side)

    for spec in joint_specs():
        _add_joint_module(assembly, spec)

    robot = assembly.build()
    robot.label = "compact_humanoid_28"
    return robot


def design_metrics() -> dict[str, object]:
    """Source-space measurements used by the validation handoff."""

    return {
        "actuated_dof": len(joint_specs()),
        "left_thigh_length_mm": round(_distance(KNEES["left"], HIPS["left"]), 3),
        "left_shank_length_mm": round(_distance(ANKLES["left"], KNEES["left"]), 3),
        "left_upper_arm_length_mm": round(_distance(SHOULDERS["left"], ELBOWS["left"]), 3),
        "left_forearm_length_mm": round(_distance(ELBOWS["left"], WRISTS["left"]), 3),
        "shoulder_spacing_mm": abs(SHOULDERS["left"][0] - SHOULDERS["right"][0]),
        "ankle_spacing_mm": abs(ANKLES["left"][0] - ANKLES["right"][0]),
        "nominal_foot_length_mm": 235.0,
    }


@step(out="../STEP/compact_humanoid.step")
def compact_humanoid() -> object:
    """Return the labeled STEP-ready build123d assembly."""

    return _build_robot()


if __name__ == "__main__":
    compact_humanoid()
