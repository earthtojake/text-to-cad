from build123d import (
    Axis,
    BuildLine,
    BuildSketch,
    Box,
    Compound,
    Cylinder,
    Plane,
    RectangleRounded,
    Spline,
    Sphere,
    extrude,
    fillet,
    make_face,
    offset,
    scale,
)

CASE_WIDTH = 84.0
CASE_HEIGHT = 86.0
TOTAL_DEPTH = 24.7

# Enclosure-local frame before viewer translation:
# X: left (-) to right (+)
# Y: bottom (-) to top (+)
# Z: back (0) to front (TOTAL_DEPTH)
LEFT_X = -(CASE_WIDTH / 2.0)
RIGHT_X = CASE_WIDTH / 2.0
BOTTOM_Y = -(CASE_HEIGHT / 2.0)
TOP_Y = CASE_HEIGHT / 2.0
BACK_Z = 0.0
FRONT_Z = TOTAL_DEPTH

BODY_PLAN_RADIUS = 18.2
BODY_TAPER_DEGREES = 0.0
BODY_FACE_BLEND_RADIUS = 10.6

SCREEN_WIDTH = 48.5
SCREEN_HEIGHT = 17.8
SCREEN_FRONT_U = 0.5
SCREEN_FRONT_V = 0.75
SCREEN_RECESS_DEPTH = 2.4
SCREEN_RIM_FILLET = 0.6

SEAM_Y = 0.0
SHELL_SPLIT_Y = SEAM_Y
SHELL_SPLIT_GAP = 0.2
SHELL_SPLIT_CUTTER_SIZE = 200.0
SHELL_WALL_THICKNESS = 1.6

LIGHT_WIDTH = 22.0
LIGHT_HEIGHT = 2.4
LIGHT_RADIUS = 1.0
LIGHT_FRONT_U = 0.5
LIGHT_FRONT_V = 0.1775
LIGHT_RECESS_DEPTH = 0.9
LIGHT_FRONT_Z_OFFSET = -(LIGHT_RECESS_DEPTH + 0.2)

LOGO_FRONT_U = 0.5
LOGO_FRONT_V = 0.405
LOGO_FRONT_Z_OFFSET = -0.65
LOGO_ENGRAVE_DEPTH = 0.75
LOGO_SCALE = 0.88
LOGO_STROKE_WIDTH = 1.45
LOGO_EPSILON_CENTER_X = -9.3
LOGO_I_CENTER_X = 0.1
LOGO_THREE_CENTER_X = 9.2
LOGO_I_HEIGHT = 9.0
LOGO_BAR_WIDTH = 4.2
LOGO_BAR_HEIGHT = 1.1
LOGO_BAR_RADIUS = 0.45
LOGO_BAR_OFFSET_X = 0.3
LOGO_BAR_OFFSET_Y = 7.0

BUTTON_WIDTH = 3.2
BUTTON_HEIGHT = 7.6
BUTTON_RADIUS = 1.2
BUTTON_FACE_DEPTH = 0.78
BUTTON_STEM_DEPTH = 0.3
BUTTON_STEM_WIDTH = 2.55
BUTTON_STEM_HEIGHT = 6.95
BUTTON_STEM_RADIUS = 0.9
BUTTON_POCKET_WIDTH = 3.55
BUTTON_POCKET_HEIGHT = 7.95
BUTTON_POCKET_RADIUS = 1.28
BUTTON_POCKET_DEPTH = 0.52
BUTTON_DOME_DEPTH = 1.45
BUTTON_TEXTURE_WIDTH = 0.32
BUTTON_TEXTURE_DEPTH = 0.08
BUTTON_TEXTURE_X_OFFSETS = (-0.58, 0.0, 0.58)
BUTTON_RIGHT_W = 0.502
BUTTON_TOP_RIGHT_V = 0.6625
BUTTON_MID_RIGHT_V = 0.525
BUTTON_BOTTOM_RIGHT_V = 0.3375
BUTTON_RIGHT_X_OFFSET = -0.8

BACK_PUCK_STEM_RADIUS = 6.6
BACK_PUCK_STEM_DEPTH = 3.3
BACK_PUCK_CAP_RADIUS = 9.4
BACK_PUCK_CAP_DEPTH = 1.8
BACK_PUCK_BACK_U = 0.5
BACK_PUCK_BACK_V = 0.5
BACK_PUCK_BACK_Z_OFFSET = 0.0

TOP_SLIDER_WIDTH = 10.0
TOP_SLIDER_HEIGHT = 3.4
TOP_SLIDER_RADIUS = 1.6
TOP_SLIDER_DEPTH = 0.9
TOP_SLIDER_TOP_U = 0.5
TOP_SLIDER_TOP_W = 0.498
TOP_SLIDER_TOP_Y_OFFSET = -0.2

BOTTOM_PORT_RECESS_WIDTH = 12.6
BOTTOM_PORT_RECESS_HEIGHT = 5.2
BOTTOM_PORT_RECESS_RADIUS = 2.0
BOTTOM_PORT_RECESS_DEPTH = 1.4
BOTTOM_PORT_WIDTH = 9.4
BOTTOM_PORT_HEIGHT = 3.4
BOTTOM_PORT_RADIUS = 1.45
BOTTOM_PORT_DEPTH = 4.0
BOTTOM_PORT_BOTTOM_U = 0.404762
BOTTOM_PORT_BOTTOM_W = 0.575
BOTTOM_PORT_BOTTOM_Y_OFFSET = 0.0

BOTTOM_PINHOLE_RADIUS = 0.45
BOTTOM_PINHOLE_DEPTH = 1.2
BOTTOM_PINHOLE_BOTTOM_U = 0.632353
BOTTOM_PINHOLE_BOTTOM_W = 0.486
BOTTOM_PINHOLE_BOTTOM_Y_OFFSET = 0.0

SPEAKER_HOLE_RADIUS = 0.45
SPEAKER_HOLE_DEPTH = 1.1
SPEAKER_ROW_SPACING = 1.95
SPEAKER_COL_SPACING = 1.95
SPEAKER_BACK_U = 0.5
SPEAKER_BACK_V = 0.19375
SPEAKER_BACK_Z_OFFSET = 0.5
SPEAKER_ROWS = [4, 5, 6, 5, 4]

PCB_WIDTH = 60.0
PCB_HEIGHT = 50.0
PCB_THICKNESS = 1.4
PCB_CASE_CENTER_X = 0.0
PCB_CASE_CENTER_Y = -16.0
PCB_CASE_CENTER_Z = 12.0
PCB_MOUNT_HOLE_DIAMETER = 2.2
PCB_MOUNT_HOLES = (
    (-28.0, 23.0),
    (28.0, 23.0),
    (-28.0, -23.0),
    (28.0, -23.0),
)
PCB_BOSS_MOUNT_HOLES = (
    (-28.0, 23.0),
    (28.0, 23.0),
    (-28.0, -23.0),
    (28.0, -23.0),
)
PCB_BOSS_OUTER_RADIUS = 2.2
PCB_BOSS_HOLE_RADIUS = 1.15
PCB_BOSS_BACK_CLEARANCE = 0.15
PCB_LOWER_BOSS_PAD_WIDTH = 7.2
PCB_LOWER_BOSS_PAD_HEIGHT = 13.2
PCB_LOWER_BOSS_PAD_RADIUS = 2.0
PCB_LOWER_BOSS_PAD_Y_OFFSET = 3.6
CASE_FRONT_BACK_SPLIT_Z = TOTAL_DEPTH / 2.0
CASE_FRONT_BACK_SPLIT_GAP = 1.0
SHELL_ALIGNMENT_POINTS = (
    (-22.0, 20.0),
    (22.0, 20.0),
    (-22.0, -20.0),
    (22.0, -20.0),
)
SHELL_ALIGNMENT_PIN_RADIUS = 0.7
SHELL_ALIGNMENT_SOCKET_RADIUS = 0.9
SHELL_ALIGNMENT_DEPTH = 1.4

VIEWER_TRANSLATION = (0, CASE_HEIGHT / 2.0, -(TOTAL_DEPTH / 2.0))
EXPLODED_BUTTON_OFFSET_X = 10.0
EXPLODED_BACK_PUCK_OFFSET_Z = -12.0


def rounded_plate(width: float, height: float, radius: float, depth: float):
    with BuildSketch(Plane.XY) as sketch:
        RectangleRounded(width, height, radius)
    return extrude(sketch.sketch, amount=depth)


def stadium_plate(width: float, height: float, depth: float):
    return rounded_plate(width, height, (height / 2.0) - 0.1, depth)


def span_point(start: float, end: float, ratio: float) -> float:
    return start + ((end - start) * ratio)


def front_anchor(u: float, v: float, z_offset: float = 0.0) -> tuple[float, float, float]:
    return (
        span_point(LEFT_X, RIGHT_X, u),
        span_point(BOTTOM_Y, TOP_Y, v),
        FRONT_Z + z_offset,
    )


def back_anchor(u: float, v: float, z_offset: float = 0.0) -> tuple[float, float, float]:
    return (
        span_point(LEFT_X, RIGHT_X, u),
        span_point(BOTTOM_Y, TOP_Y, v),
        BACK_Z + z_offset,
    )


def right_anchor(v: float, w: float, x_offset: float = 0.0) -> tuple[float, float, float]:
    return (
        RIGHT_X + x_offset,
        span_point(BOTTOM_Y, TOP_Y, v),
        span_point(BACK_Z, FRONT_Z, w),
    )


def top_anchor(u: float, w: float, y_offset: float = 0.0) -> tuple[float, float, float]:
    return (
        span_point(LEFT_X, RIGHT_X, u),
        TOP_Y + y_offset,
        span_point(BACK_Z, FRONT_Z, w),
    )


def bottom_anchor(u: float, w: float, y_offset: float = 0.0) -> tuple[float, float, float]:
    return (
        span_point(LEFT_X, RIGHT_X, u),
        BOTTOM_Y + y_offset,
        span_point(BACK_Z, FRONT_Z, w),
    )


def stroked_spline(points: list[tuple[float, float]], stroke_width: float, depth: float):
    with BuildLine() as centerline:
        Spline(*points)
    outline = offset(centerline.line, amount=stroke_width / 2.0)
    return extrude(make_face(outline.edges()), amount=depth)


def logo_shape(depth: float):
    three = stroked_spline(
        [
            (-3.2, 4.4),
            (-0.8, 5.9),
            (2.8, 4.6),
            (1.7, 1.6),
            (-0.7, 0.5),
            (1.2, -0.1),
            (3.3, -1.6),
            (2.4, -4.6),
            (-1.2, -4.8),
        ],
        LOGO_STROKE_WIDTH,
        depth,
    ).translate((LOGO_THREE_CENTER_X, 0, 0))
    epsilon = stroked_spline(
        [
            (2.9, 4.2),
            (0.7, 5.5),
            (-2.5, 4.3),
            (-3.9, 1.7),
            (-1.1, 0.8),
            (-3.3, 0.3),
            (-4.4, -2.5),
            (-2.1, -4.7),
            (1.6, -3.5),
        ],
        LOGO_STROKE_WIDTH,
        depth,
    ).translate((LOGO_EPSILON_CENTER_X, 0, 0))
    i_body = stroked_spline(
        [
            (-0.25, -4.7),
            (-0.15, -1.4),
            (0.05, 2.0),
            (0.35, 4.7),
        ],
        LOGO_STROKE_WIDTH * 0.9,
        depth,
    ).translate((LOGO_I_CENTER_X, -0.2, 0))
    bar = rounded_plate(
        LOGO_BAR_WIDTH,
        LOGO_BAR_HEIGHT,
        LOGO_BAR_RADIUS,
        depth,
    ).translate((LOGO_BAR_OFFSET_X, LOGO_BAR_OFFSET_Y, 0))
    return scale(Compound([epsilon, i_body, three, bar]), by=(LOGO_SCALE, LOGO_SCALE, 1.0))


def select_screen_rim_edges(shape):
    screen_x, screen_y, _ = front_anchor(SCREEN_FRONT_U, SCREEN_FRONT_V)
    edges = []
    x_min = screen_x - (SCREEN_WIDTH / 2.0) - 0.8
    x_max = screen_x + (SCREEN_WIDTH / 2.0) + 0.8
    y_min = screen_y - (SCREEN_HEIGHT / 2.0) - 0.8
    y_max = screen_y + (SCREEN_HEIGHT / 2.0) + 0.8
    z_min = FRONT_Z - 0.45

    for edge in shape.edges():
        bounds = edge.bounding_box()
        if (
            bounds.min.X >= x_min
            and bounds.max.X <= x_max
            and bounds.min.Y >= y_min
            and bounds.max.Y <= y_max
            and bounds.max.Z > z_min
        ):
            edges.append(edge)
    return edges


def select_cap_edges(shape, lower_z: float, upper_z: float):
    edges = []
    tolerance = 0.05

    for edge in shape.edges():
        bounds = edge.bounding_box()
        size = bounds.size
        if size.Z > tolerance:
            continue
        if bounds.max.Z <= lower_z + tolerance or bounds.min.Z >= upper_z - tolerance:
            edges.append(edge)

    return edges


def rounded_shell_body(
    width: float,
    height: float,
    depth: float,
    plan_radius: float,
    face_blend_radius: float,
    z_offset: float = 0.0,
):
    with BuildSketch(Plane.XY.offset(z_offset + (depth / 2.0))) as profile:
        RectangleRounded(width, height, plan_radius)
    body = extrude(
        profile.sketch,
        amount=depth / 2.0,
        both=True,
        taper=BODY_TAPER_DEGREES,
    )
    return fillet(select_cap_edges(body, z_offset, z_offset + depth), face_blend_radius)


def enclosure_body():
    return rounded_shell_body(
        CASE_WIDTH,
        CASE_HEIGHT,
        TOTAL_DEPTH,
        BODY_PLAN_RADIUS,
        BODY_FACE_BLEND_RADIUS,
    )


def inner_dimension(value: float):
    return max(value - (SHELL_WALL_THICKNESS * 2.0), 1.0)


def inner_radius(radius: float):
    return max(radius - SHELL_WALL_THICKNESS, 0.5)


def inner_enclosure_body():
    inner_depth = max(TOTAL_DEPTH - (SHELL_WALL_THICKNESS * 2.0), 1.0)
    return rounded_shell_body(
        inner_dimension(CASE_WIDTH),
        inner_dimension(CASE_HEIGHT),
        inner_depth,
        inner_radius(BODY_PLAN_RADIUS),
        max(BODY_FACE_BLEND_RADIUS - SHELL_WALL_THICKNESS, 0.5),
        SHELL_WALL_THICKNESS,
    )


def inner_cavity_prism(z_offset: float, depth: float):
    with BuildSketch(Plane.XY.offset(z_offset + (depth / 2.0))) as profile:
        RectangleRounded(
            inner_dimension(CASE_WIDTH),
            inner_dimension(CASE_HEIGHT),
            inner_radius(BODY_PLAN_RADIUS),
        )
    return extrude(profile.sketch, amount=depth / 2.0, both=True)


def button_blank():
    stem = rounded_plate(
        BUTTON_STEM_WIDTH,
        BUTTON_STEM_HEIGHT,
        BUTTON_STEM_RADIUS,
        BUTTON_STEM_DEPTH,
    )
    dome = rounded_shell_body(
        BUTTON_WIDTH,
        BUTTON_HEIGHT,
        BUTTON_DOME_DEPTH,
        BUTTON_RADIUS,
        min(BUTTON_DOME_DEPTH * 0.42, BUTTON_RADIUS - 0.05),
        z_offset=BUTTON_STEM_DEPTH,
    )
    return (stem + dome).rotate(Axis.Z, 90).rotate(Axis.Y, 90)


def button_pocket(right_v: float):
    return rounded_plate(
        BUTTON_POCKET_WIDTH,
        BUTTON_POCKET_HEIGHT,
        BUTTON_POCKET_RADIUS,
        BUTTON_POCKET_DEPTH,
    ).rotate(Axis.Z, 90).rotate(Axis.Y, 90).translate(
        right_anchor(right_v, BUTTON_RIGHT_W, x_offset=BUTTON_RIGHT_X_OFFSET)
    )


def side_button(right_v: float):
    return button_blank().translate(
        right_anchor(right_v, BUTTON_RIGHT_W, x_offset=BUTTON_RIGHT_X_OFFSET)
    )


def back_puck():
    stem = Cylinder(BACK_PUCK_STEM_RADIUS, BACK_PUCK_STEM_DEPTH).translate(
        (0, 0, -(BACK_PUCK_STEM_DEPTH / 2.0) + 0.1)
    )
    cap = Cylinder(BACK_PUCK_CAP_RADIUS, BACK_PUCK_CAP_DEPTH).translate(
        (0, 0, -BACK_PUCK_STEM_DEPTH - (BACK_PUCK_CAP_DEPTH / 2.0) + 0.2)
    )
    return stem + cap


def top_slider_cut():
    return rounded_plate(
        TOP_SLIDER_WIDTH,
        TOP_SLIDER_HEIGHT,
        TOP_SLIDER_RADIUS,
        TOP_SLIDER_DEPTH,
    ).rotate(Axis.X, -90).translate(
        top_anchor(TOP_SLIDER_TOP_U, TOP_SLIDER_TOP_W, y_offset=TOP_SLIDER_TOP_Y_OFFSET)
    )


def bottom_port_cut():
    recess = rounded_plate(
        BOTTOM_PORT_RECESS_WIDTH,
        BOTTOM_PORT_RECESS_HEIGHT,
        BOTTOM_PORT_RECESS_RADIUS,
        BOTTOM_PORT_RECESS_DEPTH,
    ).rotate(Axis.X, -90).translate(bottom_anchor(BOTTOM_PORT_BOTTOM_U, BOTTOM_PORT_BOTTOM_W, BOTTOM_PORT_BOTTOM_Y_OFFSET))
    opening = rounded_plate(
        BOTTOM_PORT_WIDTH,
        BOTTOM_PORT_HEIGHT,
        BOTTOM_PORT_RADIUS,
        BOTTOM_PORT_DEPTH,
    ).rotate(Axis.X, -90).translate(bottom_anchor(BOTTOM_PORT_BOTTOM_U, BOTTOM_PORT_BOTTOM_W, BOTTOM_PORT_BOTTOM_Y_OFFSET))
    return recess + opening


def pcb_case_position(board_x: float, board_y: float, board_z: float = 0.0) -> tuple[float, float, float]:
    return (
        PCB_CASE_CENTER_X + board_x,
        PCB_CASE_CENTER_Y + board_y,
        PCB_CASE_CENTER_Z + board_z,
    )


def pcb_mount_bosses_raw():
    boss_bottom_z = BACK_Z + SHELL_WALL_THICKNESS - PCB_BOSS_BACK_CLEARANCE
    boss_top_z = PCB_CASE_CENTER_Z - (PCB_THICKNESS / 2.0)
    boss_depth = boss_top_z - boss_bottom_z
    boss_clip = inner_cavity_prism(boss_bottom_z - 0.05, boss_depth + 0.1)
    bosses = []

    for hole_x, hole_y in PCB_BOSS_MOUNT_HOLES:
        if hole_y < 0:
            boss = rounded_plate(
                PCB_LOWER_BOSS_PAD_WIDTH,
                PCB_LOWER_BOSS_PAD_HEIGHT,
                PCB_LOWER_BOSS_PAD_RADIUS,
                boss_depth,
            ).translate(
                (
                    PCB_CASE_CENTER_X + hole_x,
                    PCB_CASE_CENTER_Y + hole_y + PCB_LOWER_BOSS_PAD_Y_OFFSET,
                    boss_bottom_z,
                )
            )
        else:
            boss = Cylinder(PCB_BOSS_OUTER_RADIUS, boss_depth).translate(
                pcb_case_position(hole_x, hole_y, (boss_bottom_z + boss_top_z) / 2.0 - PCB_CASE_CENTER_Z)
            )
        screw_clearance = Cylinder(PCB_BOSS_HOLE_RADIUS, boss_depth + 0.4).translate(
            pcb_case_position(hole_x, hole_y, (boss_bottom_z + boss_top_z) / 2.0 - PCB_CASE_CENTER_Z)
        )
        bosses.append((boss & boss_clip) - screw_clearance)

    return Compound(bosses)


def shell_back_alignment_pins_raw():
    split_z = CASE_FRONT_BACK_SPLIT_Z - (CASE_FRONT_BACK_SPLIT_GAP / 2.0)
    pins = []

    for point_x, point_y in SHELL_ALIGNMENT_POINTS:
        pins.append(
            Cylinder(SHELL_ALIGNMENT_PIN_RADIUS, SHELL_ALIGNMENT_DEPTH).translate(
                (point_x, point_y, split_z + (SHELL_ALIGNMENT_DEPTH / 2.0))
            )
        )

    return Compound(pins)


def shell_front_alignment_sockets_raw():
    split_z = CASE_FRONT_BACK_SPLIT_Z + (CASE_FRONT_BACK_SPLIT_GAP / 2.0)
    sockets = []

    for point_x, point_y in SHELL_ALIGNMENT_POINTS:
        sockets.append(
            Cylinder(SHELL_ALIGNMENT_SOCKET_RADIUS, SHELL_ALIGNMENT_DEPTH + 0.4).translate(
                (point_x, point_y, split_z + ((SHELL_ALIGNMENT_DEPTH + 0.4) / 2.0) - 0.1)
            )
        )

    return Compound(sockets)


def as_compound(shape):
    if hasattr(shape, "wrapped"):
        return shape
    return Compound(list(shape))


def bottom_pinhole_cut():
    return Cylinder(BOTTOM_PINHOLE_RADIUS, BOTTOM_PINHOLE_DEPTH).rotate(Axis.X, -90).translate(
        bottom_anchor(BOTTOM_PINHOLE_BOTTOM_U, BOTTOM_PINHOLE_BOTTOM_W, BOTTOM_PINHOLE_BOTTOM_Y_OFFSET)
    )


def speaker_hole_positions():
    positions = []
    row_count = len(SPEAKER_ROWS)
    row_origin = -((row_count - 1) * SPEAKER_ROW_SPACING / 2.0)
    speaker_x, speaker_y, _ = back_anchor(SPEAKER_BACK_U, SPEAKER_BACK_V)
    for row_index, hole_count in enumerate(SPEAKER_ROWS):
        row_y = speaker_y + row_origin + (row_index * SPEAKER_ROW_SPACING)
        col_origin = -((hole_count - 1) * SPEAKER_COL_SPACING / 2.0)
        for column_index in range(hole_count):
            positions.append((speaker_x + col_origin + (column_index * SPEAKER_COL_SPACING), row_y))
    return positions


def apply_speaker_holes(shape):
    result = shape
    speaker_origin = back_anchor(SPEAKER_BACK_U, SPEAKER_BACK_V, z_offset=SPEAKER_BACK_Z_OFFSET)
    speaker_anchor_x = span_point(LEFT_X, RIGHT_X, SPEAKER_BACK_U)
    speaker_anchor_y = span_point(BOTTOM_Y, TOP_Y, SPEAKER_BACK_V)
    for center_x, center_y in speaker_hole_positions():
        hole = Cylinder(SPEAKER_HOLE_RADIUS, SPEAKER_HOLE_DEPTH).translate(speaker_origin)
        hole = hole.translate((center_x - speaker_anchor_x, center_y - speaker_anchor_y, 0))
        result = result - hole
    return result


def shell_raw():
    body = enclosure_body()
    body = body - top_slider_cut()
    body = body - bottom_port_cut()
    body = body - bottom_pinhole_cut()
    body = apply_speaker_holes(body)
    body = body - button_pocket(BUTTON_TOP_RIGHT_V)
    body = body - button_pocket(BUTTON_MID_RIGHT_V)
    body = body - button_pocket(BUTTON_BOTTOM_RIGHT_V)

    screen_cut = stadium_plate(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_RECESS_DEPTH).translate(
        front_anchor(SCREEN_FRONT_U, SCREEN_FRONT_V, z_offset=-SCREEN_RECESS_DEPTH)
    )
    body = body - screen_cut
    screen_edges = select_screen_rim_edges(body)
    if screen_edges:
        try:
            body = fillet(screen_edges, SCREEN_RIM_FILLET)
        except ValueError:
            pass

    light_cut = rounded_plate(LIGHT_WIDTH, LIGHT_HEIGHT, LIGHT_RADIUS, LIGHT_RECESS_DEPTH).translate(
        front_anchor(LIGHT_FRONT_U, LIGHT_FRONT_V, z_offset=LIGHT_FRONT_Z_OFFSET)
    )
    body = body - light_cut

    logo_cut = logo_shape(LOGO_ENGRAVE_DEPTH).translate(
        front_anchor(LOGO_FRONT_U, LOGO_FRONT_V, z_offset=LOGO_FRONT_Z_OFFSET)
    )
    return body - logo_cut


def visual_shell_raw():
    return shell_raw()


def front_logo_raw():
    return logo_shape(LOGO_ENGRAVE_DEPTH).translate(front_anchor(LOGO_FRONT_U, LOGO_FRONT_V, z_offset=LOGO_FRONT_Z_OFFSET))


def split_shell_raw():
    outer_shell = shell_raw()
    inner_shell = inner_enclosure_body()
    boss_set = pcb_mount_bosses_raw()
    top_cutter = Box(
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
    ).translate(
        (
            0,
            SHELL_SPLIT_Y + (SHELL_SPLIT_GAP / 2.0) + (SHELL_SPLIT_CUTTER_SIZE / 2.0),
            0,
        )
    )
    bottom_cutter = Box(
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
    ).translate(
        (
            0,
            SHELL_SPLIT_Y - (SHELL_SPLIT_GAP / 2.0) - (SHELL_SPLIT_CUTTER_SIZE / 2.0),
            0,
        )
    )
    bottom_half = ((outer_shell & bottom_cutter) - (inner_shell & bottom_cutter)) + (boss_set & bottom_cutter)
    top_half = ((outer_shell & top_cutter) - (inner_shell & top_cutter)) + (boss_set & top_cutter)
    return Compound([bottom_half, top_half])


def front_back_shell_halves_raw():
    outer_shell = shell_raw()
    inner_shell = inner_enclosure_body()
    boss_set = pcb_mount_bosses_raw()

    back_cutter = Box(
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
    ).translate(
        (
            0,
            0,
            CASE_FRONT_BACK_SPLIT_Z - (CASE_FRONT_BACK_SPLIT_GAP / 2.0) - (SHELL_SPLIT_CUTTER_SIZE / 2.0),
        )
    )
    front_cutter = Box(
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
        SHELL_SPLIT_CUTTER_SIZE,
    ).translate(
        (
            0,
            0,
            CASE_FRONT_BACK_SPLIT_Z + (CASE_FRONT_BACK_SPLIT_GAP / 2.0) + (SHELL_SPLIT_CUTTER_SIZE / 2.0),
        )
    )
    back_half = ((outer_shell & back_cutter) - (inner_shell & back_cutter)) + (boss_set & back_cutter)
    back_half = as_compound(back_half)
    front_half = (outer_shell & front_cutter) - (inner_shell & front_cutter)
    front_half = as_compound(front_half)
    return as_compound(back_half), as_compound(front_half)


def split_shell_front_back_raw(exploded: bool = False):
    back_half, front_half = front_back_shell_halves_raw()

    if exploded:
        return Compound(
            [
                back_half.translate((0, 0, -4.0)),
                front_half.translate((0, 0, 8.0)),
            ]
        )
    return Compound([back_half, front_half])


def viewer_aligned(shape):
    return shape.translate(VIEWER_TRANSLATION)


def shell_shape():
    return viewer_aligned(split_shell_front_back_raw())


def shell_front_back_shape(exploded: bool = False):
    return viewer_aligned(split_shell_front_back_raw(exploded=exploded))


def visual_shell_shape():
    return viewer_aligned(visual_shell_raw())


def back_puck_shape():
    return viewer_aligned(back_puck().translate(back_anchor(BACK_PUCK_BACK_U, BACK_PUCK_BACK_V, z_offset=BACK_PUCK_BACK_Z_OFFSET)))


def top_button_shape():
    return viewer_aligned(side_button(BUTTON_TOP_RIGHT_V))


def mid_button_shape():
    return viewer_aligned(side_button(BUTTON_MID_RIGHT_V))


def bottom_button_shape():
    return viewer_aligned(side_button(BUTTON_BOTTOM_RIGHT_V))


def front_logo_shape():
    return viewer_aligned(front_logo_raw())


def assembled_shape():
    return Compound(
        [
            visual_shell_shape(),
            back_puck_shape(),
            top_button_shape(),
            mid_button_shape(),
            bottom_button_shape(),
        ]
    )


def validate_assembled_bounds(shape) -> None:
    # Sanity-check: assembled silhouette should equal case envelope plus the
    # parts that protrude past it (back puck behind, side buttons on +X).
    size = shape.bounding_box().size
    # Back puck embeds 0.2mm into the case and protrudes (stem+cap-0.2) behind it.
    back_puck_overhang = (BACK_PUCK_STEM_DEPTH + BACK_PUCK_CAP_DEPTH) - 0.2
    # Side buttons sit at RIGHT_X + BUTTON_RIGHT_X_OFFSET (X_OFFSET is negative,
    # pulling the button base inward). The dome+stem protrude outward; only the
    # part beyond RIGHT_X counts toward the X envelope.
    button_overhang = BUTTON_DOME_DEPTH + BUTTON_STEM_DEPTH - abs(BUTTON_RIGHT_X_OFFSET)
    expected_x = CASE_WIDTH + button_overhang
    expected_y = CASE_HEIGHT
    expected_z = TOTAL_DEPTH + back_puck_overhang
    actual = (round(size.X, 3), round(size.Y, 3), round(size.Z, 3))
    expected = (round(expected_x, 3), round(expected_y, 3), round(expected_z, 3))
    tolerance = 0.6
    if any(abs(a - e) > tolerance for a, e in zip(actual, expected)):
        raise ValueError(
            f"Unexpected mimo case bounds: actual={actual} expected≈{expected} "
            f"(derived from CASE_WIDTH/HEIGHT, TOTAL_DEPTH, BACK_PUCK_*, BUTTON_*; "
            f"tolerance={tolerance}mm). If you intentionally changed dimensions, "
            f"update the derivation, not the expected tuple."
        )


def translation_matrix(x: float, y: float, z: float) -> list[float]:
    return [
        1.0,
        0.0,
        0.0,
        x,
        0.0,
        1.0,
        0.0,
        y,
        0.0,
        0.0,
        1.0,
        z,
        0.0,
        0.0,
        0.0,
        1.0,
    ]
