from __future__ import annotations

from math import atan2, cos, degrees, hypot, radians, sin

from build123d import (
    Align,
    Axis,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Cone,
    Cylinder,
    Face,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    RectangleRounded,
    Torus,
    Wire,
    add,
    extrude,
    fillet,
    loft,
)


DISPLAY_NAME = "Cutaway miniature turbofan jet engine"

# Units: millimeters.
# Origin: front intake center at X=0 on the engine axis.
# Engine axis: +X, centered through Y=0, Z=0.

MODEL_LABEL = "cutaway_miniature_turbofan_engine"

CUTAWAY_START_DEG = -5.0
CUTAWAY_END_DEG = 95.0
VISIBLE_SECTOR_START_DEG = CUTAWAY_END_DEG
VISIBLE_SECTOR_END_DEG = 360.0 + CUTAWAY_START_DEG

NACELLE_LENGTH = 180.0
NACELLE_OUTER_RADIUS = 55.0
NACELLE_INNER_RADIUS = 48.0

BLADE_ROOT_OVERLAP = 1.5
STATOR_TIP_OVERLAP = 1.0
STRUT_OVERLAP = 0.8

BASE_CENTER_X = 90.0
BASE_LENGTH = 140.0
BASE_WIDTH = 70.0
BASE_THICKNESS = 8.0
BASE_TOP_Z = -110.0
BASE_BOTTOM_Z = BASE_TOP_Z - BASE_THICKNESS


def _polar_yz(radius: float, angle_rad: float) -> tuple[float, float]:
    return (radius * cos(angle_rad), radius * sin(angle_rad))


def _point_yz(x_pos: float, radius: float, angle_rad: float) -> tuple[float, float, float]:
    y_pos, z_pos = _polar_yz(radius, angle_rad)
    return (x_pos, y_pos, z_pos)


def _annular_sector_points(
    *,
    outer_radius: float,
    inner_radius: float,
    start_deg: float = VISIBLE_SECTOR_START_DEG,
    end_deg: float = VISIBLE_SECTOR_END_DEG,
    segments: int = 96,
) -> list[tuple[float, float]]:
    outer_points = []
    inner_points = []
    for index in range(segments + 1):
        angle = radians(start_deg + (end_deg - start_deg) * index / segments)
        outer_points.append(_polar_yz(outer_radius, angle))
        inner_points.append(_polar_yz(inner_radius, angle))
    return outer_points + list(reversed(inner_points))


def _annular_sector_face(
    *,
    x_pos: float,
    outer_radius: float,
    inner_radius: float,
    start_deg: float = VISIBLE_SECTOR_START_DEG,
    end_deg: float = VISIBLE_SECTOR_END_DEG,
    segments: int = 72,
) -> Face:
    points = []
    for index in range(segments + 1):
        angle = radians(start_deg + (end_deg - start_deg) * index / segments)
        points.append(_point_yz(x_pos, outer_radius, angle))
    for index in range(segments, -1, -1):
        angle = radians(start_deg + (end_deg - start_deg) * index / segments)
        points.append(_point_yz(x_pos, inner_radius, angle))
    return Face.make_surface(Wire.make_polygon(points, close=True))


def _yz_angle_degrees(y_pos: float, z_pos: float) -> float:
    return degrees(atan2(z_pos, y_pos)) % 360.0


def _angle_delta_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _in_cutaway(angle_deg: float) -> bool:
    angle = angle_deg % 360.0
    start = CUTAWAY_START_DEG % 360.0
    end = CUTAWAY_END_DEG % 360.0
    if start > end:
        return angle >= start or angle <= end
    return start <= angle <= end


def _safe_fillet(part, edges, radius: float):
    if not edges:
        return part
    try:
        return fillet(edges, radius=radius)
    except Exception:
        return part


def _label(part, label: str, color: Color | None = None):
    part.label = label
    if color is not None:
        part.color = color
    return part


def _make_compound(label: str, parts: list, color: Color | None = None) -> Compound:
    compound = Compound(obj=parts, children=parts, label=label)
    if color is not None:
        compound.color = color
    return compound


def _make_cylinder_x(
    *,
    label: str,
    x_start: float,
    x_end: float,
    radius: float,
    color: Color,
) -> object:
    with BuildPart() as cylinder_part:
        with Locations(Location(((x_start + x_end) / 2.0, 0.0, 0.0))):
            Cylinder(
                radius=radius,
                height=x_end - x_start,
                rotation=(0.0, 90.0, 0.0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            )
    return _label(cylinder_part.part, label, color)


def _make_annular_sector(
    *,
    label: str,
    x_start: float,
    x_end: float,
    outer_radius: float,
    inner_radius: float,
    color: Color,
    fillet_cut_edges: float | None = None,
) -> object:
    with BuildPart() as sector:
        with BuildSketch(Plane.YZ):
            Polygon(
                _annular_sector_points(
                    outer_radius=outer_radius,
                    inner_radius=inner_radius,
                ),
                align=None,
            )
        extrude(amount=x_end - x_start)

    part = sector.part.moved(Location((x_start, 0.0, 0.0)))

    if fillet_cut_edges is not None:
        cut_edges = []
        for edge in part.edges():
            bbox = edge.bounding_box()
            center = bbox.center()
            if bbox.size.X < (x_end - x_start) * 0.85:
                continue
            angle = _yz_angle_degrees(center.Y, center.Z)
            radius = hypot(center.Y, center.Z)
            if (
                min(inner_radius, outer_radius) - 1.0
                <= radius
                <= max(inner_radius, outer_radius) + 1.0
                and (
                    _angle_delta_deg(angle, CUTAWAY_START_DEG) < 1.0
                    or _angle_delta_deg(angle, CUTAWAY_END_DEG) < 1.0
                )
            ):
                cut_edges.append(edge)
        part = _safe_fillet(part, cut_edges, fillet_cut_edges)

    return _label(part, label, color)


def _make_tapered_annular_sector(
    *,
    label: str,
    x_start: float,
    x_end: float,
    outer_start_radius: float,
    inner_start_radius: float,
    outer_end_radius: float,
    inner_end_radius: float,
    color: Color,
) -> object:
    part = loft(
        [
            _annular_sector_face(
                x_pos=x_start,
                outer_radius=outer_start_radius,
                inner_radius=inner_start_radius,
            ),
            _annular_sector_face(
                x_pos=x_end,
                outer_radius=outer_end_radius,
                inner_radius=inner_end_radius,
            ),
        ]
    )
    return _label(part, label, color)


def _make_intake_lip() -> object:
    with BuildPart() as lip:
        with Locations(Location((5.0, 0.0, 0.0))):
            Torus(
                major_radius=50.0,
                minor_radius=5.0,
                major_angle=260.0,
                rotation=(0.0, 90.0, 0.0),
            )
    part = lip.part.rotate(Axis.X, -175.0)
    return _label(part, "rounded_intake_lip_5mm_radius", Color(0.74, 0.77, 0.78, 1.0))


def _make_nacelle_shell() -> Compound:
    parts = [
        _make_annular_sector(
            label="nacelle_hollow_duct_100deg_cutaway",
            x_start=0.0,
            x_end=NACELLE_LENGTH,
            outer_radius=NACELLE_OUTER_RADIUS,
            inner_radius=NACELLE_INNER_RADIUS,
            color=Color(0.73, 0.76, 0.78, 1.0),
            fillet_cut_edges=2.0,
        ),
        _make_intake_lip(),
        _make_tapered_annular_sector(
            label="rear_exhaust_ring_od92_id74",
            x_start=160.0,
            x_end=180.0,
            outer_start_radius=48.0,
            inner_start_radius=39.0,
            outer_end_radius=46.0,
            inner_end_radius=37.0,
            color=Color(0.62, 0.65, 0.67, 1.0),
        ),
    ]
    return _make_compound("nacelle_shell", parts)


def _normalized(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = hypot(hypot(vector[0], vector[1]), vector[2])
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _scale(vector: tuple[float, float, float], amount: float) -> tuple[float, float, float]:
    return (vector[0] * amount, vector[1] * amount, vector[2] * amount)


def _add_vec(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _section_face(
    *,
    center: tuple[float, float, float],
    chord_direction: tuple[float, float, float],
    thickness_direction: tuple[float, float, float],
    chord: float,
    thickness: float,
) -> Face:
    chord_half = _scale(chord_direction, chord / 2.0)
    thickness_half = _scale(thickness_direction, thickness / 2.0)
    points = [
        _add_vec(_add_vec(center, chord_half), thickness_half),
        _add_vec(_add_vec(center, _scale(chord_half, -1.0)), thickness_half),
        _add_vec(_add_vec(center, _scale(chord_half, -1.0)), _scale(thickness_half, -1.0)),
        _add_vec(_add_vec(center, chord_half), _scale(thickness_half, -1.0)),
    ]
    return Face.make_surface(Wire.make_polygon(points, close=True))


def _make_radial_blade(
    *,
    label: str,
    x_center: float,
    base_angle: float,
    root_radius: float,
    tip_radius: float,
    chord: float,
    thickness: float,
    sweep_deg: float,
    twist_root_deg: float,
    twist_tip_deg: float,
    color: Color,
    attachment_radius: float | None = None,
    axial_sweep: float = 0.0,
) -> object:
    span = tip_radius - root_radius
    stations = []
    if attachment_radius is not None and attachment_radius < root_radius:
        stations.append((attachment_radius, 0.0, 0.52, 1.08))
    stations.extend(
        [
            (root_radius, 0.0, 1.00, 1.00),
            (root_radius + span * 0.38, 0.38, 1.04, 0.92),
            (root_radius + span * 0.72, 0.72, 0.96, 0.84),
            (tip_radius, 1.0, 0.78, 0.68),
        ]
    )

    faces = []
    for radius, t, chord_scale, thickness_scale in stations:
        angle = base_angle + radians(sweep_deg) * (t**1.25)
        twist = radians(twist_root_deg + (twist_tip_deg - twist_root_deg) * t)
        tangent = (0.0, -sin(angle), cos(angle))
        x_axis = (1.0, 0.0, 0.0)
        chord_direction = _normalized(
            (
                cos(twist) * x_axis[0] + sin(twist) * tangent[0],
                cos(twist) * x_axis[1] + sin(twist) * tangent[1],
                cos(twist) * x_axis[2] + sin(twist) * tangent[2],
            )
        )
        thickness_direction = _normalized(
            (
                -sin(twist) * x_axis[0] + cos(twist) * tangent[0],
                -sin(twist) * x_axis[1] + cos(twist) * tangent[1],
                -sin(twist) * x_axis[2] + cos(twist) * tangent[2],
            )
        )
        center = (
            x_center + axial_sweep * (t - 0.5),
            radius * cos(angle),
            radius * sin(angle),
        )
        faces.append(
            _section_face(
                center=center,
                chord_direction=chord_direction,
                thickness_direction=thickness_direction,
                chord=chord * chord_scale,
                thickness=thickness * thickness_scale,
            )
        )

    part = loft(faces, ruled=False)
    return _label(part, label, color)


def _make_fan_rotor() -> Compound:
    parts = [
        _make_cylinder_x(
            label="fan_hub_d26_l18",
            x_start=19.0,
            x_end=37.0,
            radius=13.0,
            color=Color(0.31, 0.38, 0.43, 1.0),
        )
    ]
    for index in range(24):
        parts.append(
            _make_radial_blade(
                label=f"fan_blade_{index + 1:02d}",
                x_center=28.0,
                base_angle=radians(index * 360.0 / 24.0),
                root_radius=16.0,
                tip_radius=45.0,
                chord=18.0,
                thickness=2.0,
                sweep_deg=24.0,
                twist_root_deg=-20.0,
                twist_tip_deg=15.0,
                attachment_radius=13.0 - BLADE_ROOT_OVERLAP,
                axial_sweep=3.0,
                color=Color(0.77, 0.82, 0.86, 1.0),
            )
        )
    return _make_compound("fan_rotor", parts)


def _make_compressor_rotor() -> Compound:
    parts = []
    stage_centers = [57.0, 69.0, 81.0, 93.0]
    for stage_index, x_center in enumerate(stage_centers):
        parts.append(
            _make_cylinder_x(
                label=f"compressor_stage_{stage_index + 1}_disk_d42",
                x_start=x_center - 2.0,
                x_end=x_center + 2.0,
                radius=21.0,
                color=Color(0.45, 0.50, 0.54, 1.0),
            )
        )
        phase = radians(stage_index * 10.0)
        stage_angle_offset = -4.0 if stage_index % 2 else 4.0
        for blade_index in range(18):
            parts.append(
                _make_radial_blade(
                    label=f"compressor_s{stage_index + 1}_blade_{blade_index + 1:02d}",
                    x_center=x_center,
                    base_angle=phase + radians(blade_index * 360.0 / 18.0),
                    root_radius=22.0,
                    tip_radius=34.0,
                    chord=8.0,
                    thickness=1.2,
                    sweep_deg=8.0 + stage_angle_offset,
                    twist_root_deg=26.0 + stage_angle_offset,
                    twist_tip_deg=12.0 + stage_angle_offset,
                    attachment_radius=21.0 - BLADE_ROOT_OVERLAP,
                    axial_sweep=1.2,
                    color=Color(0.69, 0.73, 0.76, 1.0),
                )
            )
    return _make_compound("compressor_rotor_four_stages", parts)


def _make_stator_vanes() -> Compound:
    parts = []
    for ring_index, x_center in enumerate([63.0, 75.0, 87.0]):
        phase = radians(360.0 / 32.0 + ring_index * 6.0)
        for vane_index in range(16):
            parts.append(
                _make_radial_blade(
                    label=f"stator_r{ring_index + 1}_vane_{vane_index + 1:02d}",
                    x_center=x_center,
                    base_angle=phase + radians(vane_index * 360.0 / 16.0),
                    root_radius=36.0,
                    tip_radius=NACELLE_INNER_RADIUS + STATOR_TIP_OVERLAP,
                    chord=7.5,
                    thickness=1.0,
                    sweep_deg=-7.0,
                    twist_root_deg=-30.0,
                    twist_tip_deg=-18.0,
                    axial_sweep=-0.8,
                    color=Color(0.79, 0.65, 0.37, 1.0),
                )
            )
    return _make_compound("stator_vanes_three_rings", parts)


def _make_turbine_rotor() -> Compound:
    parts = []
    for stage_index, x_center in enumerate([128.0, 145.0]):
        parts.append(
            _make_cylinder_x(
                label=f"turbine_stage_{stage_index + 1}_disk_d46",
                x_start=x_center - 2.5,
                x_end=x_center + 2.5,
                radius=23.0,
                color=Color(0.49, 0.45, 0.41, 1.0),
            )
        )
        phase = radians(stage_index * 12.0)
        for blade_index in range(22):
            parts.append(
                _make_radial_blade(
                    label=f"turbine_s{stage_index + 1}_blade_{blade_index + 1:02d}",
                    x_center=x_center,
                    base_angle=phase + radians(blade_index * 360.0 / 22.0),
                    root_radius=24.0,
                    tip_radius=40.0,
                    chord=12.0,
                    thickness=2.0,
                    sweep_deg=-34.0,
                    twist_root_deg=-44.0,
                    twist_tip_deg=-8.0,
                    attachment_radius=23.0 - BLADE_ROOT_OVERLAP,
                    axial_sweep=2.2,
                    color=Color(0.74, 0.59, 0.42, 1.0),
                )
            )
    return _make_compound("turbine_rotor_two_stages", parts)


def _make_exhaust_cone() -> object:
    part = loft(
        [
            Face.make_surface(
                Wire.make_circle(
                    18.0,
                    plane=Plane((145.0, 0.0, 0.0), x_dir=(0.0, 1.0, 0.0), z_dir=(1.0, 0.0, 0.0)),
                )
            ),
            Face.make_surface(
                Wire.make_circle(
                    7.0,
                    plane=Plane((178.0, 0.0, 0.0), x_dir=(0.0, 1.0, 0.0), z_dir=(1.0, 0.0, 0.0)),
                )
            ),
        ]
    )
    return _label(part, "exhaust_cone_taper_d36_to_d14", Color(0.38, 0.40, 0.42, 1.0))


def _make_support_strut(index: int, angle_deg: float, *, trimmed: bool = False) -> object:
    angle = radians(angle_deg)
    inner_radius = 4.0 - STRUT_OVERLAP
    outer_radius = 31.0 if trimmed else NACELLE_INNER_RADIUS + STRUT_OVERLAP
    radial_direction = (0.0, cos(angle), sin(angle))
    tangent_direction = (0.0, -sin(angle), cos(angle))
    x_direction = (1.0, 0.0, 0.0)
    faces = []
    for radius in (inner_radius, outer_radius):
        center = (110.0, radius * radial_direction[1], radius * radial_direction[2])
        faces.append(
            _section_face(
                center=center,
                chord_direction=x_direction,
                thickness_direction=tangent_direction,
                chord=5.0,
                thickness=4.0,
            )
        )
    part = loft(faces, ruled=True)
    suffix = "_trimmed" if trimmed else ""
    return _label(part, f"support_strut_{index}_{int(angle_deg)}deg{suffix}", Color(0.33, 0.36, 0.38, 1.0))


def _make_support_struts() -> Compound:
    parts = []
    for index, angle_deg in enumerate([5.0, 95.0, 185.0, 275.0], start=1):
        trimmed = _in_cutaway(angle_deg) and _angle_delta_deg(angle_deg, CUTAWAY_END_DEG) > 0.5
        parts.append(_make_support_strut(index, angle_deg, trimmed=trimmed))
    return _make_compound("support_struts_cutaway_trimmed", parts)


def _make_mounting_pylon() -> object:
    def pylon_face(z_pos: float, x_width: float, y_width: float, x_center: float) -> Face:
        points = [
            (x_center - x_width / 2.0, 0.0, z_pos),
            (x_center - x_width * 0.18, y_width / 2.0, z_pos),
            (x_center + x_width * 0.35, y_width / 2.0, z_pos),
            (x_center + x_width / 2.0, 0.0, z_pos),
            (x_center + x_width * 0.35, -y_width / 2.0, z_pos),
            (x_center - x_width * 0.18, -y_width / 2.0, z_pos),
        ]
        return Face.make_surface(Wire.make_polygon(points, close=True))

    part = loft(
        [
            pylon_face(BASE_TOP_Z, 22.0, 10.0, 90.0),
            pylon_face(-82.0, 19.0, 9.0, 90.0),
            pylon_face(-55.0, 18.0, 8.0, 90.0),
        ],
        ruled=False,
    )
    return _label(part, "mounting_pylon_swept_aero_support", Color(0.46, 0.49, 0.50, 1.0))


def _make_display_base() -> object:
    with BuildPart() as base:
        with BuildSketch(Plane.XY):
            RectangleRounded(
                BASE_LENGTH,
                BASE_WIDTH,
                5.0,
                align=(Align.CENTER, Align.CENTER),
            )
        extrude(amount=BASE_THICKNESS)

        for x_offset in (-50.0, 50.0):
            for y_pos in (-22.0, 22.0):
                x_pos = BASE_CENTER_X + x_offset
                with Locations(Location((x_pos - BASE_CENTER_X, y_pos, -0.5))):
                    Cylinder(
                        radius=3.0,
                        height=BASE_THICKNESS + 1.0,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )
                with Locations(Location((x_pos - BASE_CENTER_X, y_pos, BASE_THICKNESS))):
                    Cone(
                        bottom_radius=3.0,
                        top_radius=5.5,
                        height=2.6,
                        align=(Align.CENTER, Align.CENTER, Align.MAX),
                        mode=Mode.SUBTRACT,
                    )

    part = base.part.moved(Location((BASE_CENTER_X, 0.0, BASE_BOTTOM_Z)))
    outer_edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        center = bbox.center()
        if abs(center.Z - BASE_BOTTOM_Z) > 0.03 and abs(center.Z - BASE_TOP_Z) > 0.03:
            continue
        if (
            abs(center.X - BASE_CENTER_X) > BASE_LENGTH / 2.0 - 6.0
            or abs(center.Y) > BASE_WIDTH / 2.0 - 6.0
        ):
            outer_edges.append(edge)
    part = _safe_fillet(part, outer_edges, 3.0)
    return _label(part, "display_base_rounded_rectangle_countersunk_holes", Color(0.22, 0.24, 0.25, 1.0))


def gen_step():
    """Return a labeled multi-body cutaway turbofan display model."""
    bodies = [
        _make_nacelle_shell(),
        _make_fan_rotor(),
        _make_compressor_rotor(),
        _make_turbine_rotor(),
        _make_cylinder_x(
            label="central_shaft_d8_x15_to_x165",
            x_start=15.0,
            x_end=165.0,
            radius=4.0,
            color=Color(0.18, 0.20, 0.22, 1.0),
        ),
        _make_stator_vanes(),
        _make_exhaust_cone(),
        _make_support_struts(),
        _make_mounting_pylon(),
        _make_display_base(),
    ]
    return _make_compound(MODEL_LABEL, bodies)
