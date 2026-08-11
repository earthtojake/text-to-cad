"""Sculpted full-scale humanoid research platform.

Fresh STEP-first design authored from the user brief only.  No model geometry,
mesh, STEP file, or source from ``models/`` is imported or referenced.

Coordinate convention
---------------------
* +X: robot left
* +Y: robot forward
* +Z: up
* Z=0: studio floor / sole contact plane

Kinematics
----------
* 28 body revolute axes
* 15 revolute axes per five-finger hand
* 58 total revolute relationships

The static export uses an athletic ready pose.  Every relationship is authored
with native build123d joints through ``AssemblyHelper``; the exported STEP is a
resolved pose with labeled occurrences and source-level mate metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin, sqrt
from typing import Iterable, Sequence

from build123d import (
    Align,
    Axis,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Cylinder,
    Ellipse,
    Location,
    Plane,
    Polygon,
    RectangleRounded,
    Sphere,
    Torus,
    loft,
)
from cadpy.assembly import AssemblyHelper, label_shape


# Restrained industrial material palette.  Source colors survive the repo's
# topology/render path; external STEP viewers may display transparency as solid.
GRAPHITE = Color("#252B30")
CARBON = Color("#343B40")
ALUMINUM = Color("#AEB6BC")
TITANIUM = Color("#747E86")
OFF_WHITE = Color("#D8D9D4")
SMOKED_GLASS = Color(0.025, 0.075, 0.095, 0.82)
OPTIC_GLASS = Color(0.01, 0.055, 0.065, 0.94)
STATUS_AMBER = Color("#B8893A")

JOINT_CLEARANCE = 1.8
MIN_REMAINDER_VOLUME = 1.0e-4


Point = tuple[float, float, float]
Vec = tuple[float, float, float]


def _add(a: Point, b: Vec) -> Point:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Point, b: Point) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(v: Vec, scale: float) -> Vec:
    return (v[0] * scale, v[1] * scale, v[2] * scale)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(v: Vec) -> float:
    return sqrt(_dot(v, v))


def _unit(v: Vec) -> Vec:
    magnitude = _length(v)
    if magnitude < 1e-9:
        raise ValueError("Direction must have non-zero length")
    return (v[0] / magnitude, v[1] / magnitude, v[2] / magnitude)


def _lerp(a: Point, b: Point, t: float) -> Point:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _basis(axis: Vec, x_hint: Vec = (1.0, 0.0, 0.0)) -> tuple[Vec, Vec, Vec]:
    z_dir = _unit(axis)
    hint = _unit(x_hint)
    projected = _sub(hint, _mul(z_dir, _dot(hint, z_dir)))
    if _length(projected) < 1e-6:
        hint = (0.0, 1.0, 0.0)
        projected = _sub(hint, _mul(z_dir, _dot(hint, z_dir)))
    x_dir = _unit(projected)
    y_dir = _unit(_cross(z_dir, x_dir))
    return x_dir, y_dir, z_dir


def _plane(origin: Point, axis: Vec, x_hint: Vec = (1.0, 0.0, 0.0)) -> Plane:
    x_dir, _, z_dir = _basis(axis, x_hint)
    return Plane(origin=origin, x_dir=x_dir, z_dir=z_dir)


def _shape(shape, label: str, color: Color):
    return label_shape(shape, label, color=color)


def _module(name: str, children: Iterable) -> Compound:
    return Compound(label=name, children=list(children))


def _expanded_keepout(
    owner: Compound,
    clearance: float,
    *,
    joint_only: bool = False,
    host_bounds=None,
) -> Compound:
    """Return an exact outward clearance envelope for one moving module."""

    grown = []
    joint_tokens = (
        "actuator_shell",
        "bearing_core",
        "capturing_cuff",
        "flush_output_flange",
        "closed_spherical_cartridge",
        "output_hub",
        "recessed_fastener",
    )
    for child in owner.children:
        if joint_only and not any(token in child.label for token in joint_tokens):
            continue
        if host_bounds is not None:
            child_bounds = child.bounding_box()
            child_min, child_max = tuple(child_bounds.min), tuple(child_bounds.max)
            host_min, host_max = tuple(host_bounds.min), tuple(host_bounds.max)
            if any(
                child_max[index] + clearance < host_min[index]
                or child_min[index] - clearance > host_max[index]
                for index in range(3)
            ):
                continue
        for solid in child.solids():
            try:
                grown.append(solid.offset_3d(None, clearance))
            except (RuntimeError, ValueError):
                # OpenCascade cannot offset a few analytic spheres through its
                # generic shell builder.  Uniform growth about an isotropic solid's
                # bounding-box center is the exact equivalent for those cases.
                bbox = solid.bounding_box()
                dimensions = tuple(bbox.size)
                if max(dimensions) - min(dimensions) > 1.0e-5:
                    raise ValueError(
                        f"Cannot offset anisotropic keepout solid in {owner.label}: {dimensions}"
                    )
                center = tuple(bbox.center())
                factor = (dimensions[0] + 2.0 * clearance) / dimensions[0]
                centered = solid.moved(Location(tuple(-value for value in center)))
                grown.append(centered.scale(factor).moved(Location(center)))
    if not grown:
        raise ValueError(f"Moving module {owner.label!r} has no clearance solids")
    return Compound(label=f"{owner.label}:clearance_keepout", children=grown)


def _socket_trim(
    host: Compound,
    owner: Compound,
    clearance: float = JOINT_CLEARANCE,
    *,
    joint_only: bool = False,
) -> Compound:
    """Cut a labeled close-fitting socket in ``host`` around ``owner``.

    Every joint cartridge belongs to the moving module.  The fixed module is
    trimmed around that owner, leaving a real 1.8 mm void instead of relying on
    intersecting cosmetic geometry for visual continuity.
    """

    keepout = _expanded_keepout(
        owner,
        clearance,
        joint_only=joint_only,
        host_bounds=host.bounding_box(),
    )
    trimmed = []
    keepout_bounds = keepout.bounding_box()
    keepout_min, keepout_max = tuple(keepout_bounds.min), tuple(keepout_bounds.max)
    for child in host.children:
        child_bounds = child.bounding_box()
        child_min, child_max = tuple(child_bounds.min), tuple(child_bounds.max)
        if any(
            child_max[index] < keepout_min[index]
            or child_min[index] > keepout_max[index]
            for index in range(3)
        ):
            trimmed.append(child)
            continue
        remainder = child - keepout
        if remainder.volume <= MIN_REMAINDER_VOLUME:
            continue
        remainder.label = child.label
        remainder.color = child.color
        trimmed.append(remainder)
    if not trimmed:
        raise ValueError(f"{host.label}: socket operation consumed the entire host")
    return Compound(label=host.label, children=trimmed)


def _socket_trim_envelope(
    host: Compound,
    center: Point,
    axis: Vec,
    radius: float,
    length: float,
    clearance: float = JOINT_CLEARANCE,
) -> Compound:
    """Trim a host with one robust cylindrical hand-joint keepout."""

    keepout = Cylinder(
        radius + clearance,
        length + 2.0 * clearance,
        align=Align.CENTER,
    ).moved(_plane(center, axis).location)
    trimmed = []
    for child in host.children:
        remainder = child - keepout
        if remainder.volume <= MIN_REMAINDER_VOLUME:
            continue
        remainder.label = child.label
        remainder.color = child.color
        trimmed.append(remainder)
    if not trimmed:
        raise ValueError(f"{host.label}: hand socket consumed the entire host")
    return Compound(label=host.label, children=trimmed)


def _joint_envelope(
    center: Point,
    axis: Vec,
    radius: float,
    length: float,
    clearance: float = JOINT_CLEARANCE,
):
    return Cylinder(
        radius + clearance,
        length + 2.0 * clearance,
        align=Align.CENTER,
    ).moved(_plane(center, axis).location)


def _union_solids(shapes: Sequence) -> list:
    shapes = list(shapes)
    if len(shapes) <= 1:
        return shapes
    result = shapes[0].fuse(*shapes[1:])
    if hasattr(result, "wrapped"):
        solids = list(result.solids())
    else:
        solids = [solid for shape in result for solid in shape.solids()]
    if not solids:
        raise ValueError("Combined keepout union has no solids")
    return solids


def _bounds_tuple(shape) -> tuple[float, ...]:
    box = shape.bounding_box()
    return (*tuple(box.min), *tuple(box.max))


def _bounds_overlap(a, b, tolerance: float = 1.0e-7) -> bool:
    return not (
        a[3] + tolerance < b[0]
        or b[3] + tolerance < a[0]
        or a[4] + tolerance < b[1]
        or b[4] + tolerance < a[1]
        or a[5] + tolerance < b[2]
        or b[5] + tolerance < a[2]
    )


def _socket_trim_many(
    host: Compound,
    keepout_solids: Sequence,
    *,
    preunion: bool = False,
) -> Compound:
    """Cut every labeled child with exact, optionally pre-unioned keepouts."""

    tools = _union_solids(keepout_solids) if preunion else list(keepout_solids)
    tool_rows = [(tool, _bounds_tuple(tool)) for tool in tools]
    trimmed = []
    for child in host.children:
        if preunion:
            child_bounds = _bounds_tuple(child)
            child_tools = [
                tool
                for tool, tool_bounds in tool_rows
                if _bounds_overlap(child_bounds, tool_bounds)
            ]
            if not child_tools:
                trimmed.append(child)
                continue
        else:
            child_tools = tools
        remainder = child.cut(*child_tools)
        if remainder.volume <= MIN_REMAINDER_VOLUME:
            continue
        remainder.label = child.label
        remainder.color = child.color
        trimmed.append(remainder)
    if not trimmed:
        raise ValueError(f"{host.label}: combined sockets consumed the entire host")
    return Compound(label=host.label, children=trimmed)


def _socket_trim_owners(
    host: Compound,
    owners: Sequence[Compound],
    clearance: float = JOINT_CLEARANCE,
) -> Compound:
    """Cut several body-owner keepouts from an unfragmented host at once."""

    keepouts = [_expanded_keepout(owner, clearance) for owner in owners]
    trimmed = []
    for child in host.children:
        remainder = child.cut(*keepouts)
        if remainder.volume <= MIN_REMAINDER_VOLUME:
            continue
        remainder.label = child.label
        remainder.color = child.color
        trimmed.append(remainder)
    if not trimmed:
        raise ValueError(f"{host.label}: body sockets consumed the entire host")
    return Compound(label=host.label, children=trimmed)


def _elliptic_loft(
    profiles: Sequence[tuple[Point, float, float]],
    *,
    axis: Vec,
    x_hint: Vec,
    label: str,
    color: Color,
):
    if len(profiles) < 2:
        raise ValueError("A loft needs at least two profiles")
    if any(rx <= 0 or ry <= 0 for _, rx, ry in profiles):
        raise ValueError(f"Loft {label!r} has a non-positive profile radius")
    with BuildPart() as body:
        for origin, radius_x, radius_y in profiles:
            with BuildSketch(_plane(origin, axis, x_hint)):
                Ellipse(radius_x, radius_y)
        loft(ruled=False)
    if not body.part.is_valid:
        raise ValueError(f"Loft {label!r} is invalid")
    return _shape(body.part, label, color)


def _polygon_loft(
    sections: Sequence[tuple[Point, Sequence[tuple[float, float]]]],
    *,
    axis: Vec,
    x_hint: Vec,
    label: str,
    color: Color,
    ruled: bool = True,
):
    """Loft stable closed polygon sections in plane-local coordinates."""

    if len(sections) < 2:
        raise ValueError("A polygon loft needs at least two sections")
    point_count = len(sections[0][1])
    if point_count < 3 or any(len(points) != point_count for _, points in sections):
        raise ValueError("Polygon loft sections must retain one vertex count")
    with BuildPart() as body:
        for origin, points in sections:
            with BuildSketch(_plane(origin, axis, x_hint)):
                Polygon(*points)
        loft(ruled=ruled)
    if not body.part.is_valid or body.part.volume <= MIN_REMAINDER_VOLUME:
        raise ValueError(f"Polygon loft {label!r} is invalid")
    return _shape(body.part, label, color)


def _chamfered_outline(
    width: float,
    height: float,
    corner: float,
) -> tuple[tuple[float, float], ...]:
    if min(width, height) <= 2.0 * corner or corner <= 0.0:
        raise ValueError("Chamfer must fit inside its profile")
    half_width, half_height = width * 0.5, height * 0.5
    return (
        (-half_width + corner, -half_height),
        (half_width - corner, -half_height),
        (half_width, -half_height + corner),
        (half_width, half_height - corner),
        (half_width - corner, half_height),
        (-half_width + corner, half_height),
        (-half_width, half_height - corner),
        (-half_width, -half_height + corner),
    )


def _chamfered_loft(
    profiles: Sequence[tuple[Point, float, float, float]],
    *,
    axis: Vec,
    x_hint: Vec,
    label: str,
    color: Color,
    ruled: bool = True,
):
    return _polygon_loft(
        [
            (origin, _chamfered_outline(width, height, corner))
            for origin, width, height, corner in profiles
        ],
        axis=axis,
        x_hint=x_hint,
        label=label,
        color=color,
        ruled=ruled,
    )


def _polygon_prism(
    center: Point,
    *,
    axis: Vec,
    x_hint: Vec,
    outline: Sequence[tuple[float, float]],
    thickness: float,
    label: str,
    color: Color,
):
    axis_u = _unit(axis)
    return _polygon_loft(
        [
            (_add(center, _mul(axis_u, -thickness * 0.5)), outline),
            (_add(center, _mul(axis_u, thickness * 0.5)), outline),
        ],
        axis=axis_u,
        x_hint=x_hint,
        label=label,
        color=color,
        ruled=True,
    )


def _rounded_rect_loft(
    profiles: Sequence[tuple[Point, float, float, float]],
    *,
    axis: Vec,
    x_hint: Vec,
    label: str,
    color: Color,
    ruled: bool = False,
):
    """Blend rounded-rectangle stations into a soft hard-surface shell."""

    if len(profiles) < 2:
        raise ValueError("A rounded-rectangle loft needs at least two profiles")
    with BuildPart() as body:
        for origin, width, height, radius in profiles:
            if min(width, height) <= 2.0 * radius or radius <= 0.0:
                raise ValueError(f"Rounded profile does not fit in {label!r}")
            with BuildSketch(_plane(origin, axis, x_hint)):
                RectangleRounded(width, height, radius)
        loft(ruled=ruled)
    if not body.part.is_valid or body.part.volume <= MIN_REMAINDER_VOLUME:
        raise ValueError(f"Rounded-rectangle loft {label!r} is invalid")
    return _shape(body.part, label, color)


def _rounded_rect_prism(
    center: Point,
    *,
    axis: Vec,
    x_hint: Vec,
    width: float,
    height: float,
    radius: float,
    thickness: float,
    label: str,
    color: Color,
):
    axis_u = _unit(axis)
    return _rounded_rect_loft(
        [
            (_add(center, _mul(axis_u, -thickness * 0.5)), width, height, radius),
            (_add(center, _mul(axis_u, thickness * 0.5)), width, height, radius),
        ],
        axis=axis_u,
        x_hint=x_hint,
        label=label,
        color=color,
        ruled=True,
    )


def _elliptic_shell(
    outer_profiles: Sequence[tuple[Point, float, float]],
    inner_profiles: Sequence[tuple[Point, float, float]],
    *,
    axis: Vec,
    x_hint: Vec,
    label: str,
    color: Color,
):
    """Create an open-ended compound-curved shell from nested lofts."""

    outer = _elliptic_loft(
        outer_profiles,
        axis=axis,
        x_hint=x_hint,
        label=f"{label}:outer_tool",
        color=color,
    )
    inner = _elliptic_loft(
        inner_profiles,
        axis=axis,
        x_hint=x_hint,
        label=f"{label}:inner_tool",
        color=color,
    )
    shell = outer - inner
    if shell.volume <= MIN_REMAINDER_VOLUME or not shell.is_valid:
        raise ValueError(f"Elliptic shell {label!r} is invalid")
    return _shape(shell, label, color)


def _oriented_cylinder(
    center: Point,
    axis: Vec,
    radius: float,
    length: float,
    *,
    label: str,
    color: Color,
):
    solid = Cylinder(radius, length, align=Align.CENTER).moved(_plane(center, axis).location)
    return _shape(solid, label, color)


def _annular_cuff(
    center: Point,
    axis: Vec,
    outer_radius: float,
    inner_radius: float,
    length: float,
    *,
    label: str,
    color: Color,
):
    if not (0 < inner_radius < outer_radius):
        raise ValueError("Annular cuff radii are inconsistent")
    outer = Cylinder(outer_radius, length, align=Align.CENTER)
    inner = Cylinder(inner_radius, length + 2.0, align=Align.CENTER)
    ring = (outer - inner).moved(_plane(center, axis).location)
    return _shape(ring, label, color)


def _moving_rotor_shroud(
    name: str,
    center: Point,
    axis: Vec,
    socket_radius: float,
    socket_length: float,
    inner_radius: float,
    *,
    color: Color = GRAPHITE,
):
    """Fill a body-joint socket with a moving, rotation-invariant shroud.

    The shroud remains 2.0 mm inside the fixed socket radially and 1.2 mm at
    each axial end.  Its bore lightly overlaps the moving cartridge cuff so it
    reads as a supported output bell rather than a floating cosmetic ring.
    """

    return _annular_cuff(
        center,
        axis,
        socket_radius - 2.0,
        inner_radius,
        socket_length - 2.4,
        label=f"{name}:output_shroud",
        color=color,
    )


def _oriented_torus(
    center: Point,
    axis: Vec,
    major_radius: float,
    minor_radius: float,
    *,
    label: str,
    color: Color,
):
    ring = Torus(major_radius, minor_radius).moved(_plane(center, axis).location)
    return _shape(ring, label, color)


def _curved_member(
    start: Point,
    end: Point,
    start_radii: tuple[float, float],
    end_radii: tuple[float, float],
    *,
    label: str,
    color: Color,
    x_hint: Vec = (1.0, 0.0, 0.0),
    curve: Vec = (0.0, 0.0, 0.0),
    bulge: float = 1.08,
):
    axis = _sub(end, start)
    stations = (0.0, 0.20, 0.50, 0.78, 1.0)
    profiles: list[tuple[Point, float, float]] = []
    for t in stations:
        curve_scale = sin(pi * t)
        origin = _add(_lerp(start, end, t), _mul(curve, curve_scale))
        rx = start_radii[0] + (end_radii[0] - start_radii[0]) * t
        ry = start_radii[1] + (end_radii[1] - start_radii[1]) * t
        middle_gain = 1.0 + (bulge - 1.0) * sin(pi * t)
        profiles.append((origin, rx * middle_gain, ry * middle_gain))
    return _elliptic_loft(
        profiles,
        axis=axis,
        x_hint=x_hint,
        label=label,
        color=color,
    )


def _captured_joint(
    name: str,
    center: Point,
    axis: Vec,
    radius: float,
    length: float,
    *,
    family: str = "drum",
    accent: Color = TITANIUM,
    fasteners: bool = True,
) -> list:
    """Create a compact cartridge with explicit 1.8 mm radial cuff clearance."""

    axis_u = _unit(axis)
    children: list = []
    if family == "ring":
        # A closed spherical cartridge communicates a compact cross-roller
        # gimbal without the open, decorative-loop silhouette of a bare torus.
        # The axial hub and both cuffs overlap the sphere, so every viewing
        # direction has a mechanically continuous load path.
        children.append(
            _shape(
                Sphere(radius * 0.94).moved(Location(center)),
                f"{name}:closed_spherical_cartridge",
                GRAPHITE,
            )
        )
        children.append(
            _oriented_cylinder(
                center,
                axis_u,
                radius * 0.70,
                length + 2.0,
                label=f"{name}:output_hub",
                color=ALUMINUM,
            )
        )
    else:
        children.append(
            _oriented_cylinder(
                center,
                axis_u,
                radius,
                length,
                label=f"{name}:actuator_shell",
                color=GRAPHITE,
            )
        )
        children.append(
            _oriented_cylinder(
                center,
                axis_u,
                radius * 0.68,
                length + 4.0,
                label=f"{name}:bearing_core",
                color=ALUMINUM,
            )
        )

    cuff_length = max(6.0, min(12.0, length * 0.22))
    cuff_offset = max(0.0, length * 0.5 - cuff_length * 0.5)
    cuff_overhang = max(3.2, min(7.5, radius * 0.18))
    is_hand_joint = name.startswith("hand:")
    flange_radius = radius + 0.8 if is_hand_joint else radius * 0.80
    flange_offset = 1.8 if is_hand_joint else 1.5
    flange_thickness = 3.2 if is_hand_joint else 2.6
    for side, detail in ((-1.0, "inboard"), (1.0, "outboard")):
        cuff_center = _add(center, _mul(axis_u, side * cuff_offset))
        children.append(
            _annular_cuff(
                cuff_center,
                axis_u,
                radius + cuff_overhang,
                radius + 1.8,
                cuff_length,
                label=f"{name}:capturing_cuff:{detail}",
                color=accent,
            )
        )
        cap_center = _add(center, _mul(axis_u, side * (length * 0.5 + flange_offset)))
        children.append(
            _oriented_cylinder(
                cap_center,
                axis_u,
                flange_radius,
                flange_thickness,
                label=f"{name}:flush_output_flange:{detail}",
                color=ALUMINUM,
            )
        )

    if fasteners and radius >= 18.0:
        radial_u, radial_v, _ = _basis(axis_u)
        cap_plane = _add(center, _mul(axis_u, length * 0.5 + 1.4))
        bolt_circle = radius * 0.50
        for index in range(6):
            angle = index * pi / 3.0
            radial = _add(_mul(radial_u, cos(angle) * bolt_circle), _mul(radial_v, sin(angle) * bolt_circle))
            fastener_center = _add(cap_plane, radial)
            children.append(
                _oriented_cylinder(
                    fastener_center,
                    axis_u,
                    max(1.4, radius * 0.055),
                    1.4,
                    label=f"{name}:recessed_fastener:{index + 1}",
                    color=GRAPHITE,
                )
            )
    return children


def _fork_cheeks(
    name: str,
    center: Point,
    axis: Vec,
    radius: float,
    moving_joint_length: float,
    *,
    color: Color = TITANIUM,
    thickness: float = 6.0,
    clearance: float = JOINT_CLEARANCE,
    bore_radius: float | None = None,
) -> list:
    """Fixed-side fork plates with an explicit axial flange clearance."""

    axis_u = _unit(axis)
    moving_outer_extent = moving_joint_length * 0.5 + 2.8
    cheek_offset = moving_outer_extent + clearance + thickness * 0.5
    cheeks = []
    for sign, side in ((-1.0, "inboard"), (1.0, "outboard")):
        cheek_center = _add(center, _mul(axis_u, sign * cheek_offset))
        if bore_radius is None:
            cheek = _oriented_cylinder(
                cheek_center,
                axis_u,
                radius,
                thickness,
                label=f"{name}:close_fitting_fork_cheek:{side}",
                color=color,
            )
        else:
            cheek = _annular_cuff(
                cheek_center,
                axis_u,
                radius,
                bore_radius,
                thickness,
                label=f"{name}:close_fitting_fork_cheek:{side}",
                color=color,
            )
        cheeks.append(cheek)
    return cheeks


def _fork_webs(
    name: str,
    center: Point,
    axis: Vec,
    moving_joint_length: float,
    anchor: Point,
    joint_half_width: float,
    anchor_half_width: float,
    *,
    color: Color = TITANIUM,
    thickness: float = 5.0,
    clearance: float = JOINT_CLEARANCE,
) -> list:
    """Connect close-fitting fork cheeks to their parent load path.

    The web lies outside the moving cartridge's axial envelope and tapers into
    the fixed link.  This prevents the unsupported-disc silhouette while the
    host-side socket trim still creates the functional radial clearance.
    """

    axis_u = _unit(axis)
    moving_outer_extent = moving_joint_length * 0.5 + 2.8
    web_offset = moving_outer_extent + clearance + thickness * 0.5
    webs = []
    for sign, side in ((-1.0, "inboard"), (1.0, "outboard")):
        offset = _mul(axis_u, sign * web_offset)
        webs.append(
            _curved_member(
                _add(center, offset),
                _add(anchor, offset),
                (thickness * 0.5, joint_half_width),
                (thickness * 0.5, anchor_half_width),
                label=f"{name}:tapered_fork_web:{side}",
                color=color,
                x_hint=axis_u,
                bulge=1.0,
            )
        )
    return webs


def _carrier(
    name: str,
    start: Point,
    end: Point,
    radius: float,
    *,
    color: Color = TITANIUM,
    curve: Vec = (0.0, 0.0, 0.0),
    x_hint: Vec = (1.0, 0.0, 0.0),
) -> list:
    return [
        _curved_member(
            start,
            end,
            (radius, radius * 0.76),
            (radius * 0.88, radius * 0.67),
            label=f"{name}:forged_carrier",
            color=color,
            curve=curve,
            x_hint=x_hint,
            bulge=1.10,
        )
    ]


def _armored_link(
    name: str,
    start: Point,
    end: Point,
    start_radii: tuple[float, float],
    end_radii: tuple[float, float],
    *,
    armor_color: Color = OFF_WHITE,
    curve: Vec = (0.0, 0.0, 0.0),
    x_hint: Vec = (1.0, 0.0, 0.0),
    cable_offset: Vec = (0.0, -1.0, 0.0),
) -> list:
    """Continuous carbon load path plus inset compound-curved armor and cable gutter."""

    axis = _sub(end, start)
    length = _length(axis)
    if length < 50.0:
        raise ValueError(f"Armored link {name!r} is too short")
    direction = _unit(axis)
    core = _curved_member(
        start,
        end,
        (start_radii[0] * 0.50, start_radii[1] * 0.50),
        (end_radii[0] * 0.48, end_radii[1] * 0.48),
        label=f"{name}:carbon_load_path",
        color=CARBON,
        curve=_mul(curve, 0.45),
        x_hint=x_hint,
        bulge=1.06,
    )

    inset = min(length * 0.15, 55.0)
    armor_start = _add(start, _mul(direction, inset))
    armor_end = _add(end, _mul(direction, -inset))
    # A six-station non-linear shell avoids the parallel-sided, extruded look
    # of a simple two-profile loft.  The restrained crown and alternating taper
    # read as tensioned sheet armor rather than a swollen anatomical muscle.
    armor_profiles: list[tuple[Point, float, float]] = []
    stations = (
        (0.00, 0.74, 0.68),
        (0.18, 0.92, 0.86),
        (0.40, 1.00, 0.92),
        (0.64, 0.92, 0.86),
        (0.84, 0.82, 0.76),
        (1.00, 0.70, 0.64),
    )
    for t, width_gain, depth_gain in stations:
        curve_scale = sin(pi * t)
        origin = _add(_lerp(armor_start, armor_end, t), _mul(curve, curve_scale))
        radius_x = start_radii[0] + (end_radii[0] - start_radii[0]) * t
        radius_y = start_radii[1] + (end_radii[1] - start_radii[1]) * t
        armor_profiles.append((origin, radius_x * width_gain, radius_y * depth_gain))
    armor = _elliptic_loft(
        armor_profiles,
        axis=axis,
        x_hint=x_hint,
        label=f"{name}:compound_curved_armor",
        color=armor_color,
    )

    band_radius = max(8.0, min(start_radii + end_radii) * 0.35)
    seam_a = _oriented_cylinder(
        _add(start, _mul(direction, inset - 2.0)),
        direction,
        band_radius,
        7.0,
        label=f"{name}:proximal_seam",
        color=GRAPHITE,
    )
    seam_b = _oriented_cylinder(
        _add(end, _mul(direction, -inset + 2.0)),
        direction,
        band_radius * 0.92,
        7.0,
        label=f"{name}:distal_seam",
        color=GRAPHITE,
    )

    cable_dir = _unit(cable_offset)
    cable_start = _add(_lerp(start, end, 0.20), _mul(cable_dir, start_radii[1] * 0.62))
    cable_end = _add(_lerp(start, end, 0.80), _mul(cable_dir, end_radii[1] * 0.62))
    gutter = _curved_member(
        cable_start,
        cable_end,
        (5.2, 3.4),
        (4.6, 3.0),
        label=f"{name}:flush_cable_gutter",
        color=GRAPHITE,
        curve=_mul(curve, 0.35),
        x_hint=x_hint,
        bulge=1.0,
    )
    return [core, armor, seam_a, seam_b, gutter]


def _foot_module(side: str, sign: float, ankle_center: Point) -> Compound:
    heel = (sign * 132.0, -104.0, 27.0)
    waist = (sign * 143.0, 15.0, 34.0)
    toe = (sign * 170.0, 151.0, 25.0)
    axis = _sub(toe, heel)
    x_hint = (1.0, -sign * 0.18, 0.0)
    sole = _elliptic_loft(
        [
            ((heel[0], heel[1], 4.0), 42.0, 4.0),
            ((waist[0], waist[1], 4.0), 61.0, 4.0),
            ((toe[0], toe[1], 4.0), 48.0, 4.0),
        ],
        axis=axis,
        x_hint=x_hint,
        label=f"foot:{side}:grounded_composite_sole",
        color=GRAPHITE,
    )
    upper = _elliptic_loft(
        [
            ((sign * 132.0, -95.0, 25.0), 34.0, 16.0),
            ((sign * 135.0, -45.0, 30.0), 42.0, 23.0),
            ((sign * 145.0, 25.0, 32.0), 55.0, 26.0),
            ((sign * 160.0, 118.0, 24.0), 48.0, 16.0),
            ((sign * 170.0, 145.0, 18.0), 30.0, 8.0),
        ],
        axis=axis,
        x_hint=x_hint,
        label=f"foot:{side}:rockered_upper_shell",
        color=TITANIUM,
    )
    bridge_end = (sign * 145.0, 8.0, 72.0)
    bridge = _curved_member(
        ankle_center,
        bridge_end,
        (34.0, 28.0),
        (36.0, 25.0),
        label=f"foot:{side}:overlapping_ankle_boot",
        color=OFF_WHITE,
        curve=(0.0, 10.0, 0.0),
        x_hint=(1.0, 0.0, 0.0),
        bulge=1.08,
    )
    joint = _captured_joint(
        f"ankle_roll:{side}",
        ankle_center,
        (0.0, 1.0, 0.0),
        31.0,
        66.0,
        family="drum",
        accent=TITANIUM,
    )
    output_shroud = _moving_rotor_shroud(
        f"ankle_roll:{side}",
        ankle_center,
        (0.0, 1.0, 0.0),
        38.5,
        76.8,
        30.8,
        color=GRAPHITE,
    )
    return _module(f"foot:{side}", [sole, upper, bridge, output_shroud, *joint])


def _torso_module(waist_pitch: Point) -> Compound:
    axis = (0.0, 0.0, 1.0)
    core = _rounded_rect_loft(
        [
            ((0.0, 0.0, 1100.0), 180.0, 110.0, 30.0),
            ((0.0, 6.0, 1180.0), 228.0, 132.0, 36.0),
            ((0.0, 16.0, 1300.0), 300.0, 158.0, 44.0),
            ((0.0, 25.0, 1400.0), 350.0, 170.0, 50.0),
            ((0.0, 35.0, 1460.0), 286.0, 134.0, 38.0),
            ((0.0, 48.0, 1490.0), 112.0, 76.0, 28.0),
        ],
        axis=axis,
        x_hint=(1.0, 0.0, 0.0),
        label="thorax:blended_rounded_carbon_load_frame",
        color=CARBON,
    )
    abdomen_boot = _elliptic_shell(
        [
            ((0.0, -1.0, 1086.0), 82.0, 70.0),
            ((0.0, 0.0, 1105.0), 88.0, 73.0),
            ((0.0, 2.0, 1125.0), 99.0, 77.0),
            ((0.0, 5.0, 1142.0), 109.0, 80.0),
        ],
        [
            ((0.0, -1.0, 1083.0), 74.0, 62.0),
            ((0.0, 0.0, 1105.0), 79.0, 64.0),
            ((0.0, 2.0, 1125.0), 89.0, 66.0),
            ((0.0, 5.0, 1145.0), 102.0, 69.0),
        ],
        axis=axis,
        x_hint=(1.0, 0.0, 0.0),
        label="thorax:sealed_flexible_abdomen_boot",
        color=GRAPHITE,
    )
    front_armors: list = []
    for sign, side in ((1.0, "left"), (-1.0, "right")):
        # One uninterrupted swept panel per side avoids a toy-like cross seam
        # while retaining a narrow, serviceable sternum split.
        front_armors.append(
            _elliptic_loft(
                [
                    ((sign * 25.0, 66.0, 1142.0), 17.0, 4.8),
                    ((sign * 34.0, 82.0, 1215.0), 24.0, 5.8),
                    ((sign * 45.0, 98.0, 1295.0), 31.0, 6.8),
                    ((sign * 56.0, 115.0, 1375.0), 37.0, 7.8),
                    ((sign * 39.0, 111.0, 1442.0), 22.0, 5.2),
                ],
                axis=axis,
                x_hint=(1.0, 0.0, 0.0),
                label=f"thorax:continuous_swept_sternum_armor:{side}",
                color=OFF_WHITE,
            )
        )
    front_spine = _curved_member(
        (0.0, 76.0, 1165.0),
        (0.0, 113.0, 1420.0),
        (5.0, 3.5),
        (4.0, 3.0),
        label="thorax:recessed_front_spine_seam",
        color=GRAPHITE,
        x_hint=(1.0, 0.0, 0.0),
        curve=(0.0, 4.0, 0.0),
        bulge=1.0,
    )
    rear_service: list = []
    for sign, side in ((1.0, "left"), (-1.0, "right")):
        rear_service.append(
            _elliptic_loft(
                [
                    ((sign * 24.0, -50.0, 1160.0), 21.0, 5.0),
                    ((sign * 40.0, -53.0, 1270.0), 37.0, 7.0),
                    ((sign * 47.0, -52.0, 1380.0), 41.0, 7.0),
                    ((sign * 31.0, -40.0, 1435.0), 24.0, 4.5),
                ],
                axis=axis,
                x_hint=(1.0, 0.0, 0.0),
                label=f"thorax:split_curved_rear_service_cover:{side}",
                color=TITANIUM,
            )
        )
    spine_cover = _curved_member(
        (-7.0, -59.0, 1130.0),
        (8.0, -45.0, 1428.0),
        (10.0, 6.0),
        (8.0, 5.0),
        label="thorax:swept_recessed_spine_cable_cover",
        color=GRAPHITE,
        x_hint=(1.0, 0.0, 0.0),
        curve=(7.0, -3.0, 0.0),
        bulge=1.04,
    )
    clavicles: list = []
    for sign, side in ((1.0, "left"), (-1.0, "right")):
        clavicles.append(
            _curved_member(
                (sign * 48.0, 108.0, 1382.0),
                (sign * 190.0, 78.0, 1408.0),
                (28.0, 15.0),
                (23.0, 14.0),
                label=f"thorax:swept_clavicle:{side}",
                color=ALUMINUM,
                x_hint=(0.0, 0.0, 1.0),
                curve=(0.0, 3.0, 5.0),
                bulge=1.01,
            )
        )
    joint = _captured_joint(
        "waist_pitch",
        waist_pitch,
        (1.0, 0.0, 0.0),
        48.0,
        112.0,
        family="ring",
        accent=TITANIUM,
    )
    waist_shroud = _moving_rotor_shroud(
        "waist_pitch",
        waist_pitch,
        (1.0, 0.0, 0.0),
        57.5,
        122.8,
        42.0,
        color=GRAPHITE,
    )
    return _module(
        "thorax",
        [
            core,
            abdomen_boot,
            *front_armors,
            front_spine,
            *rear_service,
            spine_cover,
            *clavicles,
            waist_shroud,
            *joint,
        ],
    )


def _pelvis_module() -> Compound:
    core = _elliptic_loft(
        [
            ((0.0, -3.0, 872.0), 78.0, 52.0),
            ((0.0, -5.0, 914.0), 112.0, 63.0),
            ((0.0, -4.0, 960.0), 132.0, 72.0),
            ((0.0, -2.0, 1005.0), 108.0, 63.0),
            ((0.0, -1.0, 1035.0), 70.0, 46.0),
        ],
        axis=(0.0, 0.0, 1.0),
        x_hint=(1.0, 0.0, 0.0),
        label="pelvis:blended_elliptic_load_bowl",
        color=CARBON,
    )
    children: list = [core]
    for sign, side in ((1.0, "left"), (-1.0, "right")):
        children.append(
            _curved_member(
                (sign * 48.0, 24.0, 994.0),
                (sign * 139.0, -2.0, 956.0),
                (28.0, 20.0),
                (32.0, 23.0),
                label=f"pelvis:tapered_iliac_armor:{side}",
                color=OFF_WHITE,
                x_hint=(0.0, 0.0, 1.0),
                curve=(0.0, 5.0, 11.0),
                bulge=1.03,
            )
        )
    for sign, side in ((1.0, "left"), (-1.0, "right")):
        children.append(
            _elliptic_loft(
                [
                    ((sign * 34.0, 52.0, 895.0), 17.0, 4.0),
                    ((sign * 52.0, 67.0, 952.0), 27.0, 5.8),
                    ((sign * 39.0, 57.0, 1008.0), 20.0, 4.6),
                ],
                axis=(0.0, 0.0, 1.0),
                x_hint=(1.0, 0.0, 0.0),
                label=f"pelvis:swept_front_armor:{side}",
                color=TITANIUM,
            )
        )
    return _module("pelvis_core", children)


def _head_module(neck_pitch: Point) -> Compound:
    shell = _elliptic_loft(
        [
            ((0.0, 35.0, 1602.0), 52.0, 37.0),
            ((0.0, 70.0, 1606.0), 68.0, 45.0),
            ((0.0, 108.0, 1607.0), 65.0, 43.0),
            ((0.0, 124.0, 1607.0), 57.0, 36.0),
        ],
        axis=(0.0, 1.0, 0.0),
        x_hint=(1.0, 0.0, 0.0),
        label="head:tapered_elliptic_sensor_enclosure",
        color=TITANIUM,
    )
    visor = _elliptic_loft(
        [
            ((0.0, 123.5, 1607.0), 56.0, 18.0),
            ((0.0, 131.0, 1607.0), 52.0, 16.0),
        ],
        axis=(0.0, 1.0, 0.0),
        x_hint=(1.0, 0.0, 0.0),
        label="head:convex_smoked_sensor_visor",
        color=SMOKED_GLASS,
    )
    optics = [
        _oriented_cylinder(
            (x, 129.5, 1606.0),
            (0.0, 1.0, 0.0),
            radius,
            3.0,
            label=f"head:front_optic:{name}",
            color=OPTIC_GLASS,
        )
        for x, radius, name in (
            (-30.0, 5.0, "depth"),
            (30.0, 9.0, "wide_field"),
        )
    ]
    lidar = [
        _oriented_cylinder(
            (0.0, 78.0, 1653.0),
            (0.0, 0.0, 1.0),
            18.0,
            8.0,
            label="head:flush_lidar_drum",
            color=GRAPHITE,
        ),
        _annular_cuff(
            (0.0, 78.0, 1657.0),
            (0.0, 0.0, 1.0),
            18.5,
            14.0,
            3.0,
            label="head:lidar_aperture_band",
            color=SMOKED_GLASS,
        ),
    ]
    neck_bridge = _curved_member(
        neck_pitch,
        (0.0, 59.0, 1578.0),
        (28.0, 23.0),
        (38.0, 30.0),
        label="head:overlapping_neck_saddle",
        color=OFF_WHITE,
        curve=(0.0, 3.0, 0.0),
        x_hint=(1.0, 0.0, 0.0),
        bulge=1.05,
    )
    neck_gaiter = _elliptic_shell(
        [
            ((0.0, 70.0, 1498.0), 50.0, 43.0),
            ((0.0, 80.0, 1535.0), 48.0, 41.0),
            ((0.0, 58.0, 1578.0), 52.0, 44.0),
        ],
        [
            ((0.0, 70.0, 1495.0), 44.0, 38.0),
            ((0.0, 80.0, 1535.0), 42.0, 35.0),
            ((0.0, 58.0, 1581.0), 45.0, 38.0),
        ],
        axis=(0.0, 0.0, 1.0),
        x_hint=(1.0, 0.0, 0.0),
        label="head:sealed_flexible_neck_gaiter",
        color=GRAPHITE,
    )
    joint = _captured_joint(
        "neck_pitch",
        neck_pitch,
        (1.0, 0.0, 0.0),
        27.0,
        62.0,
        family="drum",
        accent=TITANIUM,
        fasteners=False,
    )
    return _module(
        "sensor_head",
        [shell, visor, *optics, *lidar, neck_bridge, *joint],
    )


@dataclass(frozen=True)
class JointSpec:
    name: str
    fixed: str
    moving: str
    center: Point
    axis: Vec
    limits: tuple[float, float]
    group: str
    clearance_radius: float | None = None
    clearance_length: float | None = None


BODY_SOCKET_ENVELOPES: dict[str, tuple[float, float, float]] = {
    # Radius, full axial length, and axial center offset.  These values follow
    # the visible moving cartridge, cuff, or flexible collar plus 1.8 mm.  They
    # deliberately do not follow the full overlap bbox: doing so hollows the
    # neighboring shell into an unrealistic open U-frame.
    "waist_yaw": (70.0, 60.0, -18.6),
    "waist_pitch": (57.5, 122.8, 0.0),
    "neck_yaw": (49.5, 56.5, -5.0),
    "neck_pitch": (33.8, 76.0, 0.0),
    "hip_yaw": (62.0, 120.0, -30.0),
    "hip_roll": (54.0, 82.8, 0.0),
    "hip_pitch": (52.5, 96.8, 0.0),
    "knee_pitch": (49.0, 88.8, 0.0),
    "right_knee_pitch": (49.0, 88.8, 0.0),
    "ankle_pitch": (39.8, 76.8, 0.0),
    "ankle_roll": (38.5, 76.8, 0.0),
    "shoulder_pitch": (51.0, 84.8, 0.0),
    "shoulder_roll": (44.5, 75.6, 0.0),
    "shoulder_yaw": (41.9, 70.8, 0.0),
    "elbow_pitch": (38.5, 68.0, 0.0),
    "forearm_roll": (32.9, 87.2, 0.0),
    "wrist_pitch": (32.0, 72.8, 0.0),
}


def _body_socket_envelope(spec: JointSpec) -> tuple[float, float, float]:
    key = spec.name
    if key in BODY_SOCKET_ENVELOPES:
        return BODY_SOCKET_ENVELOPES[key]
    for side in ("left_", "right_"):
        if key.startswith(side):
            key = key[len(side) :]
            break
    try:
        return BODY_SOCKET_ENVELOPES[key]
    except KeyError as error:
        raise ValueError(f"Body joint {spec.name} lacks a socket envelope") from error


def _body_socket_key(spec: JointSpec) -> str:
    key = spec.name
    for side in ("left_", "right_"):
        if key.startswith(side):
            return key[len(side) :]
    return key


def _finger_modules(
    side: str,
    sign: float,
    palm_name: str,
    palm_center: Point,
) -> tuple[dict[str, Compound], list[JointSpec]]:
    modules: dict[str, Compound] = {}
    joints: list[JointSpec] = []
    # Hand breadth runs fore/aft while the fingers hang naturally downward.
    digits = (
        ("thumb", 37.0, 0.76, 0.32),
        ("index", 36.0, 0.96, 0.08),
        ("middle", 12.0, 1.04, 0.00),
        ("ring", -12.0, 0.98, -0.04),
        ("little", -39.0, 0.82, -0.10),
    )
    for digit_index, (digit, y_offset, length_scale, fan) in enumerate(digits):
        if digit == "thumb":
            base = (palm_center[0] + sign * 15.0, palm_center[1] + y_offset, palm_center[2] + 18.0)
            j2 = (base[0] + sign * 23.0, base[1] + 17.0, base[2] - 27.0)
            j3 = (j2[0] + sign * 18.0, j2[1] + 13.0, j2[2] - 23.0)
            tip = (j3[0] + sign * 15.0, j3[1] + 9.0, j3[2] - 20.0)
            base_axis = _unit((0.72, 0.0, sign * 0.70))
        else:
            base = (palm_center[0], palm_center[1] + y_offset, palm_center[2] - 48.0)
            j2 = (
                base[0] + sign * fan * 30.0,
                base[1] + 4.0,
                base[2] - 48.0 * length_scale,
            )
            j3 = (
                j2[0] + sign * fan * 20.0,
                j2[1] + 8.0,
                j2[2] - 36.0 * length_scale,
            )
            tip = (
                j3[0] + sign * fan * 15.0,
                j3[1] + 10.0,
                j3[2] - 29.0 * length_scale,
            )
            base_axis = (1.0, 0.0, 0.0)
        centers = (base, j2, j3, tip)
        parent = palm_name
        for segment_index, segment in enumerate(("proximal", "middle", "distal")):
            start = centers[segment_index]
            end = centers[segment_index + 1]
            taper = (10.0 - segment_index * 1.2) * length_scale
            link = _curved_member(
                start,
                end,
                (taper, taper * 0.76),
                (taper * 0.82, taper * 0.62),
                label=f"hand:{side}:{digit}:{segment}:tapered_link",
                color=OFF_WHITE if segment_index != 1 else ALUMINUM,
                x_hint=(0.0, 1.0, 0.0),
                curve=(0.0, 2.0 + segment_index * 1.5, 0.0),
                bulge=1.06,
            )
            hinge_axis = base_axis if segment_index == 0 else (1.0, 0.0, 0.0)
            hinge_radius = max(5.2, taper * 0.72)
            hinge_length = max(12.0, taper * 1.55)
            hinge = _captured_joint(
                f"hand:{side}:{digit}:joint_{segment_index + 1}",
                start,
                hinge_axis,
                hinge_radius,
                hinge_length,
                family="drum",
                accent=TITANIUM,
                fasteners=False,
            )
            module_name = f"hand_{side}_{digit}_{segment}"
            modules[module_name] = _module(module_name, [link, *hinge])
            joints.append(
                JointSpec(
                    name=f"{side}_{digit}_joint_{segment_index + 1}",
                    fixed=parent,
                    moving=module_name,
                    center=start,
                    axis=hinge_axis,
                    limits=(-10.0, 88.0) if digit != "thumb" else (-25.0, 70.0),
                    group=f"hand:{side}",
                    clearance_radius=hinge_radius
                    + max(3.2, min(7.5, hinge_radius * 0.18)),
                    clearance_length=hinge_length + 6.8,
                )
            )
            parent = module_name
    if len(joints) != 15:
        raise AssertionError(f"Expected 15 joints for {side} hand, got {len(joints)}")
    return modules, joints


def _palm_module(side: str, sign: float, wrist: Point) -> tuple[Compound, Point]:
    palm_center = (wrist[0] + sign * 3.0, wrist[1] + 8.0, wrist[2] - 64.0)
    palm = _elliptic_loft(
        [
            ((palm_center[0], palm_center[1], palm_center[2] + 52.0), 36.0, 18.0),
            ((palm_center[0], palm_center[1] + 1.0, palm_center[2] + 7.0), 44.0, 21.0),
            ((palm_center[0], palm_center[1] + 2.0, palm_center[2] - 38.0), 39.0, 17.0),
        ],
        axis=(0.0, 0.0, 1.0),
        x_hint=(0.0, 1.0, 0.0),
        label=f"hand:{side}:sculpted_palm",
        color=TITANIUM,
    )
    dorsal = _elliptic_loft(
        [
            ((palm_center[0] - sign * 19.0, palm_center[1], palm_center[2] + 39.0), 29.0, 5.0),
            ((palm_center[0] - sign * 21.0, palm_center[1] + 1.0, palm_center[2] + 4.0), 35.0, 6.5),
            ((palm_center[0] - sign * 17.0, palm_center[1] + 2.0, palm_center[2] - 28.0), 29.0, 5.0),
        ],
        axis=(0.0, 0.0, 1.0),
        x_hint=(0.0, 1.0, 0.0),
        label=f"hand:{side}:dorsal_composite_cover",
        color=OFF_WHITE,
    )
    wrist_bridge = _curved_member(
        wrist,
        (palm_center[0], palm_center[1], palm_center[2] + 52.0),
        (17.0, 14.0),
        (27.0, 20.0),
        label=f"hand:{side}:overlapping_wrist_cuff",
        color=OFF_WHITE,
        x_hint=(0.0, 1.0, 0.0),
        curve=(0.0, 4.0, 0.0),
        bulge=1.02,
    )
    joint = _captured_joint(
        f"wrist_pitch:{side}",
        wrist,
        (1.0, 0.0, 0.0),
        24.0,
        58.0,
        family="drum",
        accent=TITANIUM,
        fasteners=False,
    )
    wrist_output_collar = _oriented_cylinder(
        wrist,
        (1.0, 0.0, 0.0),
        30.2,
        61.2,
        label=f"hand:{side}:close_fitting_wrist_output_collar",
        color=GRAPHITE,
    )
    return _module(
        f"palm_{side}",
        [palm, dorsal, wrist_bridge, wrist_output_collar, *joint],
    ), palm_center


def gen_step():
    """Return the complete labeled humanoid assembly in its athletic pose."""

    asm = AssemblyHelper("sculpted_humanoid_28_body_dof_plus_dexterous_hands")
    raw_parts: dict[str, Compound] = {}
    parts: dict[str, Compound] = {}
    body_joints: list[JointSpec] = []
    hand_joints: list[JointSpec] = []

    def add_part(name: str, part: Compound) -> Compound:
        raw_parts[name] = part
        return part

    pelvis = add_part("pelvis_core", _pelvis_module())

    waist_yaw = (0.0, -5.0, 1034.0)
    waist_pitch = (0.0, 0.0, 1072.0)
    waist_yaw_part = _module(
        "waist_yaw_carrier",
        [
            _elliptic_loft(
                [
                    ((0.0, -5.0, 1018.0), 64.0, 52.0),
                    ((0.0, -2.0, 1048.0), 68.0, 56.0),
                    ((0.0, 0.0, 1089.0), 64.0, 52.0),
                ],
                axis=(0.0, 0.0, 1.0),
                x_hint=(1.0, 0.0, 0.0),
                label="waist:overlapping_telescopic_abdomen_cuff",
                color=ALUMINUM,
            ),
            *_captured_joint(
                "waist_yaw",
                waist_yaw,
                (0.0, 0.0, 1.0),
                49.0,
                38.0,
                family="ring",
                accent=TITANIUM,
            ),
            *_carrier(
                "waist_nested_carrier",
                waist_yaw,
                waist_pitch,
                34.0,
                color=ALUMINUM,
                curve=(0.0, 4.0, 0.0),
            ),
        ],
    )
    add_part("waist_yaw_carrier", waist_yaw_part)
    add_part("thorax", _torso_module(waist_pitch))
    body_joints.extend(
        [
            JointSpec("waist_yaw", "pelvis_core", "waist_yaw_carrier", waist_yaw, (0.0, 0.0, 1.0), (-60.0, 60.0), "waist"),
            JointSpec("waist_pitch", "waist_yaw_carrier", "thorax", waist_pitch, (1.0, 0.0, 0.0), (-20.0, 30.0), "waist"),
        ]
    )

    neck_yaw = (0.0, 70.0, 1492.0)
    neck_pitch = (0.0, 82.0, 1533.0)
    neck_carrier = _module(
        "neck_yaw_carrier",
        [
            _elliptic_loft(
                [
                    ((0.0, 64.0, 1462.0), 46.0, 39.0),
                    ((0.0, 72.0, 1497.0), 42.0, 36.0),
                    ((0.0, 82.0, 1544.0), 36.0, 31.0),
                ],
                axis=(0.0, 0.0, 1.0),
                x_hint=(1.0, 0.0, 0.0),
                label="neck:overlapping_telescopic_boot",
                color=GRAPHITE,
            ),
            *_captured_joint(
                "neck_yaw",
                neck_yaw,
                (0.0, 0.0, 1.0),
                27.0,
                34.0,
                family="ring",
                accent=TITANIUM,
                fasteners=False,
            ),
            *_carrier(
                "neck_nested_carrier",
                neck_yaw,
                neck_pitch,
                21.0,
                color=ALUMINUM,
                curve=(0.0, 4.0, 0.0),
            ),
        ],
    )
    add_part("neck_yaw_carrier", neck_carrier)
    add_part("sensor_head", _head_module(neck_pitch))
    body_joints.extend(
        [
            JointSpec("neck_yaw", "thorax", "neck_yaw_carrier", neck_yaw, (0.0, 0.0, 1.0), (-95.0, 95.0), "neck"),
            JointSpec("neck_pitch", "neck_yaw_carrier", "sensor_head", neck_pitch, (1.0, 0.0, 0.0), (-25.0, 30.0), "neck"),
        ]
    )

    for sign, side in ((1.0, "left"), (-1.0, "right")):
        # Athletic ready pose: asymmetric knee flexion and staggered load paths
        # avoid the mannequin-straight silhouette while preserving sole contact.
        hip_yaw = (sign * 104.0, -6.0, 978.0)
        hip_roll = (sign * 117.0, -3.0, 934.0)
        hip_pitch = (sign * 121.0, 5.0, 895.0)
        if side == "left":
            knee = (150.0, 175.0, 495.0)
            ankle_pitch = (145.0, 18.0, 126.0)
            ankle_roll = (144.0, 9.0, 98.0)
        else:
            knee = (-138.0, 128.0, 512.0)
            ankle_pitch = (-140.0, 10.0, 126.0)
            ankle_roll = (-141.0, 3.0, 98.0)

        hip_yaw_name = f"hip_yaw_carrier_{side}"
        hip_roll_name = f"hip_roll_carrier_{side}"
        thigh_name = f"thigh_{side}"
        shank_name = f"shank_{side}"
        ankle_name = f"ankle_pitch_carrier_{side}"
        foot_name = f"foot_{side}"

        add_part(
            hip_yaw_name,
            _module(
                hip_yaw_name,
                [
                    _elliptic_loft(
                        [
                            ((sign * 121.0, 3.0, 890.0), 40.0, 34.0),
                            ((sign * 113.0, 0.0, 934.0), 44.0, 37.0),
                            ((sign * 106.0, -3.0, 974.0), 42.0, 35.0),
                        ],
                        axis=(0.0, 0.0, 1.0),
                        x_hint=(1.0, 0.0, 0.0),
                        label=f"hip:{side}:closed_nested_gimbal_enclosure",
                        color=CARBON,
                    ),
                    _curved_member(
                        (sign * 132.0, -3.0, 970.0),
                        hip_roll,
                        (33.0, 27.0),
                        (35.0, 29.0),
                        label=f"hip:{side}:overlapping_outer_gimbal_pod",
                        color=TITANIUM,
                        x_hint=(0.0, 1.0, 0.0),
                        curve=(sign * 4.0, 6.0, 0.0),
                        bulge=1.06,
                    ),
                    _oriented_cylinder(
                        (sign * 104.0, -6.0, 986.0),
                        (0.0, 0.0, 1.0),
                        60.0,
                        28.0,
                        label=f"hip:{side}:close_fitting_yaw_output_collar",
                        color=GRAPHITE,
                    ),
                    *_captured_joint(
                        f"hip_yaw:{side}",
                        hip_yaw,
                        (0.0, 0.0, 1.0),
                        44.0,
                        38.0,
                        family="drum",
                        accent=TITANIUM,
                    ),
                    *_carrier(
                        f"hip_yaw_to_roll:{side}",
                        hip_yaw,
                        hip_roll,
                        31.0,
                        color=ALUMINUM,
                        curve=(sign * 3.0, 4.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            hip_roll_name,
            _module(
                hip_roll_name,
                [
                    _curved_member(
                        hip_roll,
                        hip_pitch,
                        (52.0, 46.0),
                        (51.0, 44.0),
                        label=f"hip:{side}:sealed_roll_pitch_flexure_boot",
                        color=GRAPHITE,
                        x_hint=(1.0, 0.0, 0.0),
                        curve=(sign * 2.0, 3.0, 0.0),
                        bulge=1.04,
                    ),
                    *_captured_joint(
                        f"hip_roll:{side}",
                        hip_roll,
                        (0.0, 1.0, 0.0),
                        42.0,
                        70.0,
                        family="drum",
                        accent=OFF_WHITE,
                    ),
                    _annular_cuff(
                        hip_roll,
                        (0.0, 1.0, 0.0),
                        52.0,
                        41.5,
                        40.0,
                        label=f"hip:{side}:roll:integrated_center_drum",
                        color=GRAPHITE,
                    ),
                    *_carrier(
                        f"hip_roll_to_pitch:{side}",
                        hip_roll,
                        hip_pitch,
                        30.0,
                        color=TITANIUM,
                        curve=(sign * 3.0, 5.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            thigh_name,
            _module(
                thigh_name,
                [
                    *[
                        _rounded_rect_prism(
                            _add(hip_pitch, (axial_sign * 45.5, -1.6, 7.8)),
                            axis=(1.0, 0.0, 0.0),
                            x_hint=(0.0, 1.0, 0.0),
                            width=42.0,
                            height=54.0,
                            radius=10.0,
                            thickness=3.0,
                            label=(
                                f"hip_pitch:{side}:rounded_output_yoke_plate:"
                                f"{'inboard' if axial_sign < 0.0 else 'outboard'}"
                            ),
                            color=TITANIUM,
                        )
                        for axial_sign in (-1.0, 1.0)
                    ],
                    _curved_member(
                        hip_pitch,
                        _lerp(hip_pitch, hip_roll, 0.70),
                        (46.0, 50.0),
                        (18.0, 16.0),
                        label=f"hip:{side}:close_fitting_pitch_output_bell",
                        color=GRAPHITE,
                        x_hint=(1.0, 0.0, 0.0),
                        curve=(0.0, 0.0, 0.0),
                        bulge=1.0,
                    ),
                    *[
                        _rounded_rect_prism(
                            _add(knee, (axial_sign * 48.05, -3.9, 9.2)),
                            axis=(1.0, 0.0, 0.0),
                            x_hint=(0.0, 1.0, 0.0),
                            width=44.0,
                            height=68.0,
                            radius=10.0,
                            thickness=4.5,
                            label=(
                                f"thigh:{side}:knee:rounded_yoke_plate:"
                                f"{'inboard' if axial_sign < 0.0 else 'outboard'}"
                            ),
                            color=TITANIUM,
                        )
                        for axial_sign in (-1.0, 1.0)
                    ],
                    *_captured_joint(
                        f"hip_pitch:{side}",
                        hip_pitch,
                        (1.0, 0.0, 0.0),
                        43.0,
                        86.0,
                        family="drum",
                        accent=TITANIUM,
                    ),
                    *_armored_link(
                        f"thigh:{side}",
                        hip_pitch,
                        knee,
                        (50.0, 36.0),
                        (35.0, 25.0),
                        armor_color=OFF_WHITE,
                        curve=(sign * 8.0, 12.0, 0.0),
                        x_hint=(1.0, 0.0, 0.0),
                        cable_offset=(0.0, -1.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            shank_name,
            _module(
                shank_name,
                [
                    *_captured_joint(
                        f"knee_pitch:{side}",
                        knee,
                        (1.0, 0.0, 0.0),
                        40.0,
                        82.0,
                        family="drum",
                        accent=ALUMINUM,
                    ),
                    *_armored_link(
                        f"shank:{side}",
                        knee,
                        ankle_pitch,
                        (37.0, 27.0),
                        (25.0, 18.0),
                        armor_color=TITANIUM,
                        curve=(sign * -5.0, -8.0, 0.0),
                        x_hint=(1.0, 0.0, 0.0),
                        cable_offset=(0.0, -1.0, 0.0),
                    ),
                    _curved_member(
                        (sign * 143.0, 17.0, 186.0),
                        ankle_pitch,
                        (31.0, 27.0),
                        (34.0, 29.0),
                        label=f"ankle:{side}:overlapping_shank_gaiter",
                        color=ALUMINUM,
                        x_hint=(1.0, 0.0, 0.0),
                        curve=(0.0, 3.0, 0.0),
                        bulge=1.04,
                    ),
                ],
            ),
        )
        add_part(
            ankle_name,
            _module(
                ankle_name,
                [
                    _elliptic_loft(
                        [
                            ((ankle_pitch[0], ankle_pitch[1], 144.0), 38.0, 31.0),
                            ((ankle_pitch[0], (ankle_pitch[1] + ankle_roll[1]) * 0.5, 117.0), 36.0, 30.0),
                            ((ankle_roll[0], ankle_roll[1], 104.0), 29.0, 23.0),
                        ],
                        axis=(0.0, 0.0, 1.0),
                        x_hint=(1.0, 0.0, 0.0),
                        label=f"ankle:{side}:sealed_biaxial_boot",
                        color=GRAPHITE,
                    ),
                    *_captured_joint(
                        f"ankle_pitch:{side}",
                        ankle_pitch,
                        (1.0, 0.0, 0.0),
                        32.0,
                        70.0,
                        family="drum",
                        accent=TITANIUM,
                    ),
                    *_carrier(
                        f"ankle_nested_carrier:{side}",
                        ankle_pitch,
                        ankle_roll,
                        24.0,
                        color=ALUMINUM,
                        curve=(0.0, 3.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(foot_name, _foot_module(side, sign, ankle_roll))

        body_joints.extend(
            [
                JointSpec(f"{side}_hip_yaw", "pelvis_core", hip_yaw_name, hip_yaw, (0.0, 0.0, 1.0), (-35.0, 35.0), f"leg:{side}"),
                JointSpec(
                    f"{side}_hip_roll",
                    hip_yaw_name,
                    hip_roll_name,
                    hip_roll,
                    (0.0, 1.0, 0.0),
                    (-15.0, 7.5) if side == "left" else (-7.5, 15.0),
                    f"leg:{side}",
                ),
                JointSpec(f"{side}_hip_pitch", hip_roll_name, thigh_name, hip_pitch, (1.0, 0.0, 0.0), (-80.0, 45.0), f"leg:{side}"),
                JointSpec(f"{side}_knee_pitch", thigh_name, shank_name, knee, (1.0, 0.0, 0.0), (0.0, 145.0), f"leg:{side}"),
                JointSpec(f"{side}_ankle_pitch", shank_name, ankle_name, ankle_pitch, (1.0, 0.0, 0.0), (-20.0, 55.0), f"leg:{side}"),
                JointSpec(f"{side}_ankle_roll", ankle_name, foot_name, ankle_roll, (0.0, 1.0, 0.0), (-15.0, 15.0), f"leg:{side}"),
            ]
        )

        # Arms counterbalance the crouch with intentionally different flexion.
        shoulder_pitch = (sign * 230.0, 72.0, 1406.0)
        shoulder_roll = (sign * 264.0, 77.0, 1378.0)
        shoulder_yaw = (sign * 281.0, 84.0, 1338.0)
        if side == "left":
            elbow = (320.0, 172.0, 1048.0)
            forearm_roll = (314.0, 202.0, 850.0)
            wrist = (310.0, 211.0, 800.0)
        else:
            elbow = (-309.0, 127.0, 1068.0)
            forearm_roll = (-306.0, 158.0, 858.0)
            wrist = (-304.0, 166.0, 810.0)

        shoulder_pitch_name = f"shoulder_pitch_carrier_{side}"
        shoulder_roll_name = f"shoulder_roll_carrier_{side}"
        upper_arm_name = f"upper_arm_{side}"
        forearm_name = f"forearm_{side}"
        wrist_carrier_name = f"wrist_carrier_{side}"
        palm_name = f"palm_{side}"

        add_part(
            shoulder_pitch_name,
            _module(
                shoulder_pitch_name,
                [
                    _curved_member(
                        (sign * 218.0, 76.0, 1410.0),
                        shoulder_roll,
                        (22.0, 16.0),
                        (24.0, 17.0),
                        label=f"shoulder:{side}:overlapping_outer_gimbal_pod",
                        color=ALUMINUM,
                        x_hint=(0.0, 0.0, 1.0),
                        curve=(sign * 2.0, 1.0, 2.0),
                        bulge=1.01,
                    ),
                    _curved_member(
                        shoulder_pitch,
                        shoulder_roll,
                        (41.0, 34.0),
                        (43.5, 37.0),
                        label=f"shoulder:{side}:sealed_pitch_roll_flexure_boot",
                        color=GRAPHITE,
                        x_hint=(0.0, 0.0, 1.0),
                        curve=(sign * 2.0, 2.0, 2.0),
                        bulge=1.02,
                    ),
                    *_captured_joint(
                        f"shoulder_pitch:{side}",
                        shoulder_pitch,
                        (1.0, 0.0, 0.0),
                        38.0,
                        74.0,
                        family="drum",
                        accent=TITANIUM,
                    ),
                    _annular_cuff(
                        shoulder_pitch,
                        (1.0, 0.0, 0.0),
                        49.0,
                        37.5,
                        38.0,
                        label=f"shoulder:{side}:pitch:integrated_center_drum",
                        color=GRAPHITE,
                    ),
                    *_carrier(
                        f"shoulder_pitch_to_roll:{side}",
                        shoulder_pitch,
                        shoulder_roll,
                        27.0,
                        color=ALUMINUM,
                        curve=(sign * 5.0, 3.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            shoulder_roll_name,
            _module(
                shoulder_roll_name,
                [
                    _curved_member(
                        shoulder_roll,
                        shoulder_yaw,
                        (38.0, 28.0),
                        (40.0, 30.0),
                        label=f"shoulder:{side}:sealed_roll_yaw_flexure_boot",
                        color=GRAPHITE,
                        x_hint=(0.0, 0.0, 1.0),
                        curve=(sign * 1.0, 2.0, 1.0),
                        bulge=1.02,
                    ),
                    *_captured_joint(
                        f"shoulder_roll:{side}",
                        shoulder_roll,
                        (0.0, 1.0, 0.0),
                        36.0,
                        66.0,
                        family="drum",
                        accent=TITANIUM,
                    ),
                    _annular_cuff(
                        shoulder_roll,
                        (0.0, 1.0, 0.0),
                        42.5,
                        35.5,
                        38.0,
                        label=f"shoulder:{side}:roll:integrated_center_drum",
                        color=GRAPHITE,
                    ),
                    *_carrier(
                        f"shoulder_roll_to_yaw:{side}",
                        shoulder_roll,
                        shoulder_yaw,
                        25.0,
                        color=TITANIUM,
                        curve=(sign * 3.0, 4.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            upper_arm_name,
            _module(
                upper_arm_name,
                [
                    *[
                        _rounded_rect_prism(
                            _add(elbow, (axial_sign * 39.05, -2.3, 7.7)),
                            axis=(1.0, 0.0, 0.0),
                            x_hint=(0.0, 1.0, 0.0),
                            width=38.0,
                            height=58.0,
                            radius=9.0,
                            thickness=4.5,
                            label=(
                                f"upper_arm:{side}:elbow:rounded_yoke_plate:"
                                f"{'inboard' if axial_sign < 0.0 else 'outboard'}"
                            ),
                            color=TITANIUM,
                        )
                        for axial_sign in (-1.0, 1.0)
                    ],
                    *_captured_joint(
                        f"shoulder_yaw:{side}",
                        shoulder_yaw,
                        (0.0, 0.0, 1.0),
                        34.0,
                        60.0,
                        family="drum",
                        accent=ALUMINUM,
                    ),
                    *_armored_link(
                        f"upper_arm:{side}",
                        shoulder_yaw,
                        elbow,
                        (35.0, 25.0),
                        (25.0, 17.0),
                        armor_color=OFF_WHITE,
                        curve=(sign * 6.0, 8.0, 0.0),
                        x_hint=(0.0, 1.0, 0.0),
                        cable_offset=(0.0, -1.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            forearm_name,
            _module(
                forearm_name,
                [
                    *_fork_cheeks(
                        f"forearm:{side}:roll",
                        forearm_roll,
                        _sub(wrist, elbow),
                        37.0,
                        58.0,
                        color=GRAPHITE,
                        thickness=8.0,
                        bore_radius=34.0,
                    ),
                    *_fork_webs(
                        f"forearm:{side}:roll",
                        forearm_roll,
                        _sub(wrist, elbow),
                        58.0,
                        _lerp(forearm_roll, elbow, 0.22),
                        31.0,
                        13.0,
                        color=GRAPHITE,
                        thickness=8.0,
                        clearance=4.2,
                    ),
                    *_captured_joint(
                        f"elbow_pitch:{side}",
                        elbow,
                        (1.0, 0.0, 0.0),
                        31.0,
                        64.0,
                        family="drum",
                        accent=TITANIUM,
                    ),
                    *_armored_link(
                        f"forearm:{side}",
                        elbow,
                        forearm_roll,
                        (28.0, 19.0),
                        (20.0, 14.0),
                        armor_color=ALUMINUM,
                        curve=(sign * -4.0, 7.0, 0.0),
                        x_hint=(0.0, 1.0, 0.0),
                        cable_offset=(0.0, -1.0, 0.0),
                    ),
                ],
            ),
        )
        add_part(
            wrist_carrier_name,
            _module(
                wrist_carrier_name,
                [
                    *_captured_joint(
                        f"forearm_roll:{side}",
                        forearm_roll,
                        _sub(wrist, elbow),
                        25.0,
                        58.0,
                        family="drum",
                        accent=TITANIUM,
                        fasteners=False,
                    ),
                    _moving_rotor_shroud(
                        f"forearm_roll:{side}",
                        forearm_roll,
                        _sub(wrist, elbow),
                        32.9,
                        87.2,
                        24.5,
                        color=GRAPHITE,
                    ),
                    *_carrier(
                        f"forearm_roll_to_wrist:{side}",
                        forearm_roll,
                        wrist,
                        27.0,
                        color=ALUMINUM,
                        curve=(0.0, 3.0, 0.0),
                        x_hint=(0.0, 1.0, 0.0),
                    ),
                    _curved_member(
                        forearm_roll,
                        _lerp(forearm_roll, wrist, 0.72),
                        (31.0, 26.0),
                        (23.0, 18.0),
                        label=f"wrist:{side}:sealed_roll_pitch_gaiter",
                        color=GRAPHITE,
                        curve=(0.0, 2.0, 0.0),
                        x_hint=(0.0, 1.0, 0.0),
                        bulge=1.03,
                    ),
                ],
            ),
        )
        palm_module, palm_center = _palm_module(side, sign, wrist)
        add_part(palm_name, palm_module)

        body_joints.extend(
            [
                JointSpec(f"{side}_shoulder_pitch", "thorax", shoulder_pitch_name, shoulder_pitch, (1.0, 0.0, 0.0), (-150.0, 90.0), f"arm:{side}"),
                JointSpec(
                    f"{side}_shoulder_roll",
                    shoulder_pitch_name,
                    shoulder_roll_name,
                    shoulder_roll,
                    (0.0, 1.0, 0.0),
                    (-45.0, 25.0) if side == "left" else (-25.0, 45.0),
                    f"arm:{side}",
                ),
                JointSpec(
                    f"{side}_shoulder_yaw",
                    shoulder_roll_name,
                    upper_arm_name,
                    shoulder_yaw,
                    (0.0, 0.0, 1.0),
                    (-100.0, 50.0) if side == "left" else (-50.0, 100.0),
                    f"arm:{side}",
                ),
                JointSpec(f"{side}_elbow_pitch", upper_arm_name, forearm_name, elbow, (1.0, 0.0, 0.0), (0.0, 108.0), f"arm:{side}"),
                JointSpec(f"{side}_forearm_roll", forearm_name, wrist_carrier_name, forearm_roll, _sub(wrist, elbow), (-170.0, 170.0), f"arm:{side}"),
                JointSpec(
                    f"{side}_wrist_pitch",
                    wrist_carrier_name,
                    palm_name,
                    wrist,
                    (1.0, 0.0, 0.0),
                    (-30.0, 30.0) if side == "left" else (-25.0, 30.0),
                    f"arm:{side}",
                ),
            ]
        )

        digit_modules, digit_joints = _finger_modules(side, sign, palm_name, palm_center)
        for module_name, module in digit_modules.items():
            add_part(module_name, module)
        hand_joints.extend(digit_joints)

    if len(body_joints) != 28:
        raise AssertionError(f"Expected 28 body axes, got {len(body_joints)}")
    if len(hand_joints) != 30:
        raise AssertionError(f"Expected 30 hand axes, got {len(hand_joints)}")

    all_joints = [*body_joints, *hand_joints]

    # Descendant moving bodies can pass through an ancestor housing even when
    # each immediate mate is clear.  Reuse the same proven analytic envelopes
    # as passive ancestor pockets so the complete neutral assembly has no
    # hidden pelvis/thigh or forearm/palm intersections.
    secondary_hosted_joints: dict[str, list[JointSpec]] = {}
    for spec in body_joints:
        if spec.name == "waist_pitch":
            secondary_hosted_joints.setdefault("pelvis_core", []).append(spec)
        elif spec.name.endswith("_hip_pitch"):
            side = "left" if spec.name.startswith("left_") else "right"
            secondary_hosted_joints.setdefault("pelvis_core", []).append(spec)
            secondary_hosted_joints.setdefault(f"hip_yaw_carrier_{side}", []).append(spec)
        elif spec.name.endswith("_wrist_pitch"):
            side = "left" if spec.name.startswith("left_") else "right"
            secondary_hosted_joints.setdefault(f"forearm_{side}", []).append(spec)

    # Sampled swept pockets preserve ancestor clearance when a downstream
    # cartridge changes orientation under an upstream yaw/roll axis.  The
    # analytic cylinders overlap generously between samples, forming a smooth
    # continuous service cavity without enlarging the visible joint seams.
    body_spec_by_name = {spec.name: spec for spec in body_joints}
    swept_host_keepouts: dict[str, list] = {}

    def add_swept_pocket(
        host_name: str,
        envelope_spec: JointSpec,
        pivot_spec: JointSpec,
        angles: Sequence[float],
        *,
        length_override: float | None = None,
    ) -> None:
        radius, length, axial_offset = _body_socket_envelope(envelope_spec)
        if length_override is not None:
            length = length_override
        envelope_center = _add(
            envelope_spec.center,
            _mul(_unit(envelope_spec.axis), axial_offset),
        )
        neutral = _joint_envelope(
            envelope_center,
            envelope_spec.axis,
            radius,
            length,
            0.0,
        )
        pivot_axis = Axis(pivot_spec.center, pivot_spec.axis)
        swept_host_keepouts.setdefault(host_name, []).extend(
            neutral.rotate(pivot_axis, angle) for angle in angles
        )

    add_swept_pocket(
        "pelvis_core",
        body_spec_by_name["waist_pitch"],
        body_spec_by_name["waist_yaw"],
        (-60.0, -45.0, -30.0, -15.0, 15.0, 30.0, 45.0, 60.0),
    )
    neck_pitch_spec = body_spec_by_name["neck_pitch"]
    neck_bridge_clearance = Sphere(35.5).moved(
        Location(_lerp(neck_pitch_spec.center, (0.0, 59.0, 1578.0), 0.25))
    )
    neck_pitch_axis = Axis(neck_pitch_spec.center, neck_pitch_spec.axis)
    swept_host_keepouts.setdefault("neck_yaw_carrier", []).extend(
        neck_bridge_clearance.rotate(neck_pitch_axis, angle)
        for angle in (-25.0, -10.0, 10.0, 20.0, 30.0)
    )
    for side in ("left", "right"):
        hip_pitch_spec = body_spec_by_name[f"{side}_hip_pitch"]
        hip_yaw_spec = body_spec_by_name[f"{side}_hip_yaw"]
        hip_roll_spec = body_spec_by_name[f"{side}_hip_roll"]
        add_swept_pocket(
            "pelvis_core",
            hip_pitch_spec,
            hip_yaw_spec,
            (-35.0, -25.0, -15.0, -5.0, 5.0, 15.0, 25.0, 35.0),
            length_override=100.6,
        )
        add_swept_pocket(
            "pelvis_core",
            hip_pitch_spec,
            hip_roll_spec,
            (-15.0, -7.5, 7.5, 15.0),
            length_override=100.6,
        )
        add_swept_pocket(
            f"hip_yaw_carrier_{side}",
            hip_pitch_spec,
            hip_roll_spec,
            (-15.0, -7.5, 7.5, 15.0),
        )
        hip_boot_clearance = Sphere(56.5).moved(
            Location(_lerp(hip_roll_spec.center, hip_pitch_spec.center, 0.50))
        )
        hip_roll_axis = Axis(hip_roll_spec.center, hip_roll_spec.axis)
        swept_host_keepouts.setdefault(f"hip_yaw_carrier_{side}", []).extend(
            hip_boot_clearance.rotate(hip_roll_axis, angle)
            for angle in (-15.0, -7.5, 7.5, 15.0)
        )

    # Build every socket for one host at once.  This avoids repeatedly
    # re-booleanning already-trimmed palm, pelvis, and thorax topology.
    hosted_joints: dict[str, list[JointSpec]] = {}
    for spec in all_joints:
        hosted_joints.setdefault(spec.fixed, []).append(spec)

    for host_name, specs in hosted_joints.items():
        host = raw_parts[host_name]
        keepouts = []
        for spec in specs:
            if spec.group.startswith("hand:"):
                if spec.clearance_radius is None or spec.clearance_length is None:
                    raise ValueError(f"Hand joint {spec.name} lacks a clearance envelope")
                keepouts.append(
                    _joint_envelope(
                        spec.center,
                        spec.axis,
                        spec.clearance_radius,
                        spec.clearance_length,
                        JOINT_CLEARANCE,
                    )
                )
            else:
                radius, length, axial_offset = _body_socket_envelope(spec)
                envelope_center = _add(
                    spec.center,
                    _mul(_unit(spec.axis), axial_offset),
                )
                keepouts.append(
                    _joint_envelope(
                        envelope_center,
                        spec.axis,
                        radius,
                        length,
                        0.0,
                    )
                )

        for spec in secondary_hosted_joints.get(host_name, []):
            radius, length, axial_offset = _body_socket_envelope(spec)
            if host_name == "pelvis_core" and spec.name.endswith("_hip_pitch"):
                # Extend only the passive pelvis pocket far enough medially to
                # clear the grandparent hip-roll boot's sub-mm grazing contact.
                length = 100.6
            envelope_center = _add(
                spec.center,
                _mul(_unit(spec.axis), axial_offset),
            )
            keepouts.append(
                _joint_envelope(
                    envelope_center,
                    spec.axis,
                    radius,
                    length,
                    0.0,
                )
            )

            if host_name.startswith("forearm_") and spec.name.endswith("_wrist_pitch"):
                keepouts.append(Sphere(45.0).moved(Location(spec.center)))

        keepouts.extend(swept_host_keepouts.get(host_name, []))

        # A pelvis, thorax, or palm can host several joints; trim every simple
        # analytic envelope from the unfragmented host in one operation.
        if keepouts:
            host = _socket_trim_many(
                host,
                keepouts,
                preunion=host_name in swept_host_keepouts,
            )

        raw_parts[host_name] = host

    for name, part in raw_parts.items():
        parts[name] = asm.add(part, name)

    # Fixed side owns the native RevoluteJoint.  The moving side owns a RigidJoint
    # at the identical world frame; angle=0 preserves the authored athletic pose.
    for spec in all_joints:
        fixed_part = parts[spec.fixed]
        moving_part = parts[spec.moving]
        axis = Axis(spec.center, spec.axis)
        fixed_frame = asm.revolute_frame(
            fixed_part,
            f"{spec.name}_axis",
            axis,
            angular_range=spec.limits,
        )
        fixed_joint_location = fixed_part.joints[fixed_frame.frame].location
        follower_location = Location(
            tuple(fixed_joint_location.position),
            tuple(fixed_joint_location.orientation),
        )
        moving_frame = asm.rigid_frame(
            moving_part,
            f"{spec.name}_follower",
            follower_location,
        )
        asm.revolute(
            fixed_frame,
            moving_frame,
            angle=0.0,
            label=spec.name,
        )

    root = asm.build()
    root.dof_summary = {
        "body": 28,
        "left_hand": 15,
        "right_hand": 15,
        "total_revolute": 58,
    }
    root.coordinate_convention = "+X left, +Y forward, +Z up, floor Z=0"
    return root


if __name__ == "__main__":
    model = gen_step()
    print(
        "sculpted_humanoid",
        f"children={len(model.children)}",
        f"mates={len(model.assembly_mates)}",
        f"bbox={model.bounding_box().size}",
    )
