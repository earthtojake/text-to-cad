from math import cos, radians, sin, tau

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
    Polygon,
    RectangleRounded,
    RegularPolygon,
    Torus,
    extrude,
    fillet,
    sweep,
)


# Units: millimeters.
# Origin: centered on the palm frame.
# XY: palm plane. +Z: back of hand/up. Fingers extend generally in +Y.

PALM_WIDTH = 70.0
PALM_LENGTH = 58.0
PALM_THICKNESS = 8.0
PALM_CORNER_RADIUS = 5.0
PALM_TOP_Z = PALM_THICKNESS

FINGER_LINK_WIDTH = 8.0
FINGER_LINK_THICKNESS = 6.0
FINGER_BASE_Z = PALM_TOP_Z + 4.5
FINGER_YAW_DEGREES = {
    "index": 2.0,
    "middle": 0.0,
    "ring": -2.0,
    "little": -4.0,
}
MAIN_FINGER_BASES = {
    "index": (-24.0, 30.0, FINGER_BASE_Z),
    "middle": (-8.0, 30.5, FINGER_BASE_Z + 0.5),
    "ring": (8.0, 30.0, FINGER_BASE_Z),
    "little": (24.0, 29.0, FINGER_BASE_Z - 0.5),
}
MAIN_LINK_LENGTHS = {
    "index": (25.0, 20.0, 16.0),
    "middle": (25.0, 20.0, 16.0),
    "ring": (25.0, 20.0, 16.0),
    "little": (22.0, 17.0, 14.0),
}
MAIN_FINGER_FLEX = {
    "index": (15.0, 40.0, 60.0),
    "middle": (13.0, 37.0, 56.0),
    "ring": (16.0, 42.0, 62.0),
    "little": (18.0, 45.0, 65.0),
}

THUMB_BASE = (-42.0, -5.0, FINGER_BASE_Z - 1.0)
THUMB_LINK_LENGTHS = (22.0, 18.0, 14.0)
THUMB_YAWS = (50.0, 36.0, 22.0)
THUMB_FLEX = (10.0, 30.0, 48.0)

DISPLAY_BASE_BOTTOM_Z = -64.0
DISPLAY_BASE_THICKNESS = 8.0
DISPLAY_BASE_TOP_Z = DISPLAY_BASE_BOTTOM_Z + DISPLAY_BASE_THICKNESS
WRIST_CENTER = (0.0, -45.0, -12.0)
WRIST_RING_OUTER_RADIUS = 27.0
WRIST_RING_INNER_RADIUS = 19.0

BRUSHED_ALUMINUM = Color(0.72, 0.74, 0.74, 1.0)
DARK_TITANIUM = Color(0.18, 0.20, 0.22, 1.0)
MATTE_BLACK = Color(0.01, 0.011, 0.012, 1.0)
DARK_GRAPHITE = Color(0.10, 0.105, 0.11, 1.0)
POLISHED_STEEL = Color(0.86, 0.88, 0.88, 1.0)
BLUE_ACCENT = Color(0.05, 0.33, 0.86, 1.0)
AMBER_ACCENT = Color(1.0, 0.55, 0.12, 1.0)


def _safe_fillet(edges, radius: float) -> None:
    """Apply a cosmetic fillet inside a BuildPart context when topology allows it."""
    try:
        fillet(edges, radius)
    except Exception:
        pass


def _set_metadata(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _teardrop_points(center: tuple[float, float], width: float, height: float) -> list[tuple[float, float]]:
    cx, cy = center
    return [
        (cx - width / 2.0, cy - height * 0.40),
        (cx + width / 2.0, cy - height * 0.40),
        (cx + width * 0.18, cy + height * 0.18),
        (cx, cy + height * 0.52),
        (cx - width * 0.18, cy + height * 0.18),
    ]


def _add_teardrop_sketch(center: tuple[float, float], width: float, height: float) -> None:
    Polygon(_teardrop_points(center, width, height), align=None)
    Circle(width * 0.28, align=Align.CENTER).locate(
        Location((center[0], center[1] + height * 0.28, 0.0))
    )


def _make_palm_frame():
    openings = [
        ((-20.0, 0.0), 12.5, 27.0),
        ((0.0, 5.0), 13.5, 31.0),
        ((20.0, 0.0), 12.5, 27.0),
    ]

    with BuildPart() as palm:
        with BuildSketch(Plane.XY):
            RectangleRounded(
                PALM_WIDTH,
                PALM_LENGTH,
                PALM_CORNER_RADIUS,
                align=(Align.CENTER, Align.CENTER),
            )
        extrude(amount=PALM_THICKNESS)
        _safe_fillet(palm.edges(), 0.8)

        for center, width, height in openings:
            with BuildSketch(Plane.XY.offset(-0.8)):
                _add_teardrop_sketch(center, width, height)
            extrude(amount=PALM_THICKNESS + 1.6, mode=Mode.SUBTRACT)

    return _set_metadata(palm.part, "skeletonized_palm_frame_70x58x8", BRUSHED_ALUMINUM)


def _make_palm_ribs():
    ribs = []
    openings = [
        ("left", (-20.0, 0.0), 12.5, 27.0),
        ("center", (0.0, 5.0), 13.5, 31.0),
        ("right", (20.0, 0.0), 12.5, 27.0),
    ]
    for name, center, width, height in openings:
        with BuildPart() as rib:
            with BuildSketch(Plane.XY.offset(PALM_TOP_Z)):
                _add_teardrop_sketch(center, width + 6.0, height + 6.0)
            extrude(amount=2.0)

            with BuildSketch(Plane.XY.offset(PALM_TOP_Z - 0.4)):
                _add_teardrop_sketch(center, width + 0.6, height + 0.6)
            extrude(amount=3.0, mode=Mode.SUBTRACT)
            _safe_fillet(rib.edges(), 1.5)

        ribs.append(_set_metadata(rib.part, f"raised_palm_rib_{name}_3mm_lip", BRUSHED_ALUMINUM))

    return ribs


def _make_display_base():
    with BuildPart() as base:
        with BuildSketch(Plane.XY):
            RectangleRounded(110.0, 80.0, 6.0, align=(Align.CENTER, Align.CENTER))
        extrude(amount=DISPLAY_BASE_THICKNESS)
        _safe_fillet(base.edges(), 3.0)

        for x_pos in (-44.0, 44.0):
            for y_pos in (-30.0, 30.0):
                with Locations(Location((x_pos, y_pos, -0.6))):
                    Cylinder(
                        radius=2.35,
                        height=DISPLAY_BASE_THICKNESS + 1.2,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )
                with Locations(Location((x_pos, y_pos, DISPLAY_BASE_THICKNESS - 2.7))):
                    Cone(
                        bottom_radius=2.35,
                        top_radius=5.1,
                        height=2.9,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )

    part = base.part.moved(Location((0.0, -5.0, DISPLAY_BASE_BOTTOM_Z)))
    return _set_metadata(part, "rounded_display_base_110x80x8_with_countersunk_holes", DARK_TITANIUM)


def _make_support_post():
    height = WRIST_CENTER[2] - WRIST_RING_OUTER_RADIUS - DISPLAY_BASE_TOP_Z
    with BuildPart() as post:
        Cylinder(
            radius=6.5,
            height=height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        _safe_fillet(post.edges(), 0.8)

    part = post.part.moved(Location((0.0, -45.0, DISPLAY_BASE_TOP_Z)))
    return _set_metadata(part, "vertical_support_post_to_wrist_gimbal", DARK_TITANIUM)


def _make_wrist_gimbal():
    parts = []

    with BuildPart() as wrist_cylinder:
        Cylinder(
            radius=21.0,
            height=35.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        _safe_fillet(wrist_cylinder.edges(), 0.5)
    cylinder = wrist_cylinder.part.moved(Location(WRIST_CENTER, (90.0, 0.0, 0.0)))
    parts.append(_set_metadata(cylinder, "wrist_short_cylinder_axis_y_od42_length35", DARK_TITANIUM))

    with BuildPart() as ring:
        Cylinder(
            radius=WRIST_RING_OUTER_RADIUS,
            height=6.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        Cylinder(
            radius=WRIST_RING_INNER_RADIUS,
            height=7.0,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )
        _safe_fillet(ring.edges(), 0.5)
    roll_ring = ring.part.moved(Location(WRIST_CENTER, (90.0, 0.0, 0.0)))
    parts.append(_set_metadata(roll_ring, "perpendicular_wrist_roll_ring_od54_id38_thick6", DARK_TITANIUM))

    for side, y_offset in (("front", 3.9), ("rear", -3.9)):
        for index in range(8):
            angle = tau * index / 8.0
            x_pos = WRIST_CENTER[0] + 23.7 * cos(angle)
            z_pos = WRIST_CENTER[2] + 23.7 * sin(angle)
            with BuildPart() as bolt:
                Cylinder(radius=2.15, height=1.5, align=(Align.CENTER, Align.CENTER, Align.CENTER))
                _safe_fillet(bolt.edges(), 0.5)
            part = bolt.part.moved(Location((x_pos, WRIST_CENTER[1] + y_offset, z_pos), (90.0, 0.0, 0.0)))
            parts.append(
                _set_metadata(
                    part,
                    f"wrist_ring_{side}_polished_bolt_head_{index + 1:02d}",
                    POLISHED_STEEL,
                )
            )

    return parts


def _make_servo_housing(label: str, center: tuple[float, float, float], accent_color: Color):
    with BuildPart() as servo:
        Box(12.0, 18.0, 8.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        _safe_fillet(servo.edges(), 1.2)
    body = servo.part.moved(Location(center))
    body = _set_metadata(body, f"dark_graphite_servo_housing_{label}_12x18x8", DARK_GRAPHITE)

    with BuildPart() as panel:
        Box(8.0, 2.8, 0.6, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        _safe_fillet(panel.edges(), 0.25)
    accent = panel.part.moved(Location((center[0], center[1] + 5.5, center[2] + 4.25)))
    accent = _set_metadata(accent, f"{label}_servo_blue_amber_accent_panel", accent_color)

    screws = []
    for sx in (-4.2, 4.2):
        for sy in (-6.3, 6.3):
            screws.append(
                _make_screw_head(
                    f"{label}_servo_screw_{len(screws) + 1:02d}",
                    (center[0] + sx, center[1] + sy, center[2] + 4.55),
                    radius=1.05,
                    height=0.55,
                    axis="z",
                )
            )

    return [body, accent, *screws]


def _make_screw_head(label: str, center: tuple[float, float, float], radius: float, height: float, axis: str):
    with BuildPart() as screw:
        Cylinder(radius=radius, height=height, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        _safe_fillet(screw.edges(), 0.35)
    rotations = {
        "x": (0.0, 90.0, 0.0),
        "y": (90.0, 0.0, 0.0),
        "z": (0.0, 0.0, 0.0),
    }
    part = screw.part.moved(Location(center, rotations[axis]))
    return _set_metadata(part, f"polished_steel_{label}", POLISHED_STEEL)


def _make_palm_fasteners():
    parts = []
    locations = [
        (-29.0, -22.0),
        (29.0, -22.0),
        (-29.0, 22.0),
        (29.0, 22.0),
        (-11.0, -23.0),
        (11.0, -23.0),
        (-11.0, 24.0),
        (11.0, 24.0),
    ]
    for index, (x_pos, y_pos) in enumerate(locations, start=1):
        parts.append(
            _make_screw_head(
                f"palm_frame_socket_screw_{index:02d}",
                (x_pos, y_pos, PALM_TOP_Z + 0.45),
                radius=1.65,
                height=0.9,
                axis="z",
            )
        )
    return parts


def _make_mechanical_link(label: str, length: float, start: tuple[float, float, float], flex: float, yaw: float):
    with BuildPart() as link:
        with BuildSketch(Plane.XY):
            RectangleRounded(
                FINGER_LINK_WIDTH,
                length,
                2.0,
                align=(Align.CENTER, Align.MIN),
            )
        extrude(amount=FINGER_LINK_THICKNESS)

        with Locations(Location((0.0, length * 0.50, FINGER_LINK_THICKNESS - 0.55))):
            Box(
                FINGER_LINK_WIDTH * 0.48,
                max(5.0, length * 0.48),
                1.3,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )
        for x_pos in (-FINGER_LINK_WIDTH / 2.0 - 0.15, FINGER_LINK_WIDTH / 2.0 + 0.15):
            with Locations(Location((x_pos, length * 0.52, FINGER_LINK_THICKNESS * 0.52))):
                Box(
                    1.15,
                    max(5.0, length * 0.52),
                    3.3,
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.SUBTRACT,
                )
        _safe_fillet(link.edges(), 1.0)

    part = link.part.moved(Location((0.0, 0.0, -FINGER_LINK_THICKNESS / 2.0)))
    part = part.moved(Location(start, (-flex, 0.0, yaw)))
    return _set_metadata(part, f"brushed_aluminum_{label}_rounded_recessed_link", BRUSHED_ALUMINUM)


def _segment_end(start: tuple[float, float, float], length: float, flex: float, yaw: float) -> tuple[float, float, float]:
    edge = Edge.make_line((0.0, 0.0, 0.0), (0.0, length, 0.0)).moved(
        Location(start, (-flex, 0.0, yaw))
    )
    candidates = [tuple(vertex) for vertex in edge.vertices()]
    return max(
        candidates,
        key=lambda point: (point[0] - start[0]) ** 2
        + (point[1] - start[1]) ** 2
        + (point[2] - start[2]) ** 2,
    )


def _make_hinge_pin(label: str, center: tuple[float, float, float], yaw: float):
    parts = []
    with BuildPart() as pin:
        Cylinder(radius=4.0, height=12.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        _safe_fillet(pin.edges(), 0.5)
    body = pin.part.moved(Location(center, (0.0, 90.0, yaw)))
    parts.append(_set_metadata(body, f"polished_steel_{label}_hinge_pin_d8", POLISHED_STEEL))

    for side, x_local in (("left", -6.8), ("right", 6.8)):
        x_pos = center[0] + x_local * cos(radians(yaw))
        y_pos = center[1] + x_local * sin(radians(yaw))
        with BuildPart() as cap:
            Cylinder(radius=5.0, height=1.5, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            _safe_fillet(cap.edges(), 0.5)
        cap_part = cap.part.moved(Location((x_pos, y_pos, center[2]), (0.0, 90.0, yaw)))
        parts.append(_set_metadata(cap_part, f"polished_steel_{label}_{side}_circular_end_cap", POLISHED_STEEL))

        screw_offset = 0.85 if side == "right" else -0.85
        parts.append(
            _make_screw_head(
                f"{label}_{side}_visible_cap_screw",
                (
                    center[0] + (x_local + screw_offset) * cos(radians(yaw)),
                    center[1] + (x_local + screw_offset) * sin(radians(yaw)),
                    center[2],
                ),
                radius=1.35,
                height=0.65,
                axis="x",
            )
        )

    return parts


def _make_fingertip_pad(label: str, start: tuple[float, float, float], flex: float, yaw: float):
    pad_length = 7.2
    with BuildPart() as pad:
        with BuildSketch(Plane.XY):
            RectangleRounded(9.5, pad_length, 3.3, align=(Align.CENTER, Align.MIN))
        extrude(amount=7.2)
        _safe_fillet(pad.edges(), 1.0)
    part = pad.part.moved(Location((0.0, 0.0, -3.6)))
    part = part.moved(Location(start, (-flex, 0.0, yaw)))
    return _set_metadata(part, f"matte_black_rubber_{label}_rounded_fingertip_pad", MATTE_BLACK)


def _make_thumb_saddle():
    with BuildPart() as saddle:
        Box(13.0, 20.0, 9.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        _safe_fillet(saddle.edges(), 1.0)
    part = saddle.part.moved(Location((-35.5, -4.0, PALM_TOP_Z + 1.5), (0.0, 0.0, -28.0)))
    return _set_metadata(part, "brushed_aluminum_left_side_thumb_mount_saddle", BRUSHED_ALUMINUM)


def _make_fingers():
    parts = []

    for finger_name, base in MAIN_FINGER_BASES.items():
        yaw = FINGER_YAW_DEGREES[finger_name]
        lengths = MAIN_LINK_LENGTHS[finger_name]
        flex_angles = MAIN_FINGER_FLEX[finger_name]
        joint = base

        for joint_index, (length, flex_angle) in enumerate(zip(lengths, flex_angles), start=1):
            parts.extend(_make_hinge_pin(f"{finger_name}_joint_{joint_index}", joint, yaw))
            parts.append(
                _make_mechanical_link(
                    f"{finger_name}_phalange_{joint_index}_length_{length:.0f}mm",
                    length,
                    joint,
                    flex_angle,
                    yaw,
                )
            )
            joint = _segment_end(joint, length, flex_angle, yaw)

        parts.append(_make_fingertip_pad(finger_name, joint, flex_angles[-1], yaw))

    parts.append(_make_thumb_saddle())
    thumb_joint = THUMB_BASE
    for joint_index, (length, flex_angle, yaw) in enumerate(
        zip(THUMB_LINK_LENGTHS, THUMB_FLEX, THUMB_YAWS),
        start=1,
    ):
        parts.extend(_make_hinge_pin(f"thumb_joint_{joint_index}", thumb_joint, yaw))
        parts.append(
            _make_mechanical_link(
                f"thumb_phalange_{joint_index}_length_{length:.0f}mm",
                length,
                thumb_joint,
                flex_angle,
                yaw,
            )
        )
        thumb_joint = _segment_end(thumb_joint, length, flex_angle, yaw)

    parts.append(_make_fingertip_pad("thumb", thumb_joint, THUMB_FLEX[-1], THUMB_YAWS[-1]))
    return parts


def _tube_profile_plane(start: tuple[float, float, float], next_point: tuple[float, float, float]) -> Plane:
    tangent = (
        next_point[0] - start[0],
        next_point[1] - start[1],
        next_point[2] - start[2],
    )
    return Plane(origin=start, x_dir=(1.0, 0.0, 0.0), z_dir=tangent)


def _make_tendon_tube(label: str, points: list[tuple[float, float, float]]):
    path = Edge.make_spline(points)
    with BuildPart() as tube:
        with BuildSketch(_tube_profile_plane(points[0], points[1])):
            Circle(1.0)
        sweep(path=path, is_frenet=True)
        _safe_fillet(tube.edges(), 0.2)
    return _set_metadata(tube.part, f"matte_black_tendon_tube_{label}_diameter_2mm", MATTE_BLACK)


def _make_servos_and_tendons():
    parts = []
    servo_centers = {
        "thumb": (-24.0, -15.0, PALM_TOP_Z + 5.0),
        "index": (-12.0, -13.0, PALM_TOP_Z + 5.0),
        "middle": (0.0, -15.5, PALM_TOP_Z + 5.0),
        "ring": (12.0, -13.0, PALM_TOP_Z + 5.0),
        "little": (24.0, -15.0, PALM_TOP_Z + 5.0),
    }

    for index, (label, center) in enumerate(servo_centers.items()):
        parts.extend(_make_servo_housing(label, center, BLUE_ACCENT if index % 2 else AMBER_ACCENT))

    tendon_targets = {
        "thumb": THUMB_BASE,
        "index": MAIN_FINGER_BASES["index"],
        "middle": MAIN_FINGER_BASES["middle"],
        "ring": MAIN_FINGER_BASES["ring"],
        "little": MAIN_FINGER_BASES["little"],
    }
    for label, start_center in servo_centers.items():
        target = tendon_targets[label]
        start = (start_center[0], start_center[1] + 9.0, start_center[2] + 3.7)
        if label == "thumb":
            points = [
                start,
                (-36.0, -11.0, PALM_TOP_Z + 14.0),
                (-43.5, -3.0, PALM_TOP_Z + 8.0),
                (target[0], target[1], target[2] + 1.0),
            ]
        else:
            points = [
                start,
                (start[0] * 0.75, 7.0, PALM_TOP_Z + 14.0),
                (target[0] * 0.96, 22.0, PALM_TOP_Z + 8.5),
                (target[0], target[1] - 1.5, target[2] + 0.6),
            ]
        parts.append(_make_tendon_tube(label, points))

    return parts


def _make_knuckle_yokes():
    parts = []
    for name, center in MAIN_FINGER_BASES.items():
        with BuildPart() as yoke:
            Box(12.0, 7.0, 7.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
            Cylinder(
                radius=4.25,
                height=13.0,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                rotation=(0.0, 90.0, FINGER_YAW_DEGREES[name]),
                mode=Mode.SUBTRACT,
            )
            _safe_fillet(yoke.edges(), 0.8)
        part = yoke.part.moved(Location((center[0], center[1] - 2.5, center[2] - 0.6)))
        parts.append(_set_metadata(part, f"brushed_aluminum_{name}_base_knuckle_yoke", BRUSHED_ALUMINUM))

    return parts


def _make_decorative_hex_fasteners():
    parts = []
    for index, (x_pos, y_pos, z_pos) in enumerate(
        [
            (-48.0, -36.0, DISPLAY_BASE_TOP_Z + 0.45),
            (48.0, -36.0, DISPLAY_BASE_TOP_Z + 0.45),
            (-48.0, 26.0, DISPLAY_BASE_TOP_Z + 0.45),
            (48.0, 26.0, DISPLAY_BASE_TOP_Z + 0.45),
        ],
        start=1,
    ):
        with BuildPart() as fastener:
            with BuildSketch(Plane.XY):
                RegularPolygon(3.2, 6, rotation=30.0)
            extrude(amount=0.9)
            _safe_fillet(fastener.edges(), 0.25)
        part = fastener.part.moved(Location((x_pos, y_pos, z_pos)))
        parts.append(_set_metadata(part, f"polished_steel_display_base_hex_fastener_{index:02d}", POLISHED_STEEL))
    return parts


def gen_step():
    """Return a labeled cybernetic robotic hand end-effector STEP assembly."""
    parts = [
        _make_display_base(),
        _make_support_post(),
        _make_palm_frame(),
        *_make_palm_ribs(),
        *_make_palm_fasteners(),
        *_make_wrist_gimbal(),
        *_make_knuckle_yokes(),
        *_make_fingers(),
        *_make_servos_and_tendons(),
        *_make_decorative_hex_fasteners(),
    ]

    assembly = Compound(
        obj=parts,
        children=parts,
        label="articulated_cybernetic_robotic_hand_end_effector",
    )
    return assembly
