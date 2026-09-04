"""Shared code for the research_humanoid models (plain module: no @step here).

Everything the humanoid and its two hand models build from: the palette, the
joint specs, the vector helpers, the part and actuator builders, the
source-level mate helpers, and `build_hand(side)` — the factory behind
`research_humanoid_hand_left.py` and `research_humanoid_hand_right.py`.
Any edit here rebuilds every model that imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin, sqrt
from typing import Iterable, Sequence

from cadgen import build123d as bd

from cadgen.assembly import AssemblyHelper, label_shape


# restrained production-prototype palette
# Plain RGB(A) tuples / sRGB hex strings, not bd.Color objects: build123d's
# Shape.color setter builds the Color on assignment, and a module-level
# bd.Color(...) would import the CAD kernel before the @step freshness gate.
ALUMINUM = "#AEB5BA"
MACHINED_DARK = "#2A3035"
CARBON = "#171B1E"
ARMOR = "#D8DBD7"
FASTENER = "#111417"
RUBBER = "#24292D"
SENSOR_GLASS = "#07151D"
STATUS = "#55B7C7"
COPPER = "#73523D"


Point = tuple[float, float, float]


@dataclass(frozen=True)
class JointSpec:
    name: str
    scope: str
    center: Point
    axis: Point
    limits_deg: tuple[float, float]
    radius: float
    length: float
    bolt_count: int = 6
    cable_direction: Point | None = None


SIDES: dict[str, float] = {"left": 1.0, "right": -1.0}

# Fresh adult-scale skeleton in a restrained athletic stance.  The body axes
# are intentionally not co-located: each serial cartridge has its own physical
# envelope and an intervening carrier/yoke.
ANKLES: dict[str, Point] = {
    "left": (128.0, 30.0, 95.0),
    "right": (-128.0, -20.0, 95.0),
}
KNEES: dict[str, Point] = {
    "left": (108.0, 102.0, 500.0),
    "right": (-108.0, 80.0, 500.0),
}
HIPS: dict[str, Point] = {
    "left": (100.0, 18.0, 895.0),
    "right": (-100.0, -18.0, 895.0),
}
SHOULDERS: dict[str, Point] = {
    "left": (260.0, 24.0, 1285.0),
    "right": (-260.0, 24.0, 1285.0),
}
ELBOWS: dict[str, Point] = {
    "left": (280.0, 84.0, 1070.0),
    "right": (-280.0, 84.0, 1070.0),
}
WRISTS: dict[str, Point] = {
    "left": (288.0, 205.0, 900.0),
    "right": (-288.0, 205.0, 900.0),
}
PALMS: dict[str, Point] = {
    "left": (292.0, 218.0, 845.0),
    "right": (-292.0, 218.0, 845.0),
}


def _v(point: Point | bd.Vector) -> bd.Vector:
    return point if isinstance(point, bd.Vector) else bd.Vector(*point)


def _p(vector: bd.Vector) -> Point:
    return (float(vector.X), float(vector.Y), float(vector.Z))


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Point, value: float) -> Point:
    return (a[0] * value, a[1] * value, a[2] * value)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point, b: Point) -> Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a: Point) -> float:
    return sqrt(_dot(a, a))


def _unit(a: Point | bd.Vector) -> Point:
    value = a if isinstance(a, tuple) else _p(a)  # tuple check first: bd.Vector would load the kernel
    magnitude = _length(value)
    if magnitude <= 1e-9:
        raise ValueError("Direction must be non-zero")
    return _scale(value, 1.0 / magnitude)


def _distance(a: Point, b: Point) -> float:
    return _length(_sub(b, a))


def _basis(axis: Point) -> tuple[Point, Point, Point]:
    w = _unit(axis)
    reference = (0.0, 0.0, 1.0) if abs(w[2]) < 0.82 else (0.0, 1.0, 0.0)
    u = _unit(_cross(w, reference))
    v = _unit(_cross(w, u))
    return u, v, w


def _lerp(a: Point, b: Point, t: float) -> Point:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _colored(shape: object, name: str, color: bd.Color, *details: object) -> object:
    return label_shape(shape, name, *details, color=color)


def _chamfered_box(width: float, depth: float, height: float, edge: float = 1.2) -> object:
    body = bd.Box(width, depth, height)
    safe = max(0.0, min(edge, width * 0.12, depth * 0.12, height * 0.12))
    if safe <= 0.05:
        return body
    try:
        return bd.chamfer(body.edges(), safe)
    except Exception:
        return body


def _tapered_box(
    bottom_width: float,
    bottom_depth: float,
    top_width: float,
    top_depth: float,
    height: float,
    corner: float = 2.0,
) -> object:
    lower_corner = min(corner, bottom_width * 0.12, bottom_depth * 0.12)
    upper_corner = min(corner, top_width * 0.12, top_depth * 0.12)
    with bd.BuildPart() as part:
        with bd.BuildSketch(bd.Plane.XY.offset(-height * 0.5)):
            bd.RectangleRounded(bottom_width, bottom_depth, lower_corner)
        with bd.BuildSketch(bd.Plane.XY.offset(height * 0.5)):
            bd.RectangleRounded(top_width, top_depth, upper_corner)
        bd.loft()
    return part.part


def _at(shape: object, center: Point, rotation: Point = (0.0, 0.0, 0.0)) -> object:
    return shape.moved(bd.Location(center, rotation))


def _local_box(
    center: Point,
    *,
    x_dir: Point,
    z_dir: Point,
    width: float,
    depth: float,
    height: float,
    edge: float = 1.2,
) -> object:
    plane = bd.Plane(origin=center, x_dir=_v(x_dir), z_dir=_v(z_dir))
    return _chamfered_box(width, depth, height, edge).moved(plane.location)


def _plane_between(start: Point, end: Point, preferred_x: Point = (1.0, 0.0, 0.0)) -> bd.Plane:
    z_dir = _unit(_sub(end, start))
    preference = _unit(preferred_x)
    projection = _sub(preference, _scale(z_dir, _dot(preference, z_dir)))
    if _length(projection) <= 1e-6:
        fallback = (0.0, 1.0, 0.0)
        projection = _sub(fallback, _scale(z_dir, _dot(fallback, z_dir)))
    return bd.Plane(origin=_lerp(start, end, 0.5), x_dir=_v(_unit(projection)), z_dir=_v(z_dir))


def _oriented_box(
    start: Point,
    end: Point,
    width: float,
    depth: float,
    *,
    preferred_x: Point = (1.0, 0.0, 0.0),
    offset: Point = (0.0, 0.0, 0.0),
    edge: float = 1.2,
) -> object:
    plane = _plane_between(start, end, preferred_x)
    origin = (
        plane.origin
        + plane.x_dir * offset[0]
        + plane.y_dir * offset[1]
        + plane.z_dir * offset[2]
    )
    placed = bd.Plane(origin=origin, x_dir=plane.x_dir, z_dir=plane.z_dir)
    return _chamfered_box(width, depth, _distance(start, end), edge).moved(placed.location)


def _oriented_tapered_box(
    start: Point,
    end: Point,
    start_width: float,
    start_depth: float,
    end_width: float,
    end_depth: float,
    *,
    preferred_x: Point = (1.0, 0.0, 0.0),
    offset: Point = (0.0, 0.0, 0.0),
    corner: float = 2.0,
) -> object:
    """Rounded loft between two link stations in an arbitrary orientation."""

    plane = _plane_between(start, end, preferred_x)
    origin = (
        plane.origin
        + plane.x_dir * offset[0]
        + plane.y_dir * offset[1]
        + plane.z_dir * offset[2]
    )
    placed = bd.Plane(origin=origin, x_dir=plane.x_dir, z_dir=plane.z_dir)
    return _tapered_box(
        start_width,
        start_depth,
        end_width,
        end_depth,
        _distance(start, end),
        corner,
    ).moved(placed.location)


def _axis_cylinder(center: Point, axis: Point, radius: float, length: float) -> object:
    return bd.Cylinder(radius, length).moved(bd.Plane(origin=center, z_dir=_v(_unit(axis))).location)


def _rod_between(start: Point, end: Point, radius: float) -> object:
    return _axis_cylinder(_lerp(start, end, 0.5), _sub(end, start), radius, _distance(start, end))


def _rect_frame(width: float, depth: float, height: float, wall_y: float, wall_z: float) -> object:
    outer = bd.Box(width, depth, height)
    inner = bd.Box(width + 2.0, max(1.0, depth - 2.0 * wall_y), max(1.0, height - 2.0 * wall_z))
    try:
        return outer - inner
    except Exception:
        return outer


def _bolt_stack(
    center: Point,
    axis: Point,
    *,
    name: str,
    index: object,
    head_radius: float = 3.8,
    head_height: float = 2.8,
) -> list[object]:
    direction = _unit(axis)
    washer_center = _add(center, _scale(direction, -0.55))
    head_center = _add(center, _scale(direction, head_height * 0.45))
    socket_center = _add(center, _scale(direction, head_height * 1.02))
    return [
        _colored(_axis_cylinder(washer_center, direction, head_radius + 1.2, 1.1), "washer", ALUMINUM, name, index),
        _colored(_axis_cylinder(head_center, direction, head_radius, head_height), "socket_head", FASTENER, name, index),
        _colored(_axis_cylinder(socket_center, direction, head_radius * 0.38, 0.45), "hex_socket", MACHINED_DARK, name, index),
    ]


def _bolt_circle(
    center: Point,
    axis: Point,
    *,
    name: str,
    count: int,
    circle_radius: float,
    face_offset: float,
    head_radius: float,
) -> list[object]:
    u, v, w = _basis(axis)
    parts: list[object] = []
    for index in range(count):
        angle = radians(index * 360.0 / count + 15.0)
        radial = _add(_scale(u, cos(angle) * circle_radius), _scale(v, sin(angle) * circle_radius))
        bolt_center = _add(_add(center, radial), _scale(w, face_offset))
        parts.extend(
            _bolt_stack(
                bolt_center,
                w,
                name=name,
                index=index + 1,
                head_radius=head_radius,
                head_height=max(2.2, head_radius * 0.72),
            )
        )
    return parts


def _panel_fasteners(
    center: Point,
    axis: Point,
    x_span: float,
    z_span: float,
    *,
    name: str,
) -> list[object]:
    u, v, w = _basis(axis)
    parts: list[object] = []
    for index, (x_sign, z_sign) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1)), start=1):
        position = _add(center, _add(_scale(u, x_sign * x_span * 0.5), _scale(v, z_sign * z_span * 0.5)))
        parts.extend(_bolt_stack(position, w, name=name, index=index, head_radius=3.0, head_height=2.3))
    return parts


def _body_joint_specs() -> tuple[JointSpec, ...]:
    specs: list[JointSpec] = [
        JointSpec("waist_yaw", "body", (0.0, -8.0, 1080.0), (0.0, 0.0, 1.0), (-40.0, 40.0), 42.0, 62.0, 8),
        JointSpec("waist_pitch", "body", (0.0, 8.0, 1175.0), (1.0, 0.0, 0.0), (-25.0, 30.0), 40.0, 92.0, 8, (0.0, -1.0, 0.0)),
        JointSpec("neck_yaw", "body", (0.0, -2.0, 1485.0), (0.0, 0.0, 1.0), (-75.0, 75.0), 27.0, 40.0, 6),
        JointSpec("neck_pitch", "body", (0.0, 6.0, 1545.0), (1.0, 0.0, 0.0), (-40.0, 45.0), 25.0, 66.0, 6, (0.0, -1.0, 0.0)),
    ]
    for side, sign in SIDES.items():
        ankle = ANKLES[side]
        knee = KNEES[side]
        hip = HIPS[side]
        shoulder = SHOULDERS[side]
        elbow = ELBOWS[side]
        wrist = WRISTS[side]
        forearm_axis = _unit(_sub(wrist, elbow))
        wrist_roll_center = _lerp(elbow, wrist, 0.70)
        hip_yaw_center = (sign * 118.0, hip[1] - 30.0, 1082.0)
        hip_roll_center = (sign * 145.0, hip[1] + 10.0, 992.0)
        shoulder_pitch_center = (sign * 185.0, -8.0, 1410.0)
        shoulder_roll_center = (sign * 276.0, 10.0, 1360.0)
        specs.extend(
            [
                JointSpec(f"{side}_hip_yaw", "body", hip_yaw_center, (0.0, 0.0, -1.0), (-40.0, 40.0), 37.0, 58.0, 8),
                JointSpec(f"{side}_hip_roll", "body", hip_roll_center, (0.0, 1.0, 0.0), (-32.0, 32.0), 39.0, 76.0, 8, (sign, 0.0, 0.0)),
                JointSpec(f"{side}_hip_pitch", "body", hip, (sign, 0.0, 0.0), (-55.0, 90.0), 44.0, 90.0, 8),
                JointSpec(f"{side}_knee_pitch", "body", knee, (sign, 0.0, 0.0), (0.0, 135.0), 40.0, 86.0, 8),
                JointSpec(f"{side}_ankle_pitch", "body", _add(ankle, (0.0, 24.0, 42.0)), (sign, 0.0, 0.0), (-38.0, 40.0), 34.0, 78.0, 6),
                JointSpec(f"{side}_ankle_roll", "body", _add(ankle, (0.0, -18.0, -38.0)), (0.0, 1.0, 0.0), (-24.0, 24.0), 30.0, 62.0, 6),
                JointSpec(f"{side}_shoulder_pitch", "body", shoulder_pitch_center, (sign, 0.0, 0.0), (-140.0, 140.0), 36.0, 86.0, 8),
                JointSpec(f"{side}_shoulder_roll", "body", shoulder_roll_center, (0.0, 1.0, 0.0), (-35.0, 110.0), 32.0, 70.0, 6, (sign, 0.0, 0.0)),
                JointSpec(f"{side}_shoulder_yaw", "body", shoulder, (0.0, 0.0, 1.0), (-100.0, 100.0), 30.0, 60.0, 6),
                JointSpec(f"{side}_elbow_pitch", "body", elbow, (sign, 0.0, 0.0), (0.0, 145.0), 32.0, 68.0, 6),
                JointSpec(f"{side}_wrist_pitch", "body", wrist, (sign, 0.0, 0.0), (-65.0, 65.0), 22.0, 52.0, 6),
                JointSpec(f"{side}_wrist_roll", "body", wrist_roll_center, forearm_axis, (-170.0, 170.0), 19.0, 48.0, 6),
            ]
        )
    assert len(specs) == 28
    return tuple(specs)


BODY_JOINT_SPECS = _body_joint_specs()


def _hand_joint_specs() -> tuple[JointSpec, ...]:
    specs: list[JointSpec] = []
    finger_offsets = (31.5, 10.5, -10.5, -31.5)
    finger_names = ("index", "middle", "ring", "little")
    finger_scales = (0.95, 1.0, 0.97, 0.84)
    for side, sign in SIDES.items():
        palm = PALMS[side]
        for finger_name, y_offset, finger_scale in zip(finger_names, finger_offsets, finger_scales):
            base = (palm[0], palm[1] + y_offset, palm[2] - 42.0)
            middle = (
                palm[0] - sign * 2.0,
                palm[1] + y_offset + 8.0,
                base[2] - 44.0 * finger_scale,
            )
            distal = (
                palm[0] - sign * 5.0,
                palm[1] + y_offset + 18.0,
                middle[2] - 31.0 * finger_scale,
            )
            for joint_name, center, limits in (
                ("mcp", base, (-15.0, 95.0)),
                ("pip", middle, (0.0, 110.0)),
                ("dip", distal, (0.0, 85.0)),
            ):
                specs.append(
                    JointSpec(
                        f"{side}_{finger_name}_{joint_name}",
                        "hand",
                        center,
                        (sign, 0.0, 0.0),
                        limits,
                        6.2 if joint_name == "mcp" else 5.2,
                        31.0,
                        4,
                    )
                )
        thumb_base = (palm[0] - sign * 17.0, palm[1] + 45.0, palm[2] + 7.0)
        thumb_mcp = (palm[0] - sign * 34.0, palm[1] + 50.0, palm[2] - 20.0)
        thumb_ip = (palm[0] - sign * 42.0, palm[1] + 54.0, palm[2] - 52.0)
        specs.extend(
            [
                JointSpec(f"{side}_thumb_opposition", "hand", thumb_base, (0.0, 0.0, 1.0), (-35.0, 55.0), 7.0, 32.0, 4),
                JointSpec(f"{side}_thumb_mcp", "hand", thumb_mcp, (sign, 0.0, 0.0), (-20.0, 85.0), 6.0, 30.0, 4),
                JointSpec(f"{side}_thumb_ip", "hand", thumb_ip, (sign, 0.0, 0.0), (0.0, 85.0), 5.0, 27.0, 4),
            ]
        )
    assert len(specs) == 30
    return tuple(specs)


HAND_JOINT_SPECS = _hand_joint_specs()


def _add_actuator(assembly: AssemblyHelper, spec: JointSpec) -> object:
    """Build a layered motor/reduction/output stack with real fastening cues."""

    u, v, w = _basis(spec.axis)
    radius = spec.radius
    length = spec.length
    children: list[object] = [
        _colored(_axis_cylinder(spec.center, w, radius, length * 0.72), "motor_housing", MACHINED_DARK, spec.name),
        _colored(
            _axis_cylinder(_add(spec.center, _scale(w, length * 0.27)), w, radius * 0.92, length * 0.38),
            "reduction_housing",
            MACHINED_DARK,
            spec.name,
        ),
        _colored(
            _axis_cylinder(_add(spec.center, _scale(w, length * 0.52)), w, radius * 0.80, 8.0),
            "output_flange",
            ALUMINUM,
            spec.name,
        ),
        _colored(
            _axis_cylinder(_add(spec.center, _scale(w, length * 0.58)), w, radius * 0.43, 11.0),
            "output_hub",
            ALUMINUM,
            spec.name,
        ),
        _colored(
            _axis_cylinder(_add(spec.center, _scale(w, -length * 0.48)), w, radius * 0.84, 7.0),
            "encoder_cap",
            ALUMINUM,
            spec.name,
        ),
        _colored(
            _axis_cylinder(_add(spec.center, _scale(w, length * 0.40)), w, radius * 0.64, 5.0),
            "cross_roller_bearing",
            FASTENER,
            spec.name,
        ),
        _colored(
            _axis_cylinder(_add(spec.center, _scale(w, -length * 0.31)), w, radius * 1.015, 2.4),
            "housing_seam",
            FASTENER,
            spec.name,
        ),
    ]

    # Scale the visible seams by cartridge family; small joints stay visually
    # quiet while high-load hip/knee units retain two serviceable bands.
    band_fractions = (-0.12, 0.16) if radius >= 36.0 else ((0.08,) if radius >= 27.0 else ())
    for band_index, fraction in enumerate(band_fractions, start=1):
        children.append(
            _colored(
                _axis_cylinder(_add(spec.center, _scale(w, length * fraction)), w, radius * 1.018, 2.0),
                "retention_band",
                ALUMINUM,
                spec.name,
                band_index,
            )
        )

    children.extend(
        _bolt_circle(
            spec.center,
            w,
            name=f"{spec.name}_output",
            count=spec.bolt_count,
            circle_radius=radius * 0.62,
            face_offset=length * 0.64,
            head_radius=max(2.5, min(4.3, radius * 0.067)),
        )
    )

    # One purposeful power/data exit and strain-relieved flex loop.
    cable_direction = _unit(spec.cable_direction) if spec.cable_direction is not None else v
    relief_span = max(8.0, min(12.0, radius * 0.28))
    gland_root = _add(_add(spec.center, _scale(cable_direction, radius + 3.0)), _scale(w, -length * 0.16))
    gland_tip = _add(gland_root, _scale(cable_direction, relief_span))
    cable_mid = _add(_add(gland_tip, _scale(cable_direction, 6.0)), _scale(w, -8.0))
    cable_end = _add(_add(cable_mid, _scale(cable_direction, 3.0)), _scale(w, -15.0))
    children.extend(
        [
            _colored(_axis_cylinder(gland_root, cable_direction, max(4.0, radius * 0.085), relief_span), "cable_gland", FASTENER, spec.name),
            _colored(_axis_cylinder(gland_tip, cable_direction, max(3.2, radius * 0.065), 8.0), "strain_relief", RUBBER, spec.name),
            _colored(_rod_between(gland_tip, cable_mid, max(2.1, radius * 0.045)), "flex_cable", RUBBER, spec.name, 1),
            _colored(_rod_between(cable_mid, cable_end, max(2.1, radius * 0.045)), "flex_cable", RUBBER, spec.name, 2),
        ]
    )

    return assembly.add_module(spec.name, children)


def _add_joint_yoke(assembly: AssemblyHelper, spec: JointSpec) -> object:
    """Double-shear clevis around one actuator cartridge."""

    u, v, w = _basis(spec.axis)
    ear_thickness = max(8.0, spec.radius * 0.18)
    ear_width = spec.radius * 2.22
    ear_depth = spec.radius * 1.22
    ear_offset = spec.length * 0.5 + ear_thickness * 0.56
    children: list[object] = []
    for side_name, sign in (("negative", -1.0), ("positive", 1.0)):
        ear_center = _add(spec.center, _scale(w, sign * ear_offset))
        children.append(
            _colored(
                _local_box(
                    ear_center,
                    x_dir=u,
                    z_dir=w,
                    width=ear_width,
                    depth=ear_depth,
                    height=ear_thickness,
                    edge=2.0,
                ),
                "clevis_ear",
                ALUMINUM,
                spec.name,
                side_name,
            )
        )
        # Two visible ear bolts show the load path into the surrounding link.
        for bolt_index, u_sign in enumerate((-1.0, 1.0), start=1):
            bolt_center = _add(
                _add(ear_center, _scale(u, u_sign * spec.radius * 0.70)),
                _scale(v, -spec.radius * 0.34),
            )
            children.extend(
                _bolt_stack(
                    _add(bolt_center, _scale(w, sign * ear_thickness * 0.62)),
                    _scale(w, sign),
                    name=f"{spec.name}_ear_{side_name}",
                    index=bolt_index,
                    head_radius=max(2.6, spec.radius * 0.058),
                    head_height=2.6,
                )
            )

    bridge_start = _add(spec.center, _scale(w, -ear_offset))
    bridge_end = _add(spec.center, _scale(w, ear_offset))
    children.extend(
        [
            _colored(
                _oriented_box(
                    bridge_start,
                    bridge_end,
                    max(14.0, spec.radius * 0.30),
                    max(18.0, spec.radius * 0.38),
                    preferred_x=u,
                    offset=(0.0, -spec.radius * 0.93, 0.0),
                    edge=1.8,
                ),
                "clevis_bridge",
                ALUMINUM,
                spec.name,
            ),
            _colored(
                _oriented_box(
                    bridge_start,
                    bridge_end,
                    max(7.0, spec.radius * 0.15),
                    max(28.0, spec.radius * 0.58),
                    preferred_x=u,
                    offset=(0.0, -spec.radius * 0.72, 0.0),
                    edge=1.0,
                ),
                "clevis_gusset",
                MACHINED_DARK,
                spec.name,
            ),
        ]
    )
    return assembly.add_module("joint_yoke", children, spec.name)


def _add_structural_link(
    assembly: AssemblyHelper,
    name: str,
    start: Point,
    end: Point,
    *,
    width: float,
    depth: float,
    trim_start: float,
    trim_end: float,
    preferred_x: Point,
    armor_fraction: float = 0.42,
    start_scale: float = 1.0,
    end_scale: float = 0.82,
) -> object:
    """Tapered twin-rail link with carbon web, end fittings, cover and harness."""

    total_length = _distance(start, end)
    direction = _unit(_sub(end, start))
    link_start = _add(start, _scale(direction, trim_start))
    link_end = _add(end, _scale(direction, -trim_end))
    length = _distance(link_start, link_end)
    rail_offset = width * 0.36
    rail_width = max(10.0, width * 0.14)
    plane = _plane_between(link_start, link_end, preferred_x)
    cover_start = _lerp(link_start, link_end, (1.0 - armor_fraction) * 0.5)
    cover_end = _lerp(link_start, link_end, 1.0 - (1.0 - armor_fraction) * 0.5)

    children: list[object] = [
        _colored(
            _oriented_tapered_box(
                link_start,
                link_end,
                width * 0.58 * start_scale,
                depth * 0.46 * start_scale,
                width * 0.58 * end_scale,
                depth * 0.46 * end_scale,
                preferred_x=preferred_x,
                corner=2.4,
            ),
            "carbon_shear_web",
            CARBON,
            name,
        ),
        _colored(
            _oriented_box(
                link_start,
                link_end,
                rail_width,
                depth * 0.86,
                preferred_x=preferred_x,
                offset=(-rail_offset, 0.0, 0.0),
                edge=1.3,
            ),
            "machined_rail",
            ALUMINUM,
            name,
            "negative",
        ),
        _colored(
            _oriented_box(
                link_start,
                link_end,
                rail_width,
                depth * 0.86,
                preferred_x=preferred_x,
                offset=(rail_offset, 0.0, 0.0),
                edge=1.3,
            ),
            "machined_rail",
            ALUMINUM,
            name,
            "positive",
        ),
        _colored(
            _oriented_tapered_box(
                cover_start,
                cover_end,
                width * 0.74 * (0.86 * start_scale + 0.14 * end_scale),
                max(6.0, depth * 0.14 * start_scale),
                width * 0.74 * (0.14 * start_scale + 0.86 * end_scale),
                max(6.0, depth * 0.14 * end_scale),
                preferred_x=preferred_x,
                offset=(0.0, depth * 0.43, 0.0),
                corner=2.4,
            ),
            "service_cover",
            ARMOR,
            name,
        ),
        _colored(
            _oriented_box(
                link_start,
                _lerp(link_start, link_end, 0.16),
                width * 0.78,
                depth * 0.92,
                preferred_x=preferred_x,
                edge=2.0,
            ),
            "proximal_end_fitting",
            MACHINED_DARK,
            name,
        ),
        _colored(
            _oriented_box(
                _lerp(link_start, link_end, 0.84),
                link_end,
                width * 0.78,
                depth * 0.92,
                preferred_x=preferred_x,
                edge=2.0,
            ),
            "distal_end_fitting",
            MACHINED_DARK,
            name,
        ),
    ]

    # Cross-braces make the rail pair read as a machined load path.
    for brace_index, fraction in enumerate((0.27, 0.50, 0.73), start=1):
        brace_center = _lerp(link_start, link_end, fraction)
        brace_start = _p(_v(brace_center) - plane.x_dir * rail_offset)
        brace_end = _p(_v(brace_center) + plane.x_dir * rail_offset)
        children.append(
            _colored(_oriented_box(brace_start, brace_end, 8.0, depth * 0.62, preferred_x=_p(plane.z_dir), edge=1.0), "cross_brace", ALUMINUM, name, brace_index)
        )

    # Functional cable trunk with two bends and retaining clips.
    cable_a = _p(_v(link_start) + plane.x_dir * (width * 0.44) + plane.y_dir * (depth * 0.46))
    cable_b = _p(_v(_lerp(link_start, link_end, 0.42)) + plane.x_dir * (width * 0.46) + plane.y_dir * (depth * 0.48))
    cable_c = _p(_v(_lerp(link_start, link_end, 0.78)) + plane.x_dir * (width * 0.41) + plane.y_dir * (depth * 0.48))
    cable_d = _p(_v(link_end) + plane.x_dir * (width * 0.36) + plane.y_dir * (depth * 0.42))
    for segment_index, (segment_start, segment_end) in enumerate(((cable_a, cable_b), (cable_b, cable_c), (cable_c, cable_d)), start=1):
        children.append(_colored(_rod_between(segment_start, segment_end, 2.8), "power_data_harness", RUBBER, name, segment_index))
    for clip_index, fraction in enumerate((0.25, 0.58, 0.84), start=1):
        clip_center = _p(
            _v(_lerp(link_start, link_end, fraction))
            + plane.x_dir * (width * 0.43)
            + plane.y_dir * (depth * 0.49)
        )
        children.append(_colored(_axis_cylinder(clip_center, _p(plane.y_dir), 5.3, 4.0), "harness_clip", ALUMINUM, name, clip_index))

    # Cover fasteners establish scale without random surface decoration.
    for fastener_index, fraction in enumerate((0.35, 0.65), start=1):
        fastener_center = _p(
            _v(_lerp(cover_start, cover_end, fraction))
            + plane.x_dir * (width * 0.27)
            + plane.y_dir * (depth * 0.52)
        )
        children.extend(
            _bolt_stack(
                fastener_center,
                _p(plane.y_dir),
                name=f"{name}_cover",
                index=fastener_index,
                head_radius=3.0,
                head_height=2.2,
            )
        )

    module = assembly.add_module(name, children)
    module.design_length_mm = length
    return module


def _add_foot(assembly: AssemblyHelper, side: str) -> object:
    sign = SIDES[side]
    ankle = ANKLES[side]
    toe_out = -5.5 * sign
    foot_center = (ankle[0], ankle[1] + 20.0, 24.0)
    rotation = (0.0, 0.0, toe_out)
    children: list[object] = [
        _colored(_at(_chamfered_box(108.0, 218.0, 14.0, 3.0), (foot_center[0], foot_center[1] - 4.0, 14.0), rotation), "aluminum_keel", ALUMINUM, side),
        _colored(_at(_tapered_box(108.0, 112.0, 94.0, 96.0, 22.0, 4.0), (foot_center[0], foot_center[1] + 62.0, 31.0), (4.5, 0.0, toe_out)), "sprung_toe_structure", MACHINED_DARK, side),
        _colored(_at(_tapered_box(96.0, 58.0, 86.0, 52.0, 24.0, 4.0), (foot_center[0], foot_center[1] - 86.0, 29.0), (-2.0, 0.0, toe_out)), "rockered_heel_structure", MACHINED_DARK, side),
        _colored(_at(_chamfered_box(92.0, 92.0, 8.0, 2.0), (foot_center[0], foot_center[1] + 60.0, 4.0), rotation), "forefoot_pad", RUBBER, side),
        _colored(_at(_chamfered_box(86.0, 68.0, 8.0, 2.0), (foot_center[0], foot_center[1] - 73.0, 4.0), rotation), "heel_pad", RUBBER, side),
        _colored(_at(_chamfered_box(72.0, 34.0, 7.0, 2.0), (foot_center[0], foot_center[1] + 116.0, 5.25), (4.5, 0.0, toe_out)), "toe_pad", RUBBER, side),
        _colored(_at(_tapered_box(74.0, 96.0, 66.0, 82.0, 9.0, 2.0), (foot_center[0], foot_center[1] + 8.0, 31.0), rotation), "instep_deck", ARMOR, side),
    ]

    # U-shaped ankle support plates and gussets.
    for ear_name, ear_sign in (("inner", -1.0), ("outer", 1.0)):
        x_value = ankle[0] + sign * ear_sign * 43.0
        children.append(
            _colored(_at(_chamfered_box(10.0, 86.0, 92.0, 2.0), (x_value, ankle[1], 72.0), rotation), "ankle_clevis", ALUMINUM, side, ear_name)
        )
        children.append(
            _colored(_at(_tapered_box(12.0, 42.0, 12.0, 70.0, 44.0, 1.5), (x_value, ankle[1] - 25.0, 40.0), rotation), "ankle_gusset", MACHINED_DARK, side, ear_name)
        )

    # Eight keel fasteners along two structural rows.
    for row_sign in (-1.0, 1.0):
        for index, y_offset in enumerate((-82.0, -28.0, 32.0, 88.0), start=1):
            bolt_center = (foot_center[0] + row_sign * 35.0, foot_center[1] + y_offset, 36.0)
            children.extend(_bolt_stack(bolt_center, (0.0, 0.0, 1.0), name=f"{side}_foot_keel", index=f"{row_sign:+.0f}_{index}", head_radius=3.2, head_height=2.5))
    return assembly.add_module("foot", children, side)


def _add_pelvis(assembly: AssemblyHelper) -> object:
    children: list[object] = [
        _colored(_at(_chamfered_box(78.0, 116.0, 218.0, 3.0), (0.0, -8.0, 988.0)), "pelvis_spine", ALUMINUM),
        _colored(_at(_chamfered_box(210.0, 132.0, 42.0, 3.0), (0.0, 0.0, 1068.0)), "waist_bulkhead", ALUMINUM),
        _colored(_at(_chamfered_box(174.0, 126.0, 104.0, 3.0), (0.0, -14.0, 962.0)), "battery_module", CARBON),
        _colored(_at(_chamfered_box(190.0, 14.0, 136.0, 2.0), (0.0, 74.0, 978.0)), "front_service_panel", ARMOR),
        _colored(_at(_chamfered_box(150.0, 16.0, 118.0, 2.0), (0.0, -78.0, 984.0)), "rear_power_panel", MACHINED_DARK),
    ]
    for side, sign in SIDES.items():
        x_value = sign * 133.0
        frame = _rect_frame(24.0, 174.0, 204.0, 26.0, 32.0)
        children.extend(
            [
                _colored(_at(frame, (x_value, 0.0, 982.0)), "hip_bulkhead_frame", ALUMINUM, side),
                _colored(_at(_chamfered_box(46.0, 162.0, 82.0, 2.5), (sign * 111.0, 0.0, 930.0)), "hip_load_block", MACHINED_DARK, side),
                _colored(_at(_chamfered_box(18.0, 142.0, 112.0, 2.0), (sign * 153.0, 0.0, 998.0)), "lateral_armor", ARMOR, side),
            ]
        )
    children.extend(_panel_fasteners((0.0, 83.0, 978.0), (0.0, 1.0, 0.0), 152.0, 108.0, name="pelvis_front_panel"))
    children.extend(_panel_fasteners((0.0, -88.0, 984.0), (0.0, -1.0, 0.0), 118.0, 90.0, name="pelvis_rear_panel"))
    # High-current battery leads remain visible at the service side.
    for side_name, x_value in (("positive", 34.0), ("negative", -34.0)):
        cable_start = (x_value, -88.0, 1025.0)
        cable_mid = (x_value * 1.15, -108.0, 1050.0)
        cable_end = (x_value * 0.82, -92.0, 1086.0)
        children.append(_colored(_rod_between(cable_start, cable_mid, 4.2), "battery_cable", COPPER, side_name, 1))
        children.append(_colored(_rod_between(cable_mid, cable_end, 4.2), "battery_cable", RUBBER, side_name, 2))
    return assembly.add_module("pelvis", children)


def _add_torso(assembly: AssemblyHelper) -> object:
    children: list[object] = [
        _colored(_at(_chamfered_box(68.0, 94.0, 338.0, 3.0), (0.0, -12.0, 1290.0)), "central_spine", ALUMINUM),
        _colored(_at(_chamfered_box(436.0, 76.0, 42.0, 3.0), (0.0, -2.0, 1412.0)), "shoulder_crossmember", ALUMINUM),
        _colored(_at(_chamfered_box(264.0, 86.0, 36.0, 2.5), (0.0, -4.0, 1142.0)), "lower_crossmember", ALUMINUM),
        _colored(_at(_chamfered_box(146.0, 116.0, 208.0, 3.0), (0.0, -18.0, 1272.0)), "compute_enclosure", CARBON),
        _colored(_at(_chamfered_box(198.0, 14.0, 94.0, 2.0), (0.0, 96.0, 1180.0)), "power_distribution_panel", MACHINED_DARK),
        _colored(_at(_chamfered_box(158.0, 18.0, 206.0, 2.0), (0.0, -92.0, 1285.0)), "rear_compute_door", MACHINED_DARK),
        _colored(
            _at(_tapered_box(224.0, 14.0, 330.0, 18.0, 214.0, 5.0), (0.0, 104.0, 1300.0)),
            "tapered_chest_fairing",
            ARMOR,
        ),
        _colored(_at(_chamfered_box(92.0, 10.0, 168.0, 3.0), (0.0, 114.0, 1290.0)), "sternum_service_spine", MACHINED_DARK),
    ]

    for side, sign in SIDES.items():
        x_value = sign * 172.0
        rib = _rect_frame(26.0, 188.0, 318.0, 27.0, 34.0)
        children.extend(
            [
                _colored(_at(rib, (x_value, 0.0, 1292.0)), "torso_rib_frame", ALUMINUM, side),
                _colored(_at(_chamfered_box(22.0, 150.0, 242.0, 2.0), (sign * 193.0, -3.0, 1292.0)), "side_shear_panel", CARBON, side),
                _colored(_at(_chamfered_box(14.0, 132.0, 164.0, 2.0), (sign * 210.0, 8.0, 1300.0)), "side_access_cover", ARMOR, side),
                _colored(_at(_chamfered_box(54.0, 98.0, 42.0, 2.0), (sign * 204.0, 0.0, 1400.0)), "clavicle_mount", MACHINED_DARK, side),
            ]
        )

    # Rear heat sink and protected cable trunks are asymmetric functional detail.
    for fin_index, z_value in enumerate(range(1202, 1389, 23), start=1):
        children.append(_colored(_at(_chamfered_box(126.0, 12.0, 8.0, 0.8), (16.0, -111.0, float(z_value))), "heat_sink_fin", ALUMINUM, fin_index))
    for trunk_name, x_value in (("motor_bus", -58.0), ("sensor_bus", 58.0)):
        cable_start = (x_value, -104.0, 1160.0)
        cable_mid = (x_value, -116.0, 1290.0)
        cable_end = (x_value * 1.55, -98.0, 1402.0)
        children.append(_colored(_rod_between(cable_start, cable_mid, 4.0), "torso_harness", RUBBER, trunk_name, 1))
        children.append(_colored(_rod_between(cable_mid, cable_end, 4.0), "torso_harness", RUBBER, trunk_name, 2))
    children.extend(_panel_fasteners((0.0, 108.0, 1290.0), (0.0, 1.0, 0.0), 206.0, 108.0, name="torso_front_panel"))
    children.extend(_panel_fasteners((0.0, 105.0, 1180.0), (0.0, 1.0, 0.0), 158.0, 64.0, name="power_panel"))
    return assembly.add_module("torso", children)


def _add_head(assembly: AssemblyHelper) -> object:
    center = (0.0, 6.0, 1622.0)
    children: list[object] = [
        _colored(_at(_tapered_box(142.0, 108.0, 158.0, 118.0, 100.0, 5.0), center, (1.5, 0.0, 0.0)), "sensor_chassis", MACHINED_DARK),
        _colored(_at(_chamfered_box(166.0, 110.0, 14.0, 2.8), (0.0, 3.0, 1680.0), (1.5, 0.0, 0.0)), "top_service_cover", ARMOR),
        _colored(_at(_tapered_box(10.0, 116.0, 12.0, 124.0, 108.0, 2.0), (81.0, 3.0, 1622.0), (1.5, 0.0, 0.0)), "side_shell", ARMOR, "left"),
        _colored(_at(_tapered_box(10.0, 116.0, 12.0, 124.0, 108.0, 2.0), (-81.0, 3.0, 1622.0), (1.5, 0.0, 0.0)), "side_shell", ARMOR, "right"),
        _colored(_at(_tapered_box(136.0, 8.0, 126.0, 8.0, 50.0, 5.0), (0.0, 67.0, 1632.0), (1.5, 0.0, 0.0)), "optical_visor", SENSOR_GLASS),
        _colored(_at(_chamfered_box(82.0, 8.0, 14.0, 2.0), (10.0, 65.0, 1598.0), (1.5, 0.0, 0.0)), "lower_sensor_rail", MACHINED_DARK),
        _colored(_at(_chamfered_box(112.0, 14.0, 92.0, 3.0), (0.0, -58.0, 1620.0), (1.5, 0.0, 0.0)), "rear_service_door", MACHINED_DARK),
    ]

    # Functional optical stack: glass, metal bezel, and recessed lens barrel.
    for sensor_name, x_value, z_value, lens_radius in (
        ("stereo_left", 43.0, 1634.0, 7.5),
        ("stereo_right", -43.0, 1634.0, 7.5),
    ):
        children.extend(
            [
                _colored(_axis_cylinder((x_value, 69.0, z_value), (0.0, 1.0, 0.0), lens_radius + 1.2, 5.0), "camera_bezel", SENSOR_GLASS, sensor_name),
                _colored(_axis_cylinder((x_value, 72.0, z_value), (0.0, 1.0, 0.0), lens_radius, 4.0), "camera_lens", SENSOR_GLASS, sensor_name),
                _colored(_axis_cylinder((x_value, 75.0, z_value), (0.0, 1.0, 0.0), lens_radius * 0.38, 1.2), "lens_aperture", FASTENER, sensor_name),
            ]
        )
    children.extend(
        [
            _colored(_at(_chamfered_box(26.0, 6.0, 17.0, 2.0), (23.0, 73.0, 1605.0)), "depth_window", SENSOR_GLASS),
            _colored(_at(_chamfered_box(14.0, 6.0, 11.0, 2.0), (-29.0, 73.0, 1606.0)), "tracking_window", SENSOR_GLASS),
            _colored(_at(_chamfered_box(16.0, 4.0, 3.0, 1.0), (51.0, 75.0, 1595.0)), "status_light", STATUS),
            _colored(_axis_cylinder((0.0, -18.0, 1694.0), (0.0, 0.0, 1.0), 26.0, 14.0), "lidar_base", MACHINED_DARK),
            _colored(_axis_cylinder((0.0, -18.0, 1702.0), (0.0, 0.0, 1.0), 22.0, 10.0), "lidar_window", SENSOR_GLASS),
            _colored(_axis_cylinder((0.0, -18.0, 1709.0), (0.0, 0.0, 1.0), 18.0, 3.0), "lidar_retainer", ALUMINUM),
        ]
    )

    # Side microphone arrays are recessed scale cues, not decorative perforation.
    for side, sign in SIDES.items():
        for mic_index, z_value in enumerate((1598.0, 1614.0, 1630.0, 1646.0), start=1):
            children.append(
                _colored(_axis_cylinder((sign * 87.0, 16.0, z_value), (1.0, 0.0, 0.0), 2.0, 2.0), "microphone_port", FASTENER, side, mic_index)
            )
    children.extend(_panel_fasteners((0.0, -67.0, 1620.0), (0.0, -1.0, 0.0), 84.0, 68.0, name="head_rear_door"))
    return assembly.add_module("sensor_head", children)


def _micro_joint_children(spec: JointSpec) -> list[object]:
    """Compact finger joint with a bearing pin, pulley and retention hardware."""

    u, v, w = _basis(spec.axis)
    children: list[object] = [
        _colored(_axis_cylinder(spec.center, w, spec.radius, spec.length), "finger_joint_body", MACHINED_DARK, spec.name),
        _colored(_axis_cylinder(_add(spec.center, _scale(w, spec.length * 0.48)), w, spec.radius * 0.74, 2.8), "finger_bearing_cap", ALUMINUM, spec.name, "outer"),
        _colored(_axis_cylinder(_add(spec.center, _scale(w, -spec.length * 0.48)), w, spec.radius * 0.74, 2.8), "finger_bearing_cap", ALUMINUM, spec.name, "inner"),
        _colored(_axis_cylinder(_add(spec.center, _scale(w, spec.length * 0.54)), w, spec.radius * 0.34, 4.0), "finger_pivot_pin", FASTENER, spec.name),
        _colored(_axis_cylinder(_add(spec.center, _scale(w, -spec.length * 0.18)), w, spec.radius * 0.82, 2.0), "tendon_pulley", COPPER, spec.name),
    ]
    for fastener_index, radial_sign in enumerate((-1.0, 1.0), start=1):
        screw_center = _add(
            _add(spec.center, _scale(u, radial_sign * spec.radius * 0.52)),
            _scale(w, spec.length * 0.57),
        )
        children.extend(
            _bolt_stack(
                screw_center,
                w,
                name=spec.name,
                index=fastener_index,
                head_radius=1.65,
                head_height=1.3,
            )
        )
    return children


def _relate_revolute(
    assembly: AssemblyHelper,
    fixed: object,
    moving: object,
    spec: JointSpec,
) -> None:
    """Author one coincident source-level revolute mate without changing pose."""

    axis = bd.Axis(spec.center, spec.axis)
    fixed_frame = assembly.revolute_frame(
        fixed,
        f"{spec.name}_parent",
        axis,
        angular_range=spec.limits_deg,
    )
    fixed_orientation = tuple(fixed.joints[fixed_frame.frame].location.orientation)
    moving_frame = assembly.rigid_frame(
        moving,
        spec.name,
        bd.Location(spec.center, fixed_orientation),
    )
    assembly.revolute(fixed_frame, moving_frame, angle=0.0, label=spec.name)


def _relate_rigid(
    assembly: AssemblyHelper,
    fixed: object,
    moving: object,
    center: Point,
    label: str,
) -> None:
    """Author a coincident carrier-to-link mount while preserving world pose."""

    fixed_frame = assembly.rigid_frame(fixed, f"{label}_fixed", bd.Location(center))
    moving_frame = assembly.rigid_frame(moving, f"{label}_moving", bd.Location(center))
    assembly.connect(fixed_frame, moving_frame, relation="rigid", label=label)


def _finger_segment(
    start: Point,
    end: Point,
    *,
    side: str,
    finger: str,
    segment: str,
    width: float,
) -> list[object]:
    sign = SIDES[side]
    rail_offset = width * 0.34
    children: list[object] = [
        _colored(
            _oriented_box(start, end, width * 0.58, 11.0, preferred_x=(sign, 0.0, 0.0), edge=1.1),
            "finger_carbon_core",
            CARBON,
            side,
            finger,
            segment,
        ),
        _colored(
            _oriented_box(
                start,
                end,
                3.4,
                13.5,
                preferred_x=(sign, 0.0, 0.0),
                offset=(-rail_offset, 0.0, 0.0),
                edge=0.7,
            ),
            "finger_side_plate",
            ALUMINUM,
            side,
            finger,
            segment,
            "inner",
        ),
        _colored(
            _oriented_box(
                start,
                end,
                3.4,
                13.5,
                preferred_x=(sign, 0.0, 0.0),
                offset=(rail_offset, 0.0, 0.0),
                edge=0.7,
            ),
            "finger_side_plate",
            ALUMINUM,
            side,
            finger,
            segment,
            "outer",
        ),
    ]
    tendon_start = _add(start, (sign * width * 0.09, 6.8, 0.0))
    tendon_end = _add(end, (sign * width * 0.09, 6.8, 0.0))
    children.append(_colored(_rod_between(tendon_start, tendon_end, 0.95), "finger_tendon", COPPER, side, finger, segment))
    return children


def build_hand(side: str) -> object:
    """One dexterous hand as a labelled sub-assembly, in the robot frame.

    The factory behind the `research_humanoid_hand_left` / `_right` models: each
    hand is its own model (a reflection is new geometry, and a hand is a
    functional unit worth its own STEP), and `research_humanoid.py` links both.
    """
    sign = SIDES[side]
    palm = PALMS[side]
    hand_assembly = AssemblyHelper(f"dexterous_hand_{side}")
    palm_children: list[object] = [
        _colored(_at(_rect_frame(38.0, 94.0, 104.0, 12.0, 15.0), palm), "palm_frame", ALUMINUM, side),
        _colored(_at(_chamfered_box(12.0, 86.0, 92.0, 1.8), (palm[0] + sign * 24.0, palm[1], palm[2])), "dorsal_plate", ARMOR, side),
        _colored(_at(_chamfered_box(8.0, 82.0, 72.0, 1.4), (palm[0] - sign * 23.0, palm[1] - 2.0, palm[2] + 5.0)), "tendon_guard", CARBON, side),
        _colored(_axis_cylinder((palm[0], palm[1], palm[2] + 50.0), (1.0, 0.0, 0.0), 25.0, 46.0), "wrist_output_adapter", MACHINED_DARK, side),
        _colored(_at(_chamfered_box(30.0, 88.0, 16.0, 1.5), (palm[0], palm[1], palm[2] - 48.0)), "knuckle_crossbar", ALUMINUM, side),
    ]

    # Six compact tendon-drive drums fill the palm volume without implying a mitten shell.
    for motor_index, (y_offset, z_offset) in enumerate(
        ((-29.0, 28.0), (0.0, 28.0), (29.0, 28.0), (-29.0, -2.0), (0.0, -2.0), (29.0, -2.0)),
        start=1,
    ):
        motor_center = (palm[0] - sign * 7.0, palm[1] + y_offset, palm[2] + z_offset)
        palm_children.extend(
            [
                _colored(_axis_cylinder(motor_center, (1.0, 0.0, 0.0), 8.2, 24.0), "tendon_motor", MACHINED_DARK, side, motor_index),
                _colored(_axis_cylinder((motor_center[0] - sign * 13.0, motor_center[1], motor_center[2]), (1.0, 0.0, 0.0), 6.0, 2.5), "tendon_spool", COPPER, side, motor_index),
            ]
        )

    finger_offsets = (31.5, 10.5, -10.5, -31.5)
    finger_names = ("index", "middle", "ring", "little")
    fingertip_drops = {"index": 24.0, "middle": 27.0, "ring": 25.0, "little": 22.0}
    joint_by_name = {spec.name: spec for spec in HAND_JOINT_SPECS}
    finger_records: list[tuple[str, JointSpec, JointSpec, JointSpec, Point]] = []
    for finger_name, y_offset in zip(finger_names, finger_offsets):
        mcp_spec = joint_by_name[f"{side}_{finger_name}_mcp"]
        pip_spec = joint_by_name[f"{side}_{finger_name}_pip"]
        dip_spec = joint_by_name[f"{side}_{finger_name}_dip"]
        tip = (
            dip_spec.center[0] - sign * 4.0,
            dip_spec.center[1] + 10.0,
            dip_spec.center[2] - fingertip_drops[finger_name],
        )
        finger_records.append((finger_name, mcp_spec, pip_spec, dip_spec, tip))

        # Separate tendons leave the palm through individual ferrules.
        ferrule = (palm[0] - sign * 22.0, palm[1] + y_offset, palm[2] - 37.0)
        palm_children.append(_colored(_axis_cylinder(ferrule, (1.0, 0.0, 0.0), 2.3, 3.0), "tendon_ferrule", ALUMINUM, side, finger_name))
        palm_children.append(_colored(_rod_between(ferrule, _add(mcp_spec.center, (-sign * 3.0, 5.0, 0.0)), 0.9), "palm_tendon", COPPER, side, finger_name))

    palm_module = hand_assembly.add_module("palm", palm_children, side)

    for finger_name, mcp_spec, pip_spec, dip_spec, tip in finger_records:
        proximal = hand_assembly.add_module(
            f"{finger_name}_proximal",
            _micro_joint_children(mcp_spec)
            + _finger_segment(mcp_spec.center, pip_spec.center, side=side, finger=finger_name, segment="proximal", width=13.5),
            side,
        )
        middle = hand_assembly.add_module(
            f"{finger_name}_middle",
            _micro_joint_children(pip_spec)
            + _finger_segment(pip_spec.center, dip_spec.center, side=side, finger=finger_name, segment="middle", width=12.0),
            side,
        )
        distal = hand_assembly.add_module(
            f"{finger_name}_distal",
            _micro_joint_children(dip_spec)
            + _finger_segment(dip_spec.center, tip, side=side, finger=finger_name, segment="distal", width=10.5)
            + [_colored(_at(_chamfered_box(11.0, 15.0, 10.0, 2.0), tip), "fingertip_pad", RUBBER, side, finger_name)],
            side,
        )
        _relate_revolute(hand_assembly, palm_module, proximal, mcp_spec)
        _relate_revolute(hand_assembly, proximal, middle, pip_spec)
        _relate_revolute(hand_assembly, middle, distal, dip_spec)

    thumb_opposition = joint_by_name[f"{side}_thumb_opposition"]
    thumb_mcp = joint_by_name[f"{side}_thumb_mcp"]
    thumb_ip = joint_by_name[f"{side}_thumb_ip"]
    thumb_tip = (thumb_ip.center[0] - sign * 11.0, thumb_ip.center[1] + 4.0, thumb_ip.center[2] - 25.0)
    thumb_metacarpal = hand_assembly.add_module(
        "thumb_metacarpal",
        _micro_joint_children(thumb_opposition)
        + _finger_segment(thumb_opposition.center, thumb_mcp.center, side=side, finger="thumb", segment="metacarpal", width=15.0),
        side,
    )
    thumb_proximal = hand_assembly.add_module(
        "thumb_proximal",
        _micro_joint_children(thumb_mcp)
        + _finger_segment(thumb_mcp.center, thumb_ip.center, side=side, finger="thumb", segment="proximal", width=13.0),
        side,
    )
    thumb_distal = hand_assembly.add_module(
        "thumb_distal",
        _micro_joint_children(thumb_ip)
        + _finger_segment(thumb_ip.center, thumb_tip, side=side, finger="thumb", segment="distal", width=11.0)
        + [_colored(_at(_chamfered_box(12.0, 16.0, 11.0, 2.0), thumb_tip), "thumb_tip_pad", RUBBER, side)],
        side,
    )
    _relate_revolute(hand_assembly, palm_module, thumb_metacarpal, thumb_opposition)
    _relate_revolute(hand_assembly, thumb_metacarpal, thumb_proximal, thumb_mcp)
    _relate_revolute(hand_assembly, thumb_proximal, thumb_distal, thumb_ip)

    return hand_assembly.build()


