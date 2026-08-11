"""Shared finishing vocabulary for the chronograph build.

Every builder uses these helpers so anglage width, screw geometry, jewel
countersinks, snailing, striping, and perlage read as one hand across the
whole movement. All dimensions default from `_spec`.

Conventions: build123d algebra mode; parts returned in their own local
frame, +Z up; caller positions them. Colors from `_spec`.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    BuildLine,
    BuildSketch,
    Circle,
    Color,
    Cone,
    Cylinder,
    Mode,
    Part,
    Plane,
    Polygon,
    Pos,
    Rot,
    Sphere,
    Spline,
    chamfer,
    extrude,
    fillet,
    make_face,
    revolve,
)

import _spec as S


# ---------------------------------------------------------------------------
# Safe edge finishing (sub-mm chamfer/fillet with a retry ladder).
# OCC can throw or emit degenerate geometry on tiny edge ops after booleans;
# every failure is retried at reduced width, then skipped. Callers that MUST
# see a bevel should apply it before booleans where possible.
# ---------------------------------------------------------------------------

def safe_chamfer(part: Part, edges, length: float, min_length: float = 0.04):
    """Chamfer `edges`, retrying at 0.7x steps down to min_length; on total
    failure returns the part unchanged. Returns (part, applied_length|None)."""
    width = length
    edge_list = list(edges)
    if not edge_list:
        return part, None
    while width >= min_length:
        try:
            result = chamfer(edge_list, length=width)
            if result.volume > 0:
                return result, width
        except Exception:
            pass
        # re-resolve nothing: edges belong to `part`'s topology; retry smaller
        width *= 0.7
    return part, None


def safe_fillet(part: Part, edges, radius: float, min_radius: float = 0.04):
    """Fillet with the same retry ladder as safe_chamfer."""
    r = radius
    edge_list = list(edges)
    if not edge_list:
        return part, None
    while r >= min_radius:
        try:
            result = fillet(edge_list, radius=r)
            if result.volume > 0:
                return result, r
        except Exception:
            pass
        r *= 0.7
    return part, None


def anglage_top(part: Part, width: float = S.ANGLAGE_WIDTH, z_tol: float = 1e-4):
    """Polished 45-degree bevel along every edge of the part's top face
    perimeter (the classic bridge/lever anglage). Selects edges belonging to
    the highest planar region. Returns (part, applied|None)."""
    top_z = part.bounding_box().max.Z
    edges = [
        e
        for e in part.edges()
        if abs(e.bounding_box().max.Z - top_z) < z_tol
        and abs(e.bounding_box().min.Z - top_z) < z_tol
    ]
    return safe_chamfer(part, edges, width)


# ---------------------------------------------------------------------------
# Screws
# ---------------------------------------------------------------------------

def slotted_screw(
    head_diameter: float = S.SCREW_HEAD_DIAMETER,
    head_height: float = 0.34,
    shank_diameter: float | None = None,
    shank_length: float = 0.8,
    slot_width: float = S.SCREW_SLOT_WIDTH,
    slot_depth: float = S.SCREW_SLOT_DEPTH,
    color: tuple = S.BLUED,
    domed: bool = True,
) -> Part:
    """Polished slotted screw, head top at z=0, shank hanging below.

    The head is a short cylinder with (optionally) a domed top, a chamfered
    rim, and a single slot with chamfered slot edges — the auction-macro
    read: crisp slot, mirror head, blued color.
    """
    if shank_diameter is None:
        shank_diameter = head_diameter * 0.55
    r = head_diameter / 2.0

    head = Cylinder(r, head_height, align=(None, None, None))
    head = Pos(0, 0, -head_height / 2) * head
    if domed:
        dome_r = r * 2.6
        dome = Sphere(dome_r)
        dome = Pos(0, 0, -math.sqrt(dome_r**2 - r**2)) * dome
        head = head & dome
    # chamfered lower rim so the head sits in a screw sink with a light ring
    head, _ = safe_chamfer(
        head,
        [e for e in head.edges() if abs(e.bounding_box().min.Z + head_height) < 1e-4],
        0.05,
    )

    slot_bar = Pos(0, 0, -slot_depth / 2 + 0.001) * _box(
        head_diameter * 1.2, slot_width, slot_depth + 0.002
    )
    head = head - slot_bar

    shank = Pos(0, 0, -head_height - shank_length / 2) * Cylinder(
        shank_diameter / 2, shank_length, align=(None, None, None)
    )
    screw = head + shank
    screw.color = Color(*color)
    return screw


def _box(x: float, y: float, z: float) -> Part:
    from build123d import Box

    return Box(x, y, z, align=(None, None, None))


# ---------------------------------------------------------------------------
# Jewels
# ---------------------------------------------------------------------------

def jewel(
    diameter: float = S.JEWEL_DIAMETER,
    thickness: float = 0.4,
    domed: bool = True,
    color: tuple = S.RUBY,
) -> Part:
    """Ruby jewel disk, top surface at z=0. Slightly domed top face."""
    r = diameter / 2.0
    body = Pos(0, 0, -thickness / 2) * Cylinder(r, thickness, align=(None, None, None))
    if domed:
        dome_r = r * 3.2
        dome = Pos(0, 0, -math.sqrt(dome_r**2 - r**2)) * Sphere(dome_r)
        body = body & dome
        body = Pos(0, 0, 0.06) * body
    body.color = Color(*color)
    return body


def jewel_countersink_cut(
    diameter: float = S.JEWEL_COUNTERSINK_DIAMETER,
    depth: float = S.JEWEL_COUNTERSINK_DEPTH,
    through_diameter: float | None = None,
    through_depth: float = 3.0,
) -> Part:
    """Cutter for a polished jewel countersink: a shallow cone-walled recess
    plus the jewel seat bore. Subtract from a plate/bridge with the target
    surface at z=0 (cut extends downward)."""
    if through_diameter is None:
        through_diameter = S.JEWEL_DIAMETER - 0.1
    r_top = diameter / 2.0
    r_seat = S.JEWEL_DIAMETER / 2.0 + 0.05
    cone = Pos(0, 0, -depth / 2 + 0.001) * Cone(
        r_top, r_seat, depth, align=(None, None, None)
    )
    seat = Pos(0, 0, -depth - 0.35) * Cylinder(r_seat, 0.75, align=(None, None, None))
    bore = Pos(0, 0, -through_depth / 2) * Cylinder(
        through_diameter / 2, through_depth, align=(None, None, None)
    )
    return cone + seat + bore


def jeweled_bearing(
    surface_z: float = 0.0,
    jewel_diameter: float = S.JEWEL_DIAMETER,
) -> Part:
    """Jewel positioned for a countersink cut made with jewel_countersink_cut
    at the same XY: returns the ruby sitting just below the surface."""
    j = jewel(jewel_diameter)
    return Pos(0, 0, surface_z - S.JEWEL_COUNTERSINK_DEPTH - 0.02) * j


# ---------------------------------------------------------------------------
# Surface finishing textures (geometric, macro-visible)
# ---------------------------------------------------------------------------

def snailing_cutter(
    outer_diameter: float,
    inner_diameter: float = 0.0,
    pitch: float = S.SNAIL_PITCH,
    groove_depth: float = 0.06,
    groove_width: float | None = None,
) -> Part:
    """Concentric V-groove cutter for snailed wheels/subdials. Subtract with
    the finished surface at z=0; grooves cut downward.

    V-section rings (not flat-bottomed slots): the finished surface becomes
    a train of sloped facets, so every ring catches the studio light at a
    different angle — that alternating sheen IS the macro read of snailing.
    Flat-bottomed grooves stay invisible inside one big specular pool
    (measured on the sampler coupon)."""
    if groove_width is None:
        groove_width = pitch * 0.95  # nearly no flat land between rings
    rings = []
    r = max(inner_diameter / 2.0 + pitch, pitch)
    while r < outer_diameter / 2.0:
        w = groove_width / 2.0
        profile = Plane.XZ * Polygon(
            (r - w, 0.02), (r + w, 0.02), (r, -groove_depth), align=None
        )
        rings.append(revolve(profile, Axis.Z))
        r += pitch
    if not rings:
        return _box(0.001, 0.001, 0.001)
    return rings[0] + rings[1:]


def geneva_stripes_cutter(
    span_x: float,
    span_y: float,
    pitch: float = S.GENEVA_STRIPE_PITCH,
    depth: float = 0.055,
    arc_radius: float = 60.0,
) -> Part:
    """Geneva striping cutter covering a span_x x span_y region centered at
    the origin. Subtract with the striped surface at z=0.

    Each stripe band's top face is left tilted alternately +/-`tilt_deg`
    about Y, meeting its neighbors in crisp ridge/valley lines. Alternating
    facet normals give adjacent bands opposing sheen under one light — the
    photographic signature of cotes de Geneve. (Shallow arc-bottom grooves
    with flats between read as one flat blown-out surface — measured.)

    `depth`/`arc_radius` retained for signature compatibility; tilt drives
    the geometry.
    """
    tilt_deg = 2.0
    tilt = math.radians(tilt_deg)
    n = int(span_x / pitch) + 3
    pieces = []
    x0 = -((n - 1) / 2.0) * pitch
    band_w = pitch * 1.08
    drop = (band_w / 2.0) * math.tan(tilt) + 0.006
    for i in range(n):
        x = x0 + i * pitch
        sign = 1.0 if i % 2 == 0 else -1.0
        piece = _box(band_w, span_y * 1.3, 1.0)
        piece = Rot(0, sign * tilt_deg, 0) * piece
        piece = Pos(x, 0, 0.5 - drop) * piece
        pieces.append(piece)
    return pieces[0] + pieces[1:]


def perlage_cutter(
    span_x: float,
    span_y: float,
    stamp_diameter: float = S.PERLAGE_DIAMETER,
    depth: float = 0.035,
    gap: float = 0.05,
) -> list:
    """Circular-graining stamps for a main-plate field, returned as a LIST
    of disjoint sphere cutters for ONE multi-tool subtract:

        plate = plate - F.perlage_cutter(...)

    Stamps are hex-packed with a small gap. Overlapping (true) perlage
    couples every sphere into one giant intersection network and takes
    OCC minutes to hours — measured — so we pack tangent-with-gap, which
    still reads as perlage at macro render scale. Do NOT fuse this list.
    """
    step = stamp_diameter + gap
    row_step = step * 0.8660  # hex packing
    r_stamp = stamp_diameter / 2.0
    sphere_r = (r_stamp**2 + depth**2) / (2 * depth)
    # ONE small lens-cap prototype (sphere bitten by the stamp cylinder,
    # kept just above/below z=0), then cheap translated copies. Full
    # spheres are ~15 mm radius and all overlap far below the surface,
    # which couples every tool into one giant boolean — measured minutes.
    proto = Pos(0, 0, sphere_r - depth) * Sphere(sphere_r) & Cylinder(
        r_stamp + 0.02, 2 * depth + 0.2, align=(None, None, None)
    )
    nx = int(span_x / step) + 2
    ny = int(span_y / row_step) + 2
    stamps = []
    for j in range(ny):
        for i in range(nx):
            x = -span_x / 2 + i * step + (step / 2 if j % 2 else 0)
            y = -span_y / 2 + j * row_step
            stamps.append(Pos(x, y, 0) * proto)
    return stamps


# ---------------------------------------------------------------------------
# Wheels and pinions
# ---------------------------------------------------------------------------

def train_wheel(
    tooth_count: int,
    outer_diameter: float,
    web_thickness: float = 0.18,
    rim_width_frac: float = 0.10,
    spoke_count: int = 5,
    hub_diameter: float | None = None,
    color: tuple = S.GILT,
    tooth_depth_frac: float = 0.12,
) -> Part:
    """Gilded going-train wheel: toothed ring, thin rim, crossed-out web
    with `spoke_count` arms, centered at origin, mid-plane z=0.

    Teeth are rounded triangular (epicycloid read at macro scale) cut by
    polar pattern.
    """
    r_o = outer_diameter / 2.0
    tooth_h = r_o * tooth_depth_frac
    r_root = r_o - tooth_h
    if hub_diameter is None:
        hub_diameter = max(1.4, outer_diameter * 0.14)
    rim_inner = r_root - outer_diameter * rim_width_frac

    # single 2D sketch: root circle + tapered round-tipped teeth, fused in
    # sketch space (2D booleans are cheap at any tooth count), one extrude
    tooth_w = 2 * math.pi * r_root / tooth_count * 0.36
    tip_r = tooth_w * 0.24
    tooth_2d = Polygon(
        (r_root - 0.05, -tooth_w / 2),
        (r_root - 0.05, tooth_w / 2),
        (r_o - tip_r, tip_r),
        (r_o - tip_r, -tip_r),
        align=None,
    ) + Pos(r_o - tip_r, 0) * Circle(tip_r)
    profile = Circle(r_root) + [
        Rot(0, 0, 360.0 * k / tooth_count) * tooth_2d for k in range(tooth_count)
    ]
    wheel = extrude(profile, amount=web_thickness / 2, both=True)

    # cross out the web: keep rim ring + spokes + hub (spoke_count=0 keeps
    # a full web, e.g. for snailed ratchet wheels)
    if spoke_count > 0:
        cut_ring = Cylinder(
            rim_inner, web_thickness + 0.02, align=(None, None, None)
        ) - Cylinder(
            hub_diameter / 2 + 0.4, web_thickness + 0.04, align=(None, None, None)
        )
        spokes = None
        spoke_w = max(0.5, outer_diameter * 0.045)
        for k in range(spoke_count):
            ang = 360.0 * k / spoke_count
            s = Rot(0, 0, ang) * _box(rim_inner * 2.05, spoke_w, web_thickness + 0.06)
            spokes = s if spokes is None else spokes + s
        wheel = wheel - (cut_ring - spokes)

    wheel.color = Color(*color)
    return wheel


def pinion(
    leaf_count: int,
    outer_diameter: float,
    length: float,
    color: tuple = S.STEEL_DARK,
) -> Part:
    """Polished-steel pinion with `leaf_count` rounded leaves, axis Z,
    mid-plane z=0."""
    r_o = outer_diameter / 2.0
    r_root = r_o * 0.62
    body = Cylinder(r_root, length, align=(None, None, None))
    leaf_w = 2 * math.pi * r_root / leaf_count * 0.5
    proto = Pos(r_root * 0.75, 0, 0) * _box(
        r_o - r_root * 0.4, leaf_w, length
    ) + Pos(r_o - leaf_w / 4, 0, 0) * Cylinder(
        leaf_w / 2, length, align=(None, None, None)
    )
    leaves = [Rot(0, 0, 360.0 * k / leaf_count) * proto for k in range(leaf_count)]
    p = body + leaves
    p.color = Color(*color)
    return p


# ---------------------------------------------------------------------------
# Heart cam (chronograph reset)
# ---------------------------------------------------------------------------

def heart_cam(
    diameter: float = 3.2,
    thickness: float = 0.5,
    bore: float = 0.5,
    color: tuple = S.STEEL_BRIGHT,
) -> Part:
    """Classic polished heart-shaped reset cam, point at +Y, axis Z,
    bottom at z=0. The heart spiral profile is drawn with splines so the
    hammer face reads as a continuous polished curve."""
    r = diameter / 2.0
    pts_right = [
        (0.0, r),               # tip
        (0.36 * r, 0.55 * r),
        (0.52 * r, 0.0),
        (0.42 * r, -0.55 * r),
        (0.0, -0.78 * r),
    ]
    with BuildSketch() as sk:
        with BuildLine():
            Spline(*pts_right)
            Spline((0.0, -0.78 * r), (-0.42 * r, -0.55 * r), (-0.52 * r, 0.0),
                   (-0.36 * r, 0.55 * r), (0.0, r))
        make_face()
        Circle(bore / 2, mode=Mode.SUBTRACT)
    cam = extrude(sk.sketch, amount=thickness)
    cam.color = Color(*color)
    return cam


__all__ = [
    "safe_chamfer",
    "safe_fillet",
    "anglage_top",
    "slotted_screw",
    "jewel",
    "jewel_countersink_cut",
    "jeweled_bearing",
    "snailing_cutter",
    "geneva_stripes_cutter",
    "perlage_cutter",
    "train_wheel",
    "pinion",
    "heart_cam",
]


def straight_grain_cutter(
    span_x: float,
    span_y: float,
    pitch: float = 0.14,
    depth: float = 0.018,
    along_x: bool = True,
) -> list:
    """Directional brushed-grain cutter: fine parallel V-grooves covering a
    span_x x span_y field centered at the origin, grooves running along X
    (along_x=True) or Y. Returns a LIST of disjoint prism tools for ONE
    multi-tool subtract with the finished surface at z=0 (grooves cut down).

    The V-section (no flat land) makes every groove flank a sloped facet, so
    the field shows the anisotropic light response of satin brushing at
    render scale — same principle as snailing_cutter/geneva stripes. Keep
    fields per-part (clip by intersecting the target before subtracting is
    unnecessary; overshoot is fine since tools only cut where they overlap).
    """
    length = (span_x if along_x else span_y) * 1.15
    across = span_y if along_x else span_x
    w = pitch * 0.5
    proto = Plane.XZ * Polygon((-w, 0.02), (w, 0.02), (0.0, -depth), align=None)
    proto = extrude(proto, amount=length / 2, both=True)
    if along_x:
        proto = Rot(0, 0, 90) * proto  # groove axis along X
    n = int(across / pitch) + 2
    tools = []
    for i in range(n):
        off = -across / 2 + i * pitch
        tools.append(Pos(0, off, 0) * proto if along_x else Pos(off, 0, 0) * proto)
    return tools
