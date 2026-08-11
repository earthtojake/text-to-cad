from __future__ import annotations

from math import degrees, cos, sin, sqrt

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Cone,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    Rectangle,
    RectangleRounded,
    SlotOverall,
    Solid,
    Text,
    TextAlign,
    Torus,
    extrude,
)


# Units: millimeters.
# Origin: center of the cup base footprint, XY on table plane, +Z upward.

MODEL_LABEL = "photo_reference_takeaway_coffee_cup"

PAPER = Color(0.86, 0.78, 0.64, 1.0)
PAPER_EDGE = Color(0.90, 0.82, 0.69, 1.0)
LID_WHITE = Color(0.96, 0.94, 0.90, 1.0)
LID_HIGHLIGHT = Color(1.0, 0.985, 0.955, 1.0)
LID_SHADOW = Color(0.82, 0.80, 0.76, 1.0)
BLUE_LOGO = Color(0.00, 0.62, 0.78, 1.0)
DARK_OPENING = Color(0.08, 0.075, 0.065, 1.0)

BODY_HEIGHT = 108.0
BODY_BOTTOM_RADIUS = 30.0
BODY_TOP_RADIUS = 43.0
BODY_WALL = 2.2
BODY_BOTTOM_THICKNESS = 2.8

LID_SKIRT_BOTTOM_Z = 103.5
LID_TOP_Z = 127.0

LOGO_LOCAL_BOTTOM_Z = -2.0
LOGO_LOCAL_TOP_Z = 86.4
LOGO_WORLD_BOTTOM_Z = 34.0
LOGO_Z_SCALE = 0.56
LOGO_X_SCALE = 0.70
LOGO_WORLD_TOP_Z = LOGO_WORLD_BOTTOM_Z + (LOGO_LOCAL_TOP_Z - LOGO_LOCAL_BOTTOM_Z) * LOGO_Z_SCALE


def _set_metadata(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _radius_at_z(z_pos: float) -> float:
    slope = (BODY_TOP_RADIUS - BODY_BOTTOM_RADIUS) / BODY_HEIGHT
    return BODY_BOTTOM_RADIUS + slope * z_pos


def _annular_cylinder(
    *,
    label: str,
    outer_radius: float,
    inner_radius: float,
    height: float,
    z_bottom: float,
    color: Color,
) -> object:
    with BuildPart() as ring:
        with Locations(Location((0.0, 0.0, z_bottom))):
            Cylinder(
                radius=outer_radius,
                height=height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        with Locations(Location((0.0, 0.0, z_bottom - 0.75))):
            Cylinder(
                radius=inner_radius,
                height=height + 1.5,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    return _set_metadata(ring.part, label, color)


def _solid_cylinder(
    *,
    label: str,
    radius: float,
    height: float,
    z_bottom: float,
    color: Color,
) -> object:
    with BuildPart() as cylinder:
        with Locations(Location((0.0, 0.0, z_bottom))):
            Cylinder(
                radius=radius,
                height=height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
    return _set_metadata(cylinder.part, label, color)


def _make_paper_cup_body() -> object:
    extra_cut_height = 4.0
    slope = (BODY_TOP_RADIUS - BODY_BOTTOM_RADIUS) / BODY_HEIGHT
    inner_bottom_radius = _radius_at_z(BODY_BOTTOM_THICKNESS) - BODY_WALL
    inner_top_radius = BODY_TOP_RADIUS - BODY_WALL + slope * extra_cut_height

    with BuildPart() as cup:
        Cone(
            bottom_radius=BODY_BOTTOM_RADIUS,
            top_radius=BODY_TOP_RADIUS,
            height=BODY_HEIGHT,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        with Locations(Location((0.0, 0.0, BODY_BOTTOM_THICKNESS))):
            Cone(
                bottom_radius=inner_bottom_radius,
                top_radius=inner_top_radius,
                height=BODY_HEIGHT - BODY_BOTTOM_THICKNESS + extra_cut_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    return _set_metadata(
        cup.part,
        "tapered_beige_paper_cup_open_shell_12oz",
        PAPER,
    )


def _make_bottom_foot_ring() -> object:
    with BuildPart() as foot:
        with Locations(Location((0.0, 0.0, 3.2))):
            Torus(major_radius=BODY_BOTTOM_RADIUS - 2.0, minor_radius=1.25)
    return _set_metadata(foot.part, "subtle_rolled_bottom_paper_foot_ring", PAPER_EDGE)


def _make_lid_skirt_parts() -> list[object]:
    parts: list[object] = []
    parts.append(
        _annular_cylinder(
            label="white_plastic_lid_lower_snap_skirt_overhanging_cup",
            outer_radius=47.8,
            inner_radius=38.8,
            height=8.0,
            z_bottom=LID_SKIRT_BOTTOM_Z,
            color=LID_WHITE,
        )
    )
    parts.append(
        _annular_cylinder(
            label="thin_shadow_groove_between_lid_beads",
            outer_radius=46.4,
            inner_radius=42.3,
            height=1.0,
            z_bottom=112.5,
            color=LID_SHADOW,
        )
    )

    for label, z_pos, major_radius, minor_radius in [
        ("rounded_lower_snap_lip_bead", 108.8, 45.9, 2.1),
        ("rounded_middle_lid_bead", 113.6, 45.2, 1.55),
        ("rounded_upper_lid_bead_under_dome", 117.2, 43.4, 1.25),
    ]:
        with BuildPart() as bead:
            with Locations(Location((0.0, 0.0, z_pos))):
                Torus(major_radius=major_radius, minor_radius=minor_radius)
        parts.append(_set_metadata(bead.part, label, LID_WHITE))

    return parts


def _make_lid_top() -> list[object]:
    parts: list[object] = []

    with BuildPart() as dome:
        with Locations(Location((0.0, 0.0, 115.5))):
            Cone(
                bottom_radius=42.8,
                top_radius=39.0,
                height=9.4,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
    parts.append(_set_metadata(dome.part, "shallow_sloped_lid_dome", LID_WHITE))

    parts.append(
        _solid_cylinder(
            label="flat_raised_top_lid_disk",
            radius=38.4,
            height=2.1,
            z_bottom=124.6,
            color=LID_HIGHLIGHT,
        )
    )

    with BuildPart() as top_outer_ring:
        with Locations(Location((0.0, 0.0, 126.9))):
            Torus(major_radius=36.4, minor_radius=0.85)
    parts.append(_set_metadata(top_outer_ring.part, "fine_raised_outer_top_emboss_ring", LID_HIGHLIGHT))

    with BuildPart() as top_inner_ring:
        with Locations(Location((0.0, 0.0, 127.15))):
            Torus(major_radius=18.0, minor_radius=0.38)
    parts.append(_set_metadata(top_inner_ring.part, "faint_central_emboss_circle", LID_HIGHLIGHT))

    return parts


def _make_sip_feature() -> list[object]:
    parts: list[object] = []
    top_plane = Plane.XY.offset(LID_TOP_Z)

    with BuildPart() as raised_sip:
        with BuildSketch(top_plane):
            with Locations((11.0, 18.4)):
                SlotOverall(width=31.0, height=12.2, rotation=-9.0)
        extrude(amount=1.2)
    parts.append(_set_metadata(raised_sip.part, "raised_oval_sipping_platform_on_lid", LID_HIGHLIGHT))

    with BuildPart() as sip_opening:
        with BuildSketch(Plane.XY.offset(LID_TOP_Z + 1.22)):
            with Locations((15.2, 20.0)):
                SlotOverall(width=16.0, height=4.0, rotation=-9.0)
        extrude(amount=0.45)
    parts.append(_set_metadata(sip_opening.part, "dark_recessed_sip_slot_opening", DARK_OPENING))

    with BuildPart() as nose_ridge:
        with BuildSketch(Plane.XY.offset(LID_TOP_Z + 0.7)):
            with Locations((0.5, 7.5)):
                RectangleRounded(width=10.0, height=22.0, radius=2.0, rotation=-8.0)
        extrude(amount=0.75)
    parts.append(_set_metadata(nose_ridge.part, "low_centered_lid_drink_ridge", LID_HIGHLIGHT))

    return parts


def _make_top_embossing() -> list[object]:
    parts: list[object] = []
    emboss_plane = Plane.XY.offset(LID_TOP_Z + 0.18)

    with BuildPart() as caution_text:
        with BuildSketch(emboss_plane):
            with Locations((-2.5, -10.5)):
                Text(
                    "CAUTION HOT",
                    font_size=4.0,
                    text_align=(TextAlign.CENTER, TextAlign.CENTER),
                    rotation=3.0,
                )
            with Locations((-4.0, 6.0)):
                Text(
                    "PLEASE RECYCLE",
                    font_size=3.0,
                    text_align=(TextAlign.CENTER, TextAlign.CENTER),
                    rotation=-4.0,
                )
        extrude(amount=0.28)
    parts.append(_set_metadata(caution_text.part, "low_raised_lid_embossed_warning_text", LID_HIGHLIGHT))

    for index, (x_pos, y_pos, width, height, rotation) in enumerate(
        [
            (-18.0, 4.5, 10.0, 1.1, 13.0),
            (18.0, 4.5, 10.0, 1.1, -13.0),
            (-15.0, -18.0, 8.5, 1.0, -16.0),
            (15.0, -18.0, 8.5, 1.0, 16.0),
        ],
        start=1,
    ):
        with BuildPart() as tick:
            with BuildSketch(Plane.XY.offset(LID_TOP_Z + 0.16)):
                with Locations((x_pos, y_pos)):
                    Rectangle(width=width, height=height, rotation=rotation)
            extrude(amount=0.24)
        parts.append(_set_metadata(tick.part, f"short_emboss_tick_mark_{index:02d}", LID_HIGHLIGHT))

    return parts


def _make_blue_logo() -> list[object]:
    bottle_cells: list[object] = []
    z_bottom = LOGO_WORLD_BOTTOM_Z
    z_top = LOGO_WORLD_TOP_Z
    dz = 0.58

    z_pos = z_bottom
    cell_index = 1
    while z_pos < z_top:
        z_next = min(z_pos + dz, z_top)
        for interval in _blue_bottle_intervals(z_pos, z_next):
            cell = _make_curved_decal_cell(
                label=f"blue_bottle_logo_curved_surface_cell_{cell_index:03d}",
                x_left_bottom=interval[0],
                x_right_bottom=interval[1],
                z_bottom=z_pos,
                x_left_top=interval[2],
                x_right_top=interval[3],
                z_top=z_next,
                color=BLUE_LOGO,
            )
            if cell is not None:
                bottle_cells.append(cell)
                cell_index += 1
        z_pos = z_next

    mark_cells: list[object] = []
    z_pos = 34.65
    while z_pos < 37.35:
        z_next = min(z_pos + 0.36, 37.35)
        interval = _registered_mark_interval((z_pos + z_next) / 2.0)
        if interval is not None:
            cell = _make_curved_decal_cell(
                label=f"blue_bottle_registered_mark_surface_cell_{len(mark_cells) + 1:02d}",
                x_left_bottom=interval[0],
                x_right_bottom=interval[1],
                z_bottom=z_pos,
                x_left_top=interval[0],
                x_right_top=interval[1],
                z_top=z_next,
                color=BLUE_LOGO,
                inner_offset=0.18,
                outer_offset=0.72,
            )
            if cell is not None:
                mark_cells.append(cell)
        z_pos = z_next

    logo = Compound(
        obj=bottle_cells + mark_cells,
        children=bottle_cells + mark_cells,
        label="front_blue_bottle_logo_wrapped_on_cup_surface",
    )
    logo.color = BLUE_LOGO
    return [logo]


def _blue_bottle_intervals(
    z_bottom: float,
    z_top: float,
) -> list[tuple[float, float, float, float]]:
    intervals: list[tuple[float, float, float, float]] = []
    bottom_intervals = _logo_outline_intervals_at(z_bottom + 1.0e-4)
    top_intervals = _logo_outline_intervals_at(z_top - 1.0e-4)
    for bottom_interval, top_interval in zip(bottom_intervals, top_intervals):
        intervals.append((bottom_interval[0], bottom_interval[1], top_interval[0], top_interval[1]))
    return intervals


def _logo_outline_intervals_at(z_pos: float) -> list[tuple[float, float]]:
    local_z = (z_pos - LOGO_WORLD_BOTTOM_Z) / LOGO_Z_SCALE + LOGO_LOCAL_BOTTOM_Z
    if local_z < LOGO_LOCAL_BOTTOM_Z or local_z > LOGO_LOCAL_TOP_Z:
        return []

    outline = [
        (-4.6, 86.4),
        (-3.5, 86.1),
        (-2.1, 84.6),
        (-0.1, 83.7),
        (3.0, 83.2),
        (7.4, 83.1),
        (8.7, 83.4),
        (8.3, 82.2),
        (5.9, 81.4),
        (1.8, 81.2),
        (-2.7, 81.7),
        (-5.8, 82.0),
        (-6.7, 83.0),
        (-6.8, 84.8),
        (-6.2, 85.9),
        (-3.4, 80.7),
        (-3.4, 73.5),
        (-3.7, 68.2),
        (-4.7, 64.3),
        (-6.3, 61.1),
        (-8.6, 58.7),
        (-11.4, 56.8),
        (-13.4, 54.4),
        (-14.5, 50.8),
        (-15.1, 45.2),
        (-15.4, 37.0),
        (-15.2, 28.4),
        (-14.5, 20.0),
        (-13.5, 11.9),
        (-12.1, 4.1),
        (-10.7, 0.7),
        (-8.6, -0.8),
        (-4.6, -1.7),
        (-0.5, -2.0),
        (4.0, -1.8),
        (8.1, -0.9),
        (10.7, 0.8),
        (12.1, 4.5),
        (13.5, 11.2),
        (14.7, 19.4),
        (15.4, 28.1),
        (15.7, 37.2),
        (15.5, 45.9),
        (14.6, 52.0),
        (13.0, 56.3),
        (10.7, 59.8),
        (8.0, 62.2),
        (5.4, 63.7),
        (2.8, 64.8),
        (1.1, 66.5),
        (0.3, 69.8),
        (0.2, 74.9),
        (0.2, 80.4),
    ]
    xs: list[float] = []
    for index, (x1, z1) in enumerate(outline):
        x2, z2 = outline[(index + 1) % len(outline)]
        if z1 == z2:
            continue
        if (z1 <= local_z < z2) or (z2 <= local_z < z1):
            t = (local_z - z1) / (z2 - z1)
            xs.append(x1 + (x2 - x1) * t)
    xs.sort()
    return [
        (xs[index] * LOGO_X_SCALE, xs[index + 1] * LOGO_X_SCALE)
        for index in range(0, len(xs) - 1, 2)
    ]


def _registered_mark_interval(z_pos: float) -> tuple[float, float] | None:
    center_x = 14.2
    center_z = 36.0
    radius = 1.25
    dy = z_pos - center_z
    if abs(dy) > radius:
        return None
    half_width = radius * sqrt(max(0.0, 1.0 - dy * dy / (radius * radius)))
    return (center_x - half_width, center_x + half_width)


def _cup_surface_point(arc_x: float, z_pos: float, radial_offset: float) -> tuple[float, float, float]:
    radius = _radius_at_z(z_pos) + radial_offset
    angle = arc_x / radius
    return (radius * sin(angle), -radius * cos(angle), z_pos)


def _make_curved_decal_cell(
    *,
    label: str,
    x_left_bottom: float,
    x_right_bottom: float,
    z_bottom: float,
    x_left_top: float,
    x_right_top: float,
    z_top: float,
    color: Color,
    inner_offset: float = 0.16,
    outer_offset: float = 0.78,
) -> object | None:
    x_left = (x_left_bottom + x_left_top) / 2.0
    x_right = (x_right_bottom + x_right_top) / 2.0
    width = x_right - x_left
    height = z_top - z_bottom
    if width < 0.18 or height <= 0.0:
        return None

    z_center = (z_bottom + z_top) / 2.0
    thickness = outer_offset - inner_offset
    max_segment_width = 3.2
    segment_count = max(1, int(width / max_segment_width + 0.999))
    segment_parts = []

    for segment_index in range(segment_count):
        segment_left = x_left + width * segment_index / segment_count
        segment_right = x_left + width * (segment_index + 1) / segment_count
        segment_width = segment_right - segment_left
        x_center = (segment_left + segment_right) / 2.0
        segment_parts.append(
            _make_surface_decal_box(
                label=f"{label}_segment_{segment_index + 1:02d}",
                x_center=x_center,
                z_center=z_center,
                width=segment_width + 0.04,
                height=height + 0.035,
                thickness=thickness,
                radial_offset=inner_offset + thickness / 2.0,
                color=color,
            )
        )

    if len(segment_parts) == 1:
        return segment_parts[0]

    compound = Compound(obj=segment_parts, children=segment_parts, label=label)
    compound.color = color
    return compound


def _make_surface_decal_box(
    *,
    label: str,
    x_center: float,
    z_center: float,
    width: float,
    height: float,
    thickness: float,
    radial_offset: float,
    color: Color,
) -> object:
    radius = _radius_at_z(z_center) + radial_offset
    angle = x_center / radius
    center = _cup_surface_point(x_center, z_center, radial_offset)
    box = Solid.make_box(width, thickness, height)
    box = box.moved(Location((-width / 2.0, -thickness / 2.0, -height / 2.0)))
    box = box.moved(Location(center, (0.0, 0.0, degrees(angle))))
    return _set_metadata(box, label, color)


def gen_step():
    """Return a photo-inspired takeaway coffee cup model in millimeters."""
    parts: list[object] = [
        _make_paper_cup_body(),
        _make_bottom_foot_ring(),
    ]
    parts.extend(_make_lid_skirt_parts())
    parts.extend(_make_lid_top())
    parts.extend(_make_sip_feature())
    parts.extend(_make_top_embossing())
    parts.extend(_make_blue_logo())

    return Compound(obj=parts, children=parts, label=MODEL_LABEL)
