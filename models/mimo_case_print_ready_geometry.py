"""
Print-ready mimo case (clamshell, 3D-print-friendly).

COORDINATE CONVENTIONS — read this before adding features.

Source frame (the frame everything is built in, before `viewer_aligned`):
    +X  → screen-right when looking at the front face
    +Y  → screen-up (TOP_Y face is the top of the monitor; BOTTOM_Y is where USB-C lives)
    +Z  → out of the screen toward the user (FRONT_Z face has the screen recess; BACK_Z is the back of the monitor)

The viewer translates by (0, +CASE_HEIGHT/2, -TOTAL_DEPTH/2) and applies NO rotation,
so the source frame IS the world frame the user sees, just shifted to sit on a Y=0 floor.

GOTCHA — `Plane.XZ` normal direction:
    build123d's `Plane.XZ` has its normal pointing in the -Y direction. So
    `BuildSketch(Plane.XZ.offset(BOTTOM_Y - 0.05))` actually places the sketch at
    Y = -(BOTTOM_Y - 0.05) = +43.05 (the TOP face), and `extrude(amount=d)` pushes
    further in -Y. If you want a feature on the BOTTOM_Y face, build the plane
    explicitly:
        Plane(origin=(0, BOTTOM_Y - 0.05, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    Same trap exists for Plane.YZ (normal -X) and Plane.XY is +Z (the only "intuitive" one).

Where features should live (source coords):
    Screen recess     → +Z face (front), on the flat zone bounded by the body fillet
    USB-C cutout      → -Y face (bottom), aligned to PCB connector J1
    PCB               → cavity centered at (PCB_CASE_CENTER_X/Y/Z), with USB-C edge facing -Y
    Mounting standoffs → between back wall and PCB underside

If a feature lands on the wrong face, FIX THE SOURCE PLACEMENT, do not add a
compensating rotation downstream. (We had a bug like that — Z-180 rotation in
viewer_aligned was masking a sketch-plane sign error.)
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from build123d import (
    Axis,
    Box,
    BuildSketch,
    Compound,
    Cylinder,
    Plane,
    RectangleRounded,
    extrude,
    fillet,
)

from mimo_case_geometry import (
    rounded_shell_body,
    PCB_MOUNT_HOLE_DIAMETER,
    PCB_THICKNESS,
    PCB_WIDTH,
    PCB_HEIGHT,
)
from mimo_pcb_geometry import (
    load_board_metadata,
    pcb_component_center,
    pcb_component_size,
    pcb_components,
    pcb_front_sensor_cluster_bbox,
    pcb_holes,
    pcb_shape_raw,
    pcb_usb_c_opening_center,
)

# Print-ready enclosure mirrors the original mimo_case shell silhouette so the
# product keeps its rounded, near-square personality. The previous 94x86x26
# geometry with a 6mm face blend looked boxy.
CASE_WIDTH = 84.0
CASE_HEIGHT = 86.0
TOTAL_DEPTH = 24.7
FRONT_Z = TOTAL_DEPTH
LEFT_X = -(CASE_WIDTH / 2.0)
RIGHT_X = CASE_WIDTH / 2.0
BOTTOM_Y = -(CASE_HEIGHT / 2.0)
TOP_Y = CASE_HEIGHT / 2.0

BODY_PLAN_RADIUS = 18.2
BODY_FACE_BLEND_RADIUS = 10.0

VIEWER_TRANSLATION = (0.0, CASE_HEIGHT / 2.0, -(TOTAL_DEPTH / 2.0))

PCB_CASE_CENTER_X = 0.0
PCB_CASE_CENTER_Y = -14.0
PCB_CASE_CENTER_Z = 8.0


def viewer_aligned(shape):
    # Source frame already has USB-C on the BOTTOM_Y face and the screen on the
    # upper half of the front, so a straight translation gives the natural
    # upright orientation: screen toward the user, USB-C edge at the bottom.
    return shape.translate(VIEWER_TRANSLATION)


def _as_compound(shape):
    if hasattr(shape, "wrapped"):
        return shape
    return Compound(list(shape))


def _span_point(start: float, end: float, ratio: float) -> float:
    return start + ((end - start) * ratio)


def front_anchor(u: float, v: float, z_offset: float = 0.0) -> tuple[float, float, float]:
    return (
        _span_point(LEFT_X, RIGHT_X, u),
        _span_point(BOTTOM_Y, TOP_Y, v),
        FRONT_Z + z_offset,
    )


def pcb_case_position(board_x: float, board_y: float, board_z: float = 0.0) -> tuple[float, float, float]:
    return (
        PCB_CASE_CENTER_X + board_x,
        PCB_CASE_CENTER_Y + board_y,
        PCB_CASE_CENTER_Z + board_z,
    )


def pcb_in_case_raw():
    return pcb_shape_raw().translate((PCB_CASE_CENTER_X, PCB_CASE_CENTER_Y, PCB_CASE_CENTER_Z))


@dataclass(frozen=True)
class PrintReadyParams:
    wall: float = 1.6
    split_z: float = 14.6
    split_gap: float = 0.0
    seam_overlap: float = 2.4
    seam_root: float = 0.9
    seam_wall: float = 1.2
    seam_clearance: float = 0.2

    # Sensor window override knobs. When `screen_use_pcb_cluster=True` (default),
    # the through-cut and recess are sized and positioned from the PCB sensor
    # cluster bbox via `pcb_front_sensor_cluster_bbox()`. The hardcoded values
    # below are only used as a fallback / override when the flag is False.
    screen_use_pcb_cluster: bool = True
    screen_u: float = 0.5
    screen_v: float = 0.5
    screen_open_w: float = 56.0
    screen_open_h: float = 36.0
    screen_open_r: float = 8.0
    screen_recess_margin: float = 4.0
    screen_recess_depth: float = 1.8

    # Per-sensor sub-apertures inside the sensor window.
    pir_fresnel_diameter: float = 10.0  # Fresnel lens insert diameter for PIR
    pir_fresnel_depth_extra: float = 1.4  # extra recess past the screen recess for the lens dome

    usb_cut_w: float = 12.0
    usb_cut_h: float = 5.5
    usb_cut_r: float = 2.0
    usb_cut_depth: float = 7.1

    standoff_r: float = 3.3
    standoff_pilot_r: float = 0.85  # pilot for M2 thread-forming screws
    lower_rail_w: float = 66.0
    lower_rail_h: float = 11.5
    lower_rail_r: float = 3.0
    lower_rail_y_offset: float = 3.2

    snap_tab_w: float = 5.0
    snap_tab_x: float = 1.0
    snap_tab_z: float = 2.4
    snap_tab_clear: float = 0.35

    align_pin_r: float = 0.95
    align_pin_clear: float = 0.25
    align_pin_root: float = 1.2
    align_pin_insertion: float = 2.8


ALIGN_POINTS = (
    (-22.0, 20.0),
    (22.0, 20.0),
    (-22.0, -20.0),
    (22.0, -20.0),
)


def _inner_dimension(value: float, wall: float) -> float:
    return max(value - (wall * 2.0), 1.0)


def _inner_radius(radius: float, wall: float) -> float:
    return max(radius - wall, 0.5)


def enclosure_outer_raw():
    return rounded_shell_body(
        CASE_WIDTH,
        CASE_HEIGHT,
        TOTAL_DEPTH,
        BODY_PLAN_RADIUS,
        BODY_FACE_BLEND_RADIUS,
    )


def enclosure_inner_raw(*, wall: float):
    inner_depth = max(TOTAL_DEPTH - (wall * 2.0), 1.0)
    return rounded_shell_body(
        _inner_dimension(CASE_WIDTH, wall),
        _inner_dimension(CASE_HEIGHT, wall),
        inner_depth,
        _inner_radius(BODY_PLAN_RADIUS, wall),
        max(BODY_FACE_BLEND_RADIUS - wall, 0.5),
        z_offset=wall,
    )


def _stadium_plate(width: float, height: float, depth: float):
    radius = max((height / 2.0) - 0.15, 0.2)
    with BuildSketch(Plane.XY) as sketch:
        RectangleRounded(width, height, radius)
    return extrude(sketch.sketch, amount=depth)


def _window_plate(width: float, height: float, depth: float, radius: float):
    with BuildSketch(Plane.XY) as sketch:
        RectangleRounded(width, height, radius)
    return extrude(sketch.sketch, amount=depth)


def _usb_c_case_datum() -> tuple[float, float, float]:
    usb_x, usb_y, usb_z = pcb_usb_c_opening_center()
    return pcb_case_position(usb_x, usb_y, usb_z)


def _usb_c_cutout_raw(params: PrintReadyParams):
    usb_x, _, usb_z = _usb_c_case_datum()
    # Sketch on the BOTTOM_Y face (y = -case_height/2) with the plane normal
    # pointing into the case (+Y). Extruding `usb_cut_depth` along that normal
    # carves a slot that starts just outside BOTTOM_Y and bites into the cavity.
    plane = Plane(origin=(0, BOTTOM_Y - 0.05, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    with BuildSketch(plane) as sketch:
        RectangleRounded(params.usb_cut_w, params.usb_cut_h, params.usb_cut_r)
    return extrude(sketch.sketch, amount=params.usb_cut_depth).translate((usb_x, 0.0, usb_z))


def _flat_front_face_half_extents() -> tuple[float, float, float, float]:
    """Half-extents of the flat front-face zone (case planform inset by face fillet)."""
    half_w = (CASE_WIDTH / 2.0) - BODY_FACE_BLEND_RADIUS
    half_h = (CASE_HEIGHT / 2.0) - BODY_FACE_BLEND_RADIUS
    corner_r = max(BODY_PLAN_RADIUS - BODY_FACE_BLEND_RADIUS, 0.5)
    corner_center_x = half_w - corner_r
    corner_center_y = half_h - corner_r
    return half_w, half_h, corner_r, corner_center_x  # corner_center_y = corner_center_x in symmetric case


def sensor_window_geometry(
    params: PrintReadyParams,
) -> tuple[tuple[float, float], float, float, float]:
    """Return ((center_x, center_y), width, height, corner_radius) for the
    sensor-window through-cut on the front face, in case coords.

    When `params.screen_use_pcb_cluster` is True (default), pulls the sensor
    cluster bbox from PCB metadata and translates it into case coords so the
    case auto-adapts as the PCB layout evolves. Otherwise falls back to the
    fixed `screen_*` overrides on `params`.
    """
    if not params.screen_use_pcb_cluster:
        center_x, center_y, _ = front_anchor(params.screen_u, params.screen_v)
        return (
            (center_x, center_y),
            params.screen_open_w,
            params.screen_open_h,
            params.screen_open_r,
        )

    pcb_x_min, pcb_x_max, pcb_y_min, pcb_y_max = pcb_front_sensor_cluster_bbox(margin=2.0)
    case_x_min, case_y_min, _ = pcb_case_position(pcb_x_min, pcb_y_min)
    case_x_max, case_y_max, _ = pcb_case_position(pcb_x_max, pcb_y_max)
    center_x = (case_x_min + case_x_max) / 2.0
    center_y = (case_y_min + case_y_max) / 2.0
    width = case_x_max - case_x_min
    height = case_y_max - case_y_min

    # Clamp to fit within the flat front-face zone with a small safety margin.
    safety = 1.5
    half_w, half_h, corner_r, _ = _flat_front_face_half_extents()
    max_half_w = half_w - safety
    max_half_h = half_h - safety
    if (width / 2.0) > max_half_w:
        width = 2.0 * max_half_w
    if (height / 2.0) > max_half_h:
        height = 2.0 * max_half_h
    # Clamp center so the recess outline doesn't run off the flat zone.
    center_x = max(min(center_x, max_half_w - width / 2.0), -(max_half_w - width / 2.0))
    center_y = max(min(center_y, max_half_h - height / 2.0), -(max_half_h - height / 2.0))

    radius = min(params.screen_open_r, height / 2.0 - 0.1, width / 2.0 - 0.1)
    return ((center_x, center_y), width, height, radius)


def _screen_opening_cut_raw(
    params: PrintReadyParams,
    *,
    center_xy: tuple[float, float],
    width: float | None = None,
    height: float | None = None,
    radius: float | None = None,
):
    center_x, center_y = center_xy
    open_w = params.screen_open_w if width is None else width
    open_h = params.screen_open_h if height is None else height
    open_r = params.screen_open_r if radius is None else radius
    # Keep the through-cut mostly within the front half so we don't inadvertently
    # weaken or clip internal back-half features.
    front_half_depth = max(TOTAL_DEPTH - params.split_z, 1.0)
    cutter_depth = max(front_half_depth + params.seam_root + 0.6, params.wall + 0.8)
    opening = _window_plate(open_w, open_h, cutter_depth, open_r).translate(
        (center_x, center_y, FRONT_Z - cutter_depth + 0.05)
    )
    recess = _window_plate(
        open_w + params.screen_recess_margin,
        open_h + params.screen_recess_margin,
        params.screen_recess_depth,
        open_r + params.screen_recess_margin / 2.0,
    ).translate((center_x, center_y, FRONT_Z - params.screen_recess_depth + 0.02))
    return recess + opening


def _pir_fresnel_cutout_raw(params: PrintReadyParams):
    """Through-hole on the front face for the PIR Fresnel lens dome.

    Position is driven by PIR1's center on the PCB. Returns None if the PIR
    isn't tagged on the board yet.
    """
    pcb_xy = pcb_component_center("PIR1")
    if pcb_xy is None:
        return None
    case_x, case_y, _ = pcb_case_position(pcb_xy[0], pcb_xy[1])
    radius = params.pir_fresnel_diameter / 2.0
    front_half_depth = max(TOTAL_DEPTH - params.split_z, 1.0)
    cutter_depth = max(
        front_half_depth + params.seam_root + 0.6 + params.pir_fresnel_depth_extra,
        params.wall + 0.8,
    )
    return Cylinder(radius, cutter_depth).translate(
        (case_x, case_y, FRONT_Z - cutter_depth / 2.0 + 0.05)
    )


def pcb_mount_holes_from_metadata() -> list[tuple[float, float, float]]:
    data = load_board_metadata()
    holes: list[tuple[float, float, float]] = []
    for hole_x, hole_y, hole_diameter in pcb_holes(data):
        if abs(float(hole_diameter) - PCB_MOUNT_HOLE_DIAMETER) <= 1e-6:
            holes.append((float(hole_x), float(hole_y), float(hole_diameter)))
    holes.sort(key=lambda item: (item[1], item[0]))
    if len(holes) != 4:
        raise ValueError(f"Expected 4 PCB mount holes of Ø{PCB_MOUNT_HOLE_DIAMETER}mm, found {len(holes)}")
    return holes


def pcb_standoffs_raw(params: PrintReadyParams) -> Compound:
    boss_bottom_z = params.wall
    board_back_z = pcb_case_position(0.0, 0.0, -(PCB_THICKNESS / 2.0))[2]
    standoff_top_z = board_back_z - 0.02
    standoff_height = standoff_top_z - boss_bottom_z
    if standoff_height <= 0:
        raise ValueError(f"Invalid standoff height: {standoff_height}")

    with BuildSketch(Plane.XY.offset(boss_bottom_z + (standoff_height / 2.0))) as profile:
        RectangleRounded(
            _inner_dimension(CASE_WIDTH, params.wall),
            _inner_dimension(CASE_HEIGHT, params.wall),
            _inner_radius(BODY_PLAN_RADIUS, params.wall),
        )
    boss_clip = extrude(profile.sketch, amount=standoff_height / 2.0, both=True)

    standoffs = []
    lower_holes = []
    for hole_x, hole_y, _ in pcb_mount_holes_from_metadata():
        case_x, case_y, _ = pcb_case_position(hole_x, hole_y, 0.0)
        if hole_y < 0:
            lower_holes.append((case_x, case_y))
            continue
        standoff = Cylinder(params.standoff_r, standoff_height).translate(
            (case_x, case_y, boss_bottom_z + (standoff_height / 2.0))
        )
        standoff = standoff & boss_clip

        # Pilot hole for M2 thread-forming screws + short locating collar that
        # doesn't block the screw path.
        pilot_h = standoff_height + 1.2
        pilot = Cylinder(params.standoff_pilot_r, pilot_h).translate(
            (case_x, case_y, boss_bottom_z + (standoff_height / 2.0))
        )

        collar_outer_r = min((PCB_MOUNT_HOLE_DIAMETER / 2.0) - 0.10, params.standoff_r - 0.5)
        collar_outer_r = max(collar_outer_r, params.standoff_pilot_r + 0.2)
        collar_h = min(max(PCB_THICKNESS - 0.35, 0.6), 1.0)
        collar = (Cylinder(collar_outer_r, collar_h) - Cylinder(params.standoff_pilot_r, collar_h + 0.4)).translate(
            (case_x, case_y, standoff_top_z + (collar_h / 2.0) - 0.02)
        )

        standoffs.append((standoff - pilot) + collar)

    if len(lower_holes) != 2:
        raise ValueError(f"Expected 2 lower PCB holes, found {len(lower_holes)}")

    lower_y = sum(y for _, y in lower_holes) / len(lower_holes)
    rail_center_y = lower_y + params.lower_rail_y_offset
    lower_rail = _stadium_plate(params.lower_rail_w, params.lower_rail_h, standoff_height).translate(
        (0.0, rail_center_y, boss_bottom_z)
    )
    lower_rail = lower_rail & boss_clip
    for case_x, case_y in lower_holes:
        pilot_h = standoff_height + 1.2
        pilot = Cylinder(params.standoff_pilot_r, pilot_h).translate(
            (case_x, case_y, boss_bottom_z + (standoff_height / 2.0))
        )
        collar_outer_r = min((PCB_MOUNT_HOLE_DIAMETER / 2.0) - 0.10, params.standoff_r - 0.5)
        collar_h = min(max(PCB_THICKNESS - 0.35, 0.6), 1.0)
        collar = (Cylinder(collar_outer_r, collar_h) - Cylinder(params.standoff_pilot_r, collar_h + 0.4)).translate(
            (case_x, case_y, standoff_top_z + (collar_h / 2.0) - 0.02)
        )
        lower_rail = (lower_rail - pilot) + collar

    standoffs.append(lower_rail)
    return Compound(standoffs)


def seam_ring_raw(params: PrintReadyParams):
    inner_w = _inner_dimension(CASE_WIDTH, params.wall)
    inner_h = _inner_dimension(CASE_HEIGHT, params.wall)
    inner_r = _inner_radius(BODY_PLAN_RADIUS, params.wall)

    attach_overlap = 0.6
    outer_w = inner_w + attach_overlap
    outer_h = inner_h + attach_overlap
    outer_r = inner_r + (attach_overlap / 2.0)

    inner2_w = inner_w - (params.seam_wall * 2.0)
    inner2_h = inner_h - (params.seam_wall * 2.0)
    inner2_r = max(inner_r - params.seam_wall, 0.5)

    depth = params.seam_overlap + params.seam_root
    with BuildSketch(Plane.XY) as sketch_outer:
        RectangleRounded(outer_w, outer_h, outer_r)
    with BuildSketch(Plane.XY) as sketch_inner:
        RectangleRounded(inner2_w, inner2_h, inner2_r)
    ring = extrude(sketch_outer.sketch, amount=depth) - extrude(sketch_inner.sketch, amount=depth)
    return ring.translate((0.0, 0.0, params.split_z - params.seam_root))


def seam_groove_cut_raw(params: PrintReadyParams):
    inner_w = _inner_dimension(CASE_WIDTH, params.wall)
    inner_h = _inner_dimension(CASE_HEIGHT, params.wall)
    inner_r = _inner_radius(BODY_PLAN_RADIUS, params.wall)

    attach_overlap = 0.6
    clearance = 0.35
    outer_w = inner_w + attach_overlap + (clearance * 2.0)
    outer_h = inner_h + attach_overlap + (clearance * 2.0)
    outer_r = inner_r + (attach_overlap / 2.0) + clearance

    inner2_w = inner_w - (params.seam_wall * 2.0) - (clearance * 2.0)
    inner2_h = inner_h - (params.seam_wall * 2.0) - (clearance * 2.0)
    inner2_r = max(inner_r - params.seam_wall - clearance, 0.5)

    depth = params.seam_overlap + 0.7
    with BuildSketch(Plane.XY) as sketch_outer:
        RectangleRounded(outer_w, outer_h, outer_r)
    with BuildSketch(Plane.XY) as sketch_inner:
        RectangleRounded(inner2_w, inner2_h, inner2_r)
    groove = extrude(sketch_outer.sketch, amount=depth) - extrude(sketch_inner.sketch, amount=depth)
    return groove.translate((0.0, 0.0, params.split_z - 0.15))


def alignment_pins_raw(params: PrintReadyParams) -> Compound:
    pin_len = params.align_pin_root + params.align_pin_insertion
    z_center = (params.split_z - params.align_pin_root + params.split_z + params.align_pin_insertion) / 2.0
    pins = [Cylinder(params.align_pin_r, pin_len).translate((x, y, z_center)) for x, y in ALIGN_POINTS]
    return Compound(pins)


def alignment_sockets_raw(params: PrintReadyParams) -> Compound:
    socket_radius = params.align_pin_r + params.align_pin_clear
    socket_len = params.align_pin_insertion + 0.6
    sockets = []
    for x, y in ALIGN_POINTS:
        sockets.append(Cylinder(socket_radius, socket_len).translate((x, y, params.split_z + (socket_len / 2.0) + 0.05)))
    return Compound(sockets)


def snap_tabs_raw(params: PrintReadyParams) -> Compound:
    inner_h = _inner_dimension(CASE_HEIGHT, params.wall)
    ring_inner_y = ((inner_h - (params.seam_clearance * 2.0)) - (params.seam_wall * 2.0)) / 2.0
    tab_depth_y = 2.8
    tab_z = params.split_z - 0.35 + (params.snap_tab_z / 2.0)
    tabs = []
    for side in (-1, 1):
        # Overlap the seam ring so each hidden snap lug is part of the shell,
        # not a separate free body sitting in the cavity.
        tab_y = side * (ring_inner_y - (tab_depth_y / 2.0) + 0.55)
        for tab_x in (-18.0, 18.0):
            tabs.append(Box(params.snap_tab_w, tab_depth_y, params.snap_tab_z).translate((tab_x, tab_y, tab_z)))
    return Compound(tabs)


def snap_socket_cuts_raw(params: PrintReadyParams) -> Compound:
    inner_h = _inner_dimension(CASE_HEIGHT, params.wall)
    ring_inner_y = ((inner_h - (params.seam_clearance * 2.0)) - (params.seam_wall * 2.0)) / 2.0
    tab_depth_y = 2.8
    cut_y_depth = tab_depth_y + params.snap_tab_clear
    cut_y = params.snap_tab_w + params.snap_tab_clear
    cut_z = params.snap_tab_z + params.snap_tab_clear
    cut_center_z = params.split_z + (cut_z / 2.0) - 0.15
    sockets = []
    for side in (-1, 1):
        tab_y = side * (ring_inner_y - (tab_depth_y / 2.0) + 0.55)
        for tab_x in (-18.0, 18.0):
            sockets.append(Box(cut_y, cut_y_depth, cut_z).translate((tab_x, tab_y, cut_center_z)))
    return Compound(sockets)


def _cutter_at(z_max: float) -> Box:
    size = 240.0
    half = size / 2.0
    return Box(size, size, size).translate((0.0, 0.0, z_max - half))


def _cutter_from(z_min: float) -> Box:
    size = 240.0
    half = size / 2.0
    return Box(size, size, size).translate((0.0, 0.0, z_min + half))


def front_back_halves_raw(
    *,
    params: PrintReadyParams | None = None,
    screen_center_xy: tuple[float, float] | None = None,
):
    params = PrintReadyParams() if params is None else params
    window_xy, window_w, window_h, window_r = sensor_window_geometry(params)
    # `screen_center_xy` is an explicit override for callers that need a non-
    # PCB-driven center (rare). Default behavior derives everything from the
    # PCB sensor cluster.
    if screen_center_xy is None:
        screen_center_xy = window_xy

    outer = enclosure_outer_raw()
    inner = enclosure_inner_raw(wall=params.wall)

    outer = outer - _usb_c_cutout_raw(params)
    outer = outer - _screen_opening_cut_raw(
        params,
        center_xy=screen_center_xy,
        width=window_w,
        height=window_h,
        radius=window_r,
    )

    pir_cut = _pir_fresnel_cutout_raw(params)
    if pir_cut is not None:
        outer = outer - pir_cut

    back_cutter = _cutter_at(params.split_z - (params.split_gap / 2.0))
    front_cutter = _cutter_from(params.split_z + (params.split_gap / 2.0))

    outer_back = _as_compound(outer & back_cutter)
    outer_front = _as_compound(outer & front_cutter)

    back = _as_compound(outer_back - (inner & back_cutter))
    front = _as_compound(outer_front - (inner & front_cutter))

    standoffs = _as_compound(pcb_standoffs_raw(params) & outer_back)
    overlap_features = _as_compound((seam_ring_raw(params) + snap_tabs_raw(params)) & outer)
    back_features = _as_compound(standoffs + overlap_features)
    back = _as_compound(back.fuse(back_features).clean())

    front_sockets = _as_compound((seam_groove_cut_raw(params) + snap_socket_cuts_raw(params)) & outer_front)
    front = _as_compound(front - front_sockets)

    # Ease the exterior edge around the screen recess when possible.
    try:
        x, y = screen_center_xy
        w = window_w + params.screen_recess_margin
        h = window_h + params.screen_recess_margin
        x_min = x - (w / 2.0) - 1.0
        x_max = x + (w / 2.0) + 1.0
        y_min = y - (h / 2.0) - 1.0
        y_max = y + (h / 2.0) + 1.0
        z_min = TOTAL_DEPTH - (params.wall + params.screen_recess_depth + 2.0)
        candidate_edges = []
        for edge in front.edges():
            bounds = edge.bounding_box()
            if (
                bounds.min.X >= x_min
                and bounds.max.X <= x_max
                and bounds.min.Y >= y_min
                and bounds.max.Y <= y_max
                and bounds.max.Z >= z_min
            ):
                candidate_edges.append(edge)
        if candidate_edges:
            front = fillet(candidate_edges, 0.9)
    except ValueError:
        pass

    return back, front


def validate_print_ready_alignment(
    *,
    params: PrintReadyParams | None = None,
    screen_center_xy: tuple[float, float] | None = None,
    window_size: tuple[float, float] | None = None,
):
    params = PrintReadyParams() if params is None else params
    if screen_center_xy is None or window_size is None:
        derived_xy, derived_w, derived_h, _ = sensor_window_geometry(params)
        if screen_center_xy is None:
            screen_center_xy = derived_xy
        if window_size is None:
            window_size = (derived_w, derived_h)

    inner_half_x = (CASE_WIDTH / 2.0) - params.wall
    inner_half_y = (CASE_HEIGHT / 2.0) - params.wall

    pcb_min_x = -(PCB_WIDTH / 2.0)
    pcb_max_x = PCB_WIDTH / 2.0
    pcb_min_y = -(PCB_HEIGHT / 2.0)
    pcb_max_y = PCB_HEIGHT / 2.0

    pcb_case_min_y = PCB_CASE_CENTER_Y + pcb_min_y
    inner_min_y = -(CASE_HEIGHT / 2.0) + params.wall
    clearance_bottom = pcb_case_min_y - inner_min_y
    if clearance_bottom < 0.25:
        raise ValueError(
            f"PCB bottom clearance too small for print-ready walls: {clearance_bottom:.3f}mm (wall={params.wall:.2f})."
        )

    # Ensure the nominal PCB outline is comfortably inside the cavity, leaving
    # some tolerance for print variance and chamfers.
    pcb_case_min_x = pcb_case_position(pcb_min_x, 0.0, 0.0)[0]
    pcb_case_max_x = pcb_case_position(pcb_max_x, 0.0, 0.0)[0]
    pcb_case_max_y = pcb_case_position(0.0, pcb_max_y, 0.0)[1]
    inner_min_x = -(CASE_WIDTH / 2.0) + params.wall
    inner_max_x = (CASE_WIDTH / 2.0) - params.wall
    inner_max_y = (CASE_HEIGHT / 2.0) - params.wall
    if pcb_case_min_x < inner_min_x + 0.8 or pcb_case_max_x > inner_max_x - 0.8:
        raise ValueError("PCB outline is too close to the left/right cavity walls.")
    if pcb_case_max_y > inner_max_y - 0.8:
        raise ValueError("PCB outline is too close to the top cavity wall.")

    holes = pcb_mount_holes_from_metadata()
    mount_board = [(round(x, 3), round(y, 3), round(d, 3)) for x, y, d in holes]
    mount_case = [tuple(round(v, 3) for v in pcb_case_position(x, y, 0.0)) for x, y, _ in holes]

    usb_case = _usb_c_case_datum()
    usb_board = tuple(round(float(v), 3) for v in pcb_usb_c_opening_center())
    usb_cut_y0 = BOTTOM_Y - 0.05
    usb_cut_y1 = usb_cut_y0 + params.usb_cut_depth
    if not (usb_cut_y0 <= usb_case[1] <= usb_cut_y1):
        raise ValueError(
            f"USB-C datum Y={usb_case[1]:.3f} not within cutout depth Y=[{usb_cut_y0:.3f},{usb_cut_y1:.3f}]"
        )
    usb_cut_x0 = usb_case[0] - (params.usb_cut_w / 2.0)
    usb_cut_x1 = usb_case[0] + (params.usb_cut_w / 2.0)
    usb_cut_z0 = usb_case[2] - (params.usb_cut_h / 2.0)
    usb_cut_z1 = usb_case[2] + (params.usb_cut_h / 2.0)
    # Cable insertion center should land comfortably within the cutout window.
    if not (usb_cut_x0 + 0.5 <= usb_case[0] <= usb_cut_x1 - 0.5):
        raise ValueError("USB-C datum X is too close to cutout side walls.")
    if not (usb_cut_z0 + 0.4 <= usb_case[2] <= usb_cut_z1 - 0.4):
        raise ValueError("USB-C datum Z is too close to cutout top/bottom walls.")
    if usb_case[2] >= params.split_z - 1.0:
        raise ValueError("USB-C datum is too close to the clamshell split; increase split_z.")

    # Keep the tallest PCB-side component below the clamshell split with some margin.
    data = load_board_metadata()
    max_component_top = 0.0
    for component in pcb_components(data):
        top_local_z = (PCB_THICKNESS / 2.0) + component["z_height"]
        max_component_top = max(max_component_top, pcb_case_position(0.0, 0.0, top_local_z)[2])
    if max_component_top >= params.split_z - 0.6:
        raise ValueError(
            f"PCB component Z max {max_component_top:.3f}mm too close to split_z={params.split_z:.3f}mm; raise split_z."
        )

    opening_x, opening_y = screen_center_xy
    opening_w, opening_h = window_size
    opening_half_w = opening_w / 2.0
    opening_half_h = opening_h / 2.0
    if opening_x - opening_half_w < LEFT_X + 6.0 or opening_x + opening_half_w > RIGHT_X - 6.0:
        raise ValueError("Sensor window is too close to the left/right outer edges.")
    if opening_y - opening_half_h < BOTTOM_Y + 6.0 or opening_y + opening_half_h > TOP_Y - 6.0:
        raise ValueError("Sensor window is too close to the top/bottom outer edges.")

    pcb_case_min_y = pcb_case_position(0.0, pcb_min_y, 0.0)[1]
    facts = {
        "case_width_mm": CASE_WIDTH,
        "case_height_mm": CASE_HEIGHT,
        "case_depth_mm": TOTAL_DEPTH,
        "wall_mm": params.wall,
        "split_z_mm": params.split_z,
        "seam_overlap_mm": params.seam_overlap,
        "pcb_center_y_mm": PCB_CASE_CENTER_Y,
        "pcb_bottom_clearance_mm": round(clearance_bottom, 3),
        "pcb_component_top_z_mm": round(max_component_top, 3),
        "mount_holes_board_mm": mount_board,
        "mount_holes_case_mm": mount_case,
        "usb_c_datum_board_mm": usb_board,
        "usb_c_datum_case_mm": tuple(round(v, 3) for v in usb_case),
        "usb_cutout_y_range_mm": (round(usb_cut_y0, 3), round(usb_cut_y1, 3)),
        "usb_cutout_xz_size_mm": (round(params.usb_cut_w, 3), round(params.usb_cut_h, 3)),
        "window_center_xy_mm": (round(opening_x, 3), round(opening_y, 3)),
        "window_opening_mm": (round(opening_w, 3), round(opening_h, 3)),
        "pcb_case_bounds_xy_mm": (
            round(pcb_case_min_x, 3),
            round(pcb_case_max_x, 3),
            round(pcb_case_min_y, 3),
            round(pcb_case_max_y, 3),
        ),
    }

    # Log key numbers when run through `gen_step_part`.
    print("print-ready:", json.dumps(facts, sort_keys=True))
    return facts
