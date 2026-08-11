from __future__ import annotations

import sys
from pathlib import Path

import build123d

V2_DIR = Path(__file__).resolve().parents[1]
PARTS_DIR = V2_DIR / "parts"
for path in (V2_DIR, PARTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import link_common as lc
from robot_common.step_entry import load_step_entry

sem = load_step_entry("servo_end_mount")


PART_NAME = Path(__file__).stem
DISPLAY_NAME = "Double Servo End Mount"

SIDE_BY_SIDE_CLEARANCE_MM = 2.0
SERVO_CENTER_SPACING_Y_MM = (2.0 * abs(lc.SERVO_REAR_EXTREME_LOCAL_Y_MM)) + SIDE_BY_SIDE_CLEARANCE_MM
SERVO_CENTER_OFFSET_Y_MM = 0.5 * SERVO_CENTER_SPACING_Y_MM
REAR_SERVO_CENTER_Y_MM = -SERVO_CENTER_OFFSET_Y_MM
FRONT_SERVO_CENTER_Y_MM = SERVO_CENTER_OFFSET_Y_MM
OUTER_FLANGE_WIDTH_SCALE = 2.0
SLOT_WIDTH_SCALE = 1.0
# Run the slot end-to-end between the vertical midlines of the two mount-hole
# rows so the slot grows with the widened double-servo side plate.
SLOT_LENGTH_MM = 2.0 * lc.SERVO_MOUNT_HOLE_LOCAL_Z_MM
CENTER_RELIEF_EDGE_CLEARANCE_MM = 1.0
# Match the output-horn relief used by link_bracket.py on link_assembly
# #o1.4.f4. This radius keeps the near M2 screw web at the same distance
# from the horn relief while clearing the rotating horn boss.
OUTPUT_HORN_RELIEF_RADIUS_MM = 11.0
EXTENDED_TOP_MOUNT_HOLES = tuple(
    (
        build123d.Vector(x_mm, 0.0, z_mm),
        lc.SERVO_MOUNT_HOLE_RADIUS_MM,
    )
    for x_mm in lc.SERVO_TOP_MOUNT_HOLE_LOCAL_X_MM
    for z_mm in (-lc.SERVO_MOUNT_HOLE_LOCAL_Z_MM, lc.SERVO_MOUNT_HOLE_LOCAL_Z_MM)
)


def _load_single_layout() -> sem.BracketLayout:
    if not sem.SERVO_STEP.exists():
        raise FileNotFoundError(f"Missing STS3250 servo STEP: {sem.SERVO_STEP}")
    servo_shape = sem.import_as_shape(sem.SERVO_STEP)
    return sem._build_layout(servo_shape, include_top_center_bridge=True)


def _translated_band(y_min: float, y_max: float, y_offset: float) -> tuple[float, float]:
    return y_min + y_offset, y_max + y_offset


def _x_flipped_band(y_min: float, y_max: float, y_offset: float) -> tuple[float, float]:
    return y_offset - y_max, y_offset - y_min


def _extended_top_tab_x_min() -> float:
    return (
        min(center.X - radius - sem.MOUNT_HOLE_EDGE_X_WEB_MM for center, radius in EXTENDED_TOP_MOUNT_HOLES)
        - sem.TOP_FLANGE_LENGTH_EXTENSION_MM
    )


def _expanded_z_bounds(layout: sem.BracketLayout) -> tuple[float, float]:
    lower_z_min, lower_z_inner = layout.tab_bands[0]
    _upper_z_inner, upper_z_max = layout.tab_bands[-1]
    lower_width = lower_z_inner - lower_z_min
    width_extension = (OUTER_FLANGE_WIDTH_SCALE - 1.0) * lower_width
    return (
        lower_z_min - width_extension,
        upper_z_max + width_extension,
    )


def _slot_center_z(layout: sem.BracketLayout) -> float:
    z_min, z_max = _expanded_z_bounds(layout)
    return 0.5 * (z_min + z_max)


def _expanded_tab_bands(layout: sem.BracketLayout) -> tuple[tuple[float, float], ...]:
    z_min, z_max = _expanded_z_bounds(layout)
    _lower_z_min, lower_z_max = layout.tab_bands[0]
    upper_z_min, _upper_z_max = layout.tab_bands[-1]
    lower_z_max -= CENTER_RELIEF_EDGE_CLEARANCE_MM
    upper_z_min += CENTER_RELIEF_EDGE_CLEARANCE_MM
    return (
        (z_min, lower_z_max),
        (upper_z_min, z_max),
    )


def _z_slot_cut(
    *,
    center_x: float,
    center_z: float,
    length: float,
    width: float,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    radius = 0.5 * width
    half_straight = 0.5 * length - radius
    y_start = y_min - sem.CUT_EXTENSION_MM
    y_height = (y_max - y_min) + (2.0 * sem.CUT_EXTENSION_MM)
    body: build123d.Shape = sem._make_box(
        x_min=center_x - radius,
        x_max=center_x + radius,
        y_min=y_start,
        y_max=y_start + y_height,
        z_min=center_z - half_straight,
        z_max=center_z + half_straight,
    )
    for end_z in (center_z - half_straight, center_z + half_straight):
        cap = sem._make_cylinder_along(
            radius=radius,
            height=y_height,
            origin=build123d.Vector(center_x, y_start, end_z),
            direction=build123d.Vector(0.0, 1.0, 0.0),
        )
        body = body.fuse(cap)
    return body


def _fuse_outer_flange(
    bracket: build123d.Shape,
    *,
    layout: sem.BracketLayout,
    x_min: float,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    for z_band_min, z_band_max in _expanded_tab_bands(layout):
        bracket = bracket.fuse(
            sem._make_rounded_flange_tab(
                x_min=x_min,
                x_max=layout.bracket_face_outer_x,
                y_min=y_min,
                y_max=y_max,
                z_min=z_band_min,
                z_max=z_band_max,
                radius=sem.FLANGE_FREE_CORNER_RADIUS_MM,
            )
        )

    if layout.center_bridge_x_min is not None and len(layout.tab_bands) >= 2:
        center_gap_z_min = layout.tab_bands[0][1] - CENTER_RELIEF_EDGE_CLEARANCE_MM
        center_gap_z_max = layout.tab_bands[-1][0] + CENTER_RELIEF_EDGE_CLEARANCE_MM
        bracket = bracket.fuse(
            sem._make_box(
                x_min=layout.center_bridge_x_min,
                x_max=layout.bracket_face_outer_x,
                y_min=y_min,
                y_max=y_max,
                z_min=center_gap_z_min,
                z_max=center_gap_z_max,
            )
        )
    return bracket


def _cut_outer_flange_slots(
    bracket: build123d.Shape,
    *,
    layout: sem.BracketLayout,
    rear_y_min: float,
    rear_y_max: float,
    front_y_min: float,
    front_y_max: float,
) -> build123d.Shape:
    scaled_slot_width = sem.SLOT_WIDTH_MM * SLOT_WIDTH_SCALE
    slot_center_z = _slot_center_z(layout)
    for name, center_x, _center_z, _length in sem._slot_specs(layout):
        if name == "top":
            y_min, y_max = front_y_min, front_y_max
        else:
            y_min, y_max = rear_y_min, rear_y_max
        bracket = bracket.cut(
            _z_slot_cut(
                center_x=center_x,
                center_z=slot_center_z,
                length=SLOT_LENGTH_MM,
                width=scaled_slot_width,
                y_min=y_min,
                y_max=y_max,
            )
        )
    return bracket


def _cut_rear_output_horn_relief(
    bracket: build123d.Shape,
    *,
    rear_y_min: float,
    rear_y_max: float,
) -> build123d.Shape:
    cutter = sem._make_cylinder_along(
        radius=OUTPUT_HORN_RELIEF_RADIUS_MM,
        height=(rear_y_max - rear_y_min) + (2.0 * sem.CUT_EXTENSION_MM),
        origin=build123d.Vector(
            lc.SERVO_SHAFT_LOCAL_X_MM,
            rear_y_min - sem.CUT_EXTENSION_MM,
            0.0,
        ),
        direction=build123d.Vector(0.0, 1.0, 0.0),
    )
    return bracket.cut(cutter)


def _cut_centered_front_horn_holes(
    bracket: build123d.Shape,
    *,
    layout: sem.BracketLayout,
) -> build123d.Shape:
    hole_depth = sem.SENDCUTSEND_SHEET_THICKNESS_MM + (2.0 * sem.CUT_EXTENSION_MM)
    start_x = layout.bracket_face_outer_x + sem.CUT_EXTENSION_MM
    rear_outer_horn_y = REAR_SERVO_CENTER_Y_MM - lc.SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM
    front_outer_horn_y = FRONT_SERVO_CENTER_Y_MM + lc.SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM
    front_horn_center_y = 0.5 * (rear_outer_horn_y + front_outer_horn_y)
    center_y_delta = front_horn_center_y - layout.front_face_center_y
    for center_y, center_z, radius in sem._front_horn_mount_hole_profiles(layout):
        cutter = sem._make_cylinder_along(
            radius=radius,
            height=hole_depth,
            origin=build123d.Vector(start_x, center_y + center_y_delta, center_z),
            direction=build123d.Vector(-1.0, 0.0, 0.0),
        )
        bracket = bracket.cut(cutter)
    return bracket


def _front_horn_center_y(layout: sem.BracketLayout) -> float:
    rear_outer_horn_y = REAR_SERVO_CENTER_Y_MM - lc.SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM
    front_outer_horn_y = FRONT_SERVO_CENTER_Y_MM + lc.SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM
    return 0.5 * (rear_outer_horn_y + front_outer_horn_y)


def _build_double_flat_layout() -> sem.BracketLayout:
    single = _load_single_layout()
    extended_top_tab_x_min = _extended_top_tab_x_min()
    z_min, z_max = _expanded_z_bounds(single)
    rear_y_min, rear_y_max = _x_flipped_band(
        single.top_tab_y_min,
        single.top_tab_y_max,
        REAR_SERVO_CENTER_Y_MM,
    )
    front_y_min, front_y_max = _translated_band(
        single.top_tab_y_min,
        single.top_tab_y_max,
        FRONT_SERVO_CENTER_Y_MM,
    )
    tab_bands = _expanded_tab_bands(single)
    center_bridge_x_min = single.center_bridge_x_min
    bend_bands = sem._merge_z_bands(
        (
            *tab_bands,
            (
                tab_bands[0][1],
                tab_bands[-1][0],
            ),
        )
    )
    return sem.BracketLayout(
        z_min=z_min,
        z_max=z_max,
        top_holes=EXTENDED_TOP_MOUNT_HOLES,
        bottom_holes=EXTENDED_TOP_MOUNT_HOLES,
        top_tab_x_min=extended_top_tab_x_min,
        bottom_tab_x_min=extended_top_tab_x_min,
        bracket_face_inner_x=single.bracket_face_inner_x,
        bracket_face_outer_x=single.bracket_face_outer_x,
        top_tab_y_min=front_y_min,
        top_tab_y_max=front_y_max,
        bottom_tab_y_min=rear_y_min,
        bottom_tab_y_max=rear_y_max,
        tab_bands=tab_bands,
        bend_bands=bend_bands,
        center_bridge_x_min=center_bridge_x_min,
        front_face_center_y=_front_horn_center_y(single),
        outer_flush_gap=single.outer_flush_gap,
    )


def _add_double_slots_to_dxf(doc, flat_pattern: sem.FlatPattern, layout: sem.BracketLayout) -> None:
    msp = doc.modelspace()
    slot_center_x = sem._slot_center_x(layout)
    slot_center_z = _slot_center_z(layout)
    slot_width = sem.SLOT_WIDTH_MM * SLOT_WIDTH_SCALE
    for name in ("top", "bottom"):
        if name == "top":
            flat_center_x = slot_center_x - layout.top_tab_x_min
        else:
            flat_center_x = flat_pattern.total_length_mm - (slot_center_x - layout.bottom_tab_x_min)
        flat_center_y = slot_center_z - layout.z_min
        msp.add_lwpolyline(
            sem._slot_profile_points(
                center_x=flat_center_x,
                center_y=flat_center_y,
                length=SLOT_LENGTH_MM,
                width=slot_width,
            ),
            close=True,
            dxfattribs={"layer": "CUT"},
        )


def build_step() -> build123d.Shape:
    layout = _load_single_layout()
    extended_top_tab_x_min = _extended_top_tab_x_min()
    z_min, z_max = _expanded_z_bounds(layout)
    rear_y_min, rear_y_max = _x_flipped_band(
        layout.top_tab_y_min,
        layout.top_tab_y_max,
        REAR_SERVO_CENTER_Y_MM,
    )
    front_y_min, front_y_max = _translated_band(
        layout.top_tab_y_min,
        layout.top_tab_y_max,
        FRONT_SERVO_CENTER_Y_MM,
    )

    bracket: build123d.Shape = sem._make_box(
        x_min=layout.bracket_face_inner_x,
        x_max=layout.bracket_face_outer_x,
        y_min=rear_y_min,
        y_max=front_y_max,
        z_min=z_min,
        z_max=z_max,
    )
    bracket = _fuse_outer_flange(
        bracket,
        layout=layout,
        x_min=extended_top_tab_x_min,
        y_min=rear_y_min,
        y_max=rear_y_max,
    )
    bracket = _fuse_outer_flange(
        bracket,
        layout=layout,
        x_min=extended_top_tab_x_min,
        y_min=front_y_min,
        y_max=front_y_max,
    )

    bracket = sem._cut_mount_holes(
        bracket,
        profiles=list(EXTENDED_TOP_MOUNT_HOLES),
        start_y=rear_y_min - sem.CUT_EXTENSION_MM,
        direction_y=1.0,
    )
    bracket = sem._cut_mount_holes(
        bracket,
        profiles=list(EXTENDED_TOP_MOUNT_HOLES),
        start_y=front_y_max + sem.CUT_EXTENSION_MM,
        direction_y=-1.0,
    )
    bracket = _cut_rear_output_horn_relief(
        bracket,
        rear_y_min=rear_y_min,
        rear_y_max=rear_y_max,
    )
    bracket = _cut_centered_front_horn_holes(bracket, layout=layout)
    bracket = _cut_outer_flange_slots(
        bracket,
        layout=layout,
        rear_y_min=rear_y_min,
        rear_y_max=rear_y_max,
        front_y_min=front_y_min,
        front_y_max=front_y_max,
    )

    solids = bracket.solids()
    if len(solids) != 1:
        raise RuntimeError(f"Expected one connected double servo end mount solid, found {len(solids)}")

    bracket.label = PART_NAME
    bracket.color = lc.BRACKET_COLOR
    bb = bracket.bounding_box()
    print(
        f"{DISPLAY_NAME}: "
        f"servo_center_spacing_y={SERVO_CENTER_SPACING_Y_MM:.3f} mm, "
        f"span_y={bb.size.Y:.3f} mm, "
        f"span_z={bb.size.Z:.3f} mm, "
        f"flange_x_min={extended_top_tab_x_min:.3f} mm, "
        f"slot={SLOT_LENGTH_MM:.3f}x"
        f"{sem.SLOT_WIDTH_MM * SLOT_WIDTH_SCALE:.3f} mm, "
        f"slot_center_z={_slot_center_z(layout):.3f} mm, "
        f"center_relief_edge_clearance={CENTER_RELIEF_EDGE_CLEARANCE_MM:.3f} mm, "
        f"rear_horn_relief_radius={OUTPUT_HORN_RELIEF_RADIUS_MM:.3f} mm, "
        f"mount_face_x={layout.bracket_face_outer_x:.4f} mm, "
        f"thickness={sem.SENDCUTSEND_SHEET_THICKNESS_MM:.4f} mm, "
        f"front_horn_patterns=1"
    )
    return bracket


def build_dxf():
    layout = _build_double_flat_layout()
    flat_pattern = sem._build_flat_pattern(layout)
    bracket = build_step()
    doc = sem._topology_flat_pattern_dxf(bracket, layout, flat_pattern)
    slot_edge_to_bend_min = layout.bracket_face_inner_x - (
        sem._slot_center_x(layout) + (0.5 * sem.SLOT_WIDTH_MM * SLOT_WIDTH_SCALE)
    )
    slot_side_end_gap = min(
        (_slot_center_z(layout) - (0.5 * SLOT_LENGTH_MM)) - layout.z_min,
        layout.z_max - (_slot_center_z(layout) + (0.5 * SLOT_LENGTH_MM)),
    )
    print(
        f"{DISPLAY_NAME} DXF: "
        f"length={flat_pattern.total_length_mm:.3f} mm, "
        f"width={flat_pattern.width_mm:.3f} mm, "
        f"bend_lines=({flat_pattern.bend_line_positions_mm[0]:.3f}, "
        f"{flat_pattern.bend_line_positions_mm[1]:.3f}) mm, "
        f"cut_circles={len(flat_pattern.cut_circles)}, "
        f"slots=2x{SLOT_LENGTH_MM:.3f}x{sem.SLOT_WIDTH_MM * SLOT_WIDTH_SCALE:.3f} mm, "
        f"slot_edge_to_bend_min={slot_edge_to_bend_min:.3f} mm, "
        f"slot_side_end_gap={slot_side_end_gap:.3f} mm"
    )
    return doc


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
