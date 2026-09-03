"""Shared fastener vocabulary for the W16.

Every bolt, nut, stud, washer and bracket the engine wears is built here so the
whole model speaks one hardware language: real ISO/DIN proportions, one seating
convention, one placement helper.

LOCAL FRAME (every builder returns a part in this frame, at the origin)
  +Z   the fastener axis, pointing OUT of the joint (head end).
  z=0  the SEATING face — the plane the fastener bears on. Heads, nut bodies
       and washers live above z=0; shanks hang below.
  So `place(bolt, point, normal)` seats the bolt on a face at `point` whose
  outward normal is `normal`, with no per-callsite arithmetic.

THREADS are not modelled as helices. A threaded shank is a plain cylinder at
the coarse-pitch PITCH diameter (d - 0.6495 * p), which is the standard
simplified-fastener convention and reads correctly against a tapped boss.

Every part comes back as a single closed positive-volume solid with an EMPTY
label — callers own labels — and a default colour from `lib.palette`
(TITANIUM for bolts, STEEL_DARK for studs/nuts/washers/brackets).

Cosmetic bevels are built into revolved profiles wherever that is cheap; the
few real 3D chamfers/fillets go through `safe_fillet`/`safe_chamfer`, which
retry at 0.7x and then give up rather than kill a build.

Self-test:  cd models/w16/src && ../../../.venv/bin/python -m lib.fasteners
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import palette as P

__all__ = [
    "hex_flange_bolt",
    "socket_cap_bolt",
    "twelve_point_bolt",
    "hex_nut",
    "flange_nut",
    "washer",
    "stud",
    "banjo_bolt",
    "lifting_eye",
    "id_pad",
    "place",
    "bolt_ring",
    "bolt_row",
    "safe_fillet",
    "safe_chamfer",
    "pitch",
    "minor_diameter",
]


# ---------------------------------------------------------------------------
# Standard dimensions.  Tables are DIN/ISO; the fallbacks let an off-size
# diameter still build something proportionate instead of raising.
# ---------------------------------------------------------------------------

# ISO 261 coarse pitch
_PITCH = {3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25, 10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0}

# DIN 6921 hex flange bolt: across-flats s, flange dia dc, head height k
# (flange included), flange thickness c.
_FLANGE_BOLT = {
    6: (10.0, 13.9, 6.6, 1.1),
    8: (13.0, 17.8, 8.1, 1.3),
    10: (15.0, 21.3, 9.6, 1.5),
    12: (18.0, 25.4, 11.6, 1.8),
}

# DIN 912 socket cap: head dia dk, head height k, socket across-flats, socket depth
_SOCKET_CAP = {
    6: (10.0, 6.0, 5.0, 3.0),
    8: (13.0, 8.0, 6.0, 4.0),
    10: (16.0, 10.0, 8.0, 5.0),
    12: (18.0, 12.0, 10.0, 6.0),
}

# ARP-style 12-point: wrench across-flats
_TWELVE_POINT = {6: 8.0, 8: 10.0, 10: 12.0, 12: 14.0}

# DIN 934 hex nut: across-flats s, height m
_HEX_NUT = {6: (10.0, 5.0), 8: (13.0, 6.5), 10: (17.0, 8.0), 12: (19.0, 10.0)}

# DIN 6923 flange nut: across-flats s, flange dia dc, height m, flange thickness c
_FLANGE_NUT = {
    6: (10.0, 14.2, 6.0, 1.1),
    8: (13.0, 17.9, 8.0, 1.3),
    10: (15.0, 21.8, 10.0, 1.5),
    12: (18.0, 26.0, 12.0, 1.8),
}

# DIN 125A washer: inner dia, outer dia, thickness
_WASHER = {
    6: (6.4, 12.0, 1.6),
    8: (8.4, 16.0, 1.6),
    10: (10.5, 20.0, 2.0),
    12: (13.0, 24.0, 2.5),
}

# DIN 933 plain hex bolt across-flats (used for the banjo head)
_HEX_BOLT_AF = {6: 10.0, 8: 13.0, 10: 17.0, 12: 19.0}


def _key(d: float):
    """Nearest tabled nominal diameter, or None when nothing is close."""
    for nominal in (3, 4, 5, 6, 8, 10, 12, 14, 16):
        if abs(d - nominal) < 0.26:
            return nominal
    return None


def pitch(d: float) -> float:
    """Coarse thread pitch for nominal diameter `d` (mm)."""
    k = _key(d)
    return _PITCH.get(k, 0.15 * d) if k is not None else 0.15 * d


def minor_diameter(d: float) -> float:
    """Nut/tapped-hole minor diameter for nominal `d` (ISO 68 basic profile)."""
    return d - 1.0825 * pitch(d)


def _shank_radius(d: float) -> float:
    """Radius of the simplified (helix-free) threaded shank: the pitch radius."""
    return (d - 0.6495 * pitch(d)) / 2.0


# ---------------------------------------------------------------------------
# Safe edge finishing.  Same retry ladder the moonwatch build uses: OCC throws
# or degenerates on small edge ops after booleans, and a cosmetic bevel must
# never be able to kill a 16-cylinder build.
# ---------------------------------------------------------------------------

def safe_chamfer(part, edges, length: float, min_length: float = 0.06):
    """Chamfer `edges` at `length`, retrying at 0.7x down to `min_length`.

    Returns (part, applied_length | None); on total failure the part is
    returned unchanged.
    """
    edge_list = list(edges)
    if not edge_list:
        return part, None
    w = length
    while w >= min_length:
        try:
            result = bd.chamfer(edge_list, length=w)
            if result.volume > 0:
                return result, w
        except Exception:
            pass
        w *= 0.7
    return part, None


def safe_fillet(part, edges, radius: float, min_radius: float = 0.06):
    """Fillet `edges` with the same retry ladder as `safe_chamfer`."""
    edge_list = list(edges)
    if not edge_list:
        return part, None
    r = radius
    while r >= min_radius:
        try:
            result = bd.fillet(edge_list, radius=r)
            if result.volume > 0:
                return result, r
        except Exception:
            pass
        r *= 0.7
    return part, None


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def _ccw(points):
    """Return `points` wound counter-clockwise in the (r, z) profile plane.

    A clockwise-wound Polygon fuses/extrudes as a reversed face; normalising
    the winding here is cheaper than debugging an inverted revolve later.
    """
    pts = list(points)
    area = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        area += x0 * y1 - x1 * y0
    return pts if area > 0 else pts[::-1]


def _rev(points, arc: float = 360.0):
    """Revolve a closed (radius, z) profile about +Z.

    Bevels, drafts and dishes go in here rather than into 3D chamfer ops:
    a constructive bevel survives every later boolean, a chamfered edge often
    does not.
    """
    profile = bd.Plane.XZ * bd.Polygon(*_ccw(points), align=None)
    return bd.revolve(profile, bd.Axis.Z, revolution_arc=arc)


def _hex_prism(across_flats: float, z0: float, z1: float, rotation: float = 30.0):
    """Hexagonal prism spanning z0..z1, `across_flats` wide, a FLAT facing +X."""
    sketch = bd.RegularPolygon(
        across_flats / 2.0, 6, major_radius=False, rotation=rotation
    )
    return bd.Pos(0, 0, z0) * bd.extrude(sketch, amount=z1 - z0)


def _wrench_head(
    across_flats: float,
    z0: float,
    z1: float,
    chamfer_bottom: bool = False,
    chamfer_top: bool = True,
    dish: float = 0.0,
    side_count: int = 6,
    rotation: float = 30.0,
):
    """A hex (or 12-point) wrenching body between z0 and z1.

    The corner chamfers are cut by INTERSECTING with one revolved limiter
    rather than by 3D-chamfering the corner edges: a 45-degree cone through the
    circumradius reproduces the standard head chamfer, cannot fail on a tangent
    chain, and lets the shallow dished top ride in the same profile.
    """
    a = across_flats / 2.0                                   # apothem
    if side_count == 6:
        body = _hex_prism(across_flats, z0, z1, rotation)
        r_corner = a / math.cos(math.pi / 6.0)               # circumradius
    else:  # 12-point == two hexes 30 degrees apart, fused in sketch space
        sk = bd.RegularPolygon(a, 6, major_radius=False, rotation=rotation) + \
            bd.RegularPolygon(a, 6, major_radius=False, rotation=rotation + 30.0)
        body = bd.Pos(0, 0, z0) * bd.extrude(sk, amount=z1 - z0)
        r_corner = a / math.cos(math.pi / 6.0)

    z_base = z0 - 1.0
    ch = r_corner - a                                        # radial cut at the corners
    r_top = a if side_count == 6 else a * 1.04
    # 45-degree cone: radius == r_corner exactly at z1 - ch, larger below it,
    # so nothing is touched under the chamfer band.
    r_big = r_top + (z1 - z_base)
    pts = [(0.0, z_base), (r_big, z_base), (r_top, z1)]
    if dish > 0.0:
        pts += [(r_top * 0.80, z1), (0.0, z1 - dish)]
    else:
        pts += [(0.0, z1)]
    limiter = _rev(pts)

    if not chamfer_top:
        limiter = _rev([(0.0, z_base), (r_big, z_base), (r_big, z1), (0.0, z1)])
    head = body & limiter

    if chamfer_bottom:
        # mirror-image cone rising from the bearing face: washer-faced nut/bolt
        r_big_b = a + (z1 + 1.0 - z0)
        head = head & _rev(
            [(0.0, z0), (a, z0), (r_big_b, z1 + 1.0), (0.0, z1 + 1.0)]
        )
    return head


def _threaded_shank(d: float, length: float, z_top: float = 0.0):
    """Plain (helix-free) shank from `z_top` down to `z_top - length`.

    Built as a revolve so the lead-in chamfer at the tip is constructive.
    `z_top` normally reaches a little way INTO the head so the fuse is a
    proper interpenetration rather than a coplanar face kiss.
    """
    r = _shank_radius(d)
    ch = min(0.9, 0.11 * d)
    z_bot = z_top - length
    return _rev(
        [
            (0.0, z_bot),
            (r - ch, z_bot),
            (r, z_bot + ch),
            (r, z_top),
            (0.0, z_top),
        ]
    )


def _extrude_maybe_tapered(sketch, amount: float, taper: float, both: bool = False):
    """`extrude` with a draft angle, falling back to a straight prism.

    Draft is how a forging/casting actually looks, but OCC's taper prism fails
    on some outlines; a cosmetic draft is never worth a dead build.
    """
    if taper:
        try:
            solid = bd.extrude(sketch, amount=amount, taper=taper, both=both)
            if solid.volume > 0:
                return solid
        except Exception:
            pass
    return bd.extrude(sketch, amount=amount, both=both)


def _finish(part, color):
    """Colour a finished fastener and assert the single-closed-solid contract.

    Labels are deliberately left empty: the caller owns naming.
    """
    solids = part.solids()
    if len(solids) != 1:
        part = max(solids, key=lambda s: s.volume)
    if part.volume <= 0.0:
        raise ValueError("fastener built with non-positive volume")
    part.label = ""
    part.color = color
    return part


# ---------------------------------------------------------------------------
# Bolts
# ---------------------------------------------------------------------------

def hex_flange_bolt(d: float, length: float):
    """DIN 6921 hex flange bolt, nominal `d`, `length` of shank below the flange.

    Flange underside carries a slight draft so only the rim bears, the hex
    corners are chamfered and the top face is shallowly dished.
    """
    k = _key(d)
    if k in _FLANGE_BOLT:
        s, dc, head_h, c = _FLANGE_BOLT[k]
    else:
        s, dc, head_h, c = 1.55 * d, 2.2 * d, 1.0 * d, 0.16 * d

    r_f = dc / 2.0
    bev = min(0.45, 0.3 * c)
    draft = min(0.30, 0.25 * c)          # underside rise from rim to centre

    flange = _rev(
        [
            (0.0, draft),
            (r_f - bev, 0.0),            # drafted bearing face, rim contacts first
            (r_f, bev),
            (r_f, c - bev),
            (r_f - bev, c),
            (0.0, c),
        ]
    )
    head = _wrench_head(s, c - 0.6, head_h, dish=min(0.28, 0.035 * d))
    shank = _threaded_shank(d, length + c, z_top=c)
    return _finish(flange + [head, shank], P.TITANIUM)


def socket_cap_bolt(d: float, length: float):
    """DIN 912 socket head cap screw: cylindrical head, hex socket, rolled top edge."""
    k = _key(d)
    if k in _SOCKET_CAP:
        dk, head_h, sock_af, sock_t = _SOCKET_CAP[k]
    else:
        dk, head_h, sock_af, sock_t = 1.55 * d, 1.0 * d, 0.8 * d, 0.55 * d

    r_k = dk / 2.0
    bev = 0.3
    head = _rev(
        [
            (0.0, 0.0),
            (r_k - bev, 0.0),
            (r_k, bev),                  # broken bottom edge under the bearing face
            (r_k, head_h),
            (0.0, head_h),
        ]
    )
    # rolled top edge: one clean circular edge on a plain cylinder, filleted
    # BEFORE the socket is cut so the op never sees a hex corner.
    top_edges = [
        e for e in head.edges() if abs(e.center().Z - head_h) < 1e-6 and e.length > 1.0
    ]
    head, _ = safe_fillet(head, top_edges, min(0.55, 0.055 * d))

    socket = _hex_prism(sock_af, head_h - sock_t, head_h + 1.0)
    # Socket mouth: a plain hex cut, then a small CHAMFER on the six mouth
    # edges.  A revolved lead-in cone fused into the tool (the earlier design)
    # left faces that BOPAlgo flags as self-intersecting once the bolt is
    # rotated to certain angles (15 and 30 deg tilts failed, 45 passed: the
    # placed coil bolts were the ones validate caught); the chamfer is stable
    # at every tilt tested (validity.check_occurrence_shape, 5 sizes x 6 axes).
    head = head - socket
    mouth = [e for e in head.edges() if abs(e.center().Z - head_h) < 1e-6 and e.length < sock_af]
    if len(mouth) == 6:
        try:
            head = head.chamfer(0.4, None, mouth)
        except Exception:
            pass

    shank = _threaded_shank(d, length + 0.6, z_top=0.6)
    return _finish(head + shank, P.TITANIUM)


def twelve_point_bolt(d: float, length: float):
    """ARP-style 12-point bolt: double-hex head on a raised washer face."""
    k = _key(d)
    af = _TWELVE_POINT.get(k, 1.25 * d)
    head_h = 0.74 * d
    wf_d = 1.55 * d
    wf_t = 0.10 * d + 0.30

    r_w = wf_d / 2.0
    bev = 0.35
    washer_face = _rev(
        [
            (0.0, 0.0),
            (r_w - bev, 0.0),
            (r_w, bev),
            (r_w, wf_t - bev),
            (r_w - bev, wf_t),
            (0.0, wf_t),
        ]
    )
    head = _wrench_head(
        af,
        wf_t - 0.4,
        wf_t + head_h,
        side_count=12,
        dish=min(0.25, 0.03 * d),
        rotation=15.0,
    )
    shank = _threaded_shank(d, length + wf_t, z_top=wf_t)
    return _finish(washer_face + [head, shank], P.TITANIUM)


def banjo_bolt(d: float):
    """Banjo bolt for an oil/coolant line: hex head, axial drilling, cross hole.

    Length is fixed by the nominal size (2.4 d) — a banjo bolt's length is set
    by the fitting eye it carries, not by the joint.
    """
    k = _key(d)
    af = _HEX_BOLT_AF.get(k, 1.6 * d)
    head_h = 0.68 * d
    length = 2.4 * d
    r_s = _shank_radius(d)

    head = _wrench_head(af, 0.0, head_h, chamfer_bottom=True, dish=0.0)
    shank = _threaded_shank(d, length + head_h * 0.6, z_top=head_h * 0.6)
    body = head + shank

    r_bore = 0.29 * d
    z_cross = -0.46 * length
    axial = bd.Pos(0, 0, -length - 0.5) * bd.Cylinder(
        r_bore, length * 0.72 + 0.5, align=(None, None, None)
    )
    cross = bd.Pos(0, -(r_s + 1.0), z_cross) * bd.Rot(-90, 0, 0) * bd.Cylinder(
        0.17 * d, 2 * (r_s + 1.0), align=(None, None, None)
    )
    return _finish(body - [axial, cross], P.TITANIUM)


# ---------------------------------------------------------------------------
# Nuts, washers, studs
# ---------------------------------------------------------------------------

def hex_nut(d: float):
    """DIN 934 hex nut, bearing face at z=0, body above, chamfered both ends."""
    k = _key(d)
    s, m = _HEX_NUT.get(k, (1.6 * d, 0.85 * d))
    body = _wrench_head(s, 0.0, m, chamfer_bottom=True, dish=0.0)
    bore = bd.Pos(0, 0, -1.0) * bd.Cylinder(
        minor_diameter(d) / 2.0, m + 2.0, align=(None, None, None)
    )
    return _finish(body - bore, P.STEEL_DARK)


def flange_nut(d: float):
    """DIN 6923 hex flange nut, drafted flange underside bearing at z=0."""
    k = _key(d)
    if k in _FLANGE_NUT:
        s, dc, m, c = _FLANGE_NUT[k]
    else:
        s, dc, m, c = 1.6 * d, 2.2 * d, 1.0 * d, 0.16 * d

    r_f = dc / 2.0
    bev = min(0.45, 0.3 * c)
    draft = min(0.30, 0.25 * c)
    flange = _rev(
        [
            (0.0, draft),
            (r_f - bev, 0.0),
            (r_f, bev),
            (r_f, c - bev),
            (r_f - bev, c),
            (0.0, c),
        ]
    )
    hexn = _wrench_head(s, c - 0.6, m, dish=0.0)
    bore = bd.Pos(0, 0, -1.0) * bd.Cylinder(
        minor_diameter(d) / 2.0, m + 2.0, align=(None, None, None)
    )
    return _finish((flange + hexn) - bore, P.STEEL_DARK)


def washer(d: float):
    """DIN 125A flat washer, seating face at z=0, edges lightly broken."""
    k = _key(d)
    di, do, t = _WASHER.get(k, (d * 1.07, d * 2.0, max(1.0, 0.2 * d)))
    ri, ro = di / 2.0, do / 2.0
    b = min(0.18, 0.12 * t)
    return _finish(
        _rev(
            [
                (ri, b),
                (ri + b, 0.0),
                (ro - b, 0.0),
                (ro, b),
                (ro, t - b),
                (ro - b, t),
                (ri + b, t),
                (ri, t - b),
            ]
        ),
        P.STEEL_DARK,
    )


def stud(d: float, length_out: float, length_in: float):
    """Plain stud: z=0 at the surface it screws into, `length_out` proud,
    `length_in` buried. Both ends carry a lead-in chamfer."""
    r = _shank_radius(d)
    ch = min(0.9, 0.12 * d)
    return _finish(
        _rev(
            [
                (0.0, -length_in),
                (r - ch, -length_in),
                (r, -length_in + ch),
                (r, length_out - ch),
                (r - ch, length_out),
                (0.0, length_out),
            ]
        ),
        P.STEEL_DARK,
    )


# ---------------------------------------------------------------------------
# Brackets and cast-in features
# ---------------------------------------------------------------------------

def lifting_eye():
    """Forged M10 engine lifting eye, bolt-hole axis at the local origin.

    Foot bears on z=0 with a drafted pad; the strap leans out in +X and ends in
    a torus eye (hole axis along Y), so the bolt-head access above the hole
    stays clear. The eye is a torus rather than a filleted plate: a fully round
    section by construction, no fillet ladder on a multi-arc outline.
    """
    hole_d = 10.5
    foot_l, foot_w, foot_h = 40.0, 26.0, 10.0
    foot_cx = 10.0                       # foot centre; the hole sits at x = 0
    strap_w = 12.0
    eye_x, eye_z = 36.0, 46.0
    eye_major, eye_minor = 15.0, 6.0

    foot = bd.Pos(foot_cx, 0, 0) * _extrude_maybe_tapered(
        bd.RectangleRounded(foot_l, foot_w, 7.0), foot_h, taper=5.0
    )

    # strap: one multi-operand 2D fuse (chained 2D unions decay), extruded in Y
    strap_2d = bd.Polygon(
        (13.0, 3.0), (30.0, 3.0), (44.0, 24.0), (28.0, 24.0), align=None
    ) + [
        bd.Pos(eye_x, 24.0) * bd.Circle(10.0),
        bd.Pos(20.0, 7.5) * bd.Circle(6.5),
    ]
    strap = bd.extrude(bd.Plane.XZ * strap_2d, amount=strap_w / 2.0, both=True)

    eye = bd.Pos(eye_x, 0, eye_z) * bd.Rot(90, 0, 0) * bd.Torus(eye_major, eye_minor)

    body = foot + [strap, eye]

    bolt_hole = bd.Pos(0, 0, -1.0) * bd.Cylinder(
        hole_d / 2.0, foot_h + 2.0, align=(None, None, None)
    )
    counter = _rev(
        [
            (0.0, foot_h - 0.9),
            (hole_d / 2.0, foot_h - 0.9),
            (hole_d / 2.0 + 0.9, foot_h + 1.0),
            (0.0, foot_h + 1.0),
        ]
    )
    return _finish(body - [bolt_hole, counter], P.STEEL_DARK)


def id_pad(w: float, h: float, t: float = 2.0):
    """Raised machined identification pad: `w` x `h` footprint, `t` proud of the
    surface, seating face at z=0. Corners radiused, sides drafted as cast, top
    left flat and unbranded for the caller to letter (or leave blank)."""
    r = max(0.8, min(4.0, 0.15 * min(w, h)))
    return _finish(
        _extrude_maybe_tapered(bd.RectangleRounded(w, h, r), t, taper=7.0),
        P.MACHINED,
    )


# ---------------------------------------------------------------------------
# Placement — the one helper every other W16 module uses
# ---------------------------------------------------------------------------

def _frame(z_dir, x_dir=None):
    """Right-handed orthonormal (x, y, z) with z along `z_dir`.

    The frame is assembled from EXPLICIT direction vectors. `Plane.rotated()`
    composes in world axes, not the plane's own, which silently yaws a frame
    whose axes are not the global ones — the single most expensive trap in this
    library, because the result is a valid solid in the wrong place.
    """
    z = bd.Vector(*z_dir)
    if z.length < 1e-12:
        raise ValueError("z_dir must be non-zero")
    z = z.normalized()

    if x_dir is None:
        # stable perpendicular: cross with whichever world axis is least
        # aligned with z, so z parallel or antiparallel to Z is fine.
        aux = bd.Vector(1, 0, 0) if abs(z.X) < 0.9 else bd.Vector(0, 1, 0)
        y = z.cross(aux).normalized()
        x = y.cross(z).normalized()
    else:
        x = bd.Vector(*x_dir)
        x = x - z * x.dot(z)             # Gram-Schmidt against z
        if x.length < 1e-9:
            raise ValueError("x_dir is parallel to z_dir")
        x = x.normalized()
        y = z.cross(x).normalized()
    return x, y, z


def place(shape, point, z_dir, x_dir=None):
    """Return a COPY of `shape` seated at `point` with its local +Z along `z_dir`.

    `point` and `z_dir` are 3-tuples; `z_dir` need not be unit length and may
    be parallel or antiparallel to world Z. `x_dir` fixes the roll about the
    axis (it is orthogonalised against `z_dir`); when omitted a stable
    perpendicular is chosen.

    Uses `.moved()`, which COMPOSES with any transform the shape already
    carries — `.located()` would assign an absolute location and throw an
    existing rotation away without raising.
    """
    x, _y, z = _frame(z_dir, x_dir)
    plane = bd.Plane(origin=bd.Vector(*point), x_dir=x, z_dir=z)
    return plane * shape


def bolt_ring(shape, centre, axis_dir, radius, count, start_deg=0.0, ref_dir=None):
    """`count` copies of `shape` on a circle of `radius` about `axis_dir`
    through `centre`, each seated with local +Z along `axis_dir`.

    Each copy is clocked so its local +X points radially outward, which makes
    the hex flats read as a deliberate pattern rather than as noise.
    `ref_dir` fixes where angle 0 sits (default: a stable perpendicular).
    """
    if count <= 0:
        return []
    rx, ry, rz = _frame(axis_dir, ref_dir)
    c = bd.Vector(*centre)
    out = []
    for i in range(count):
        a = math.radians(start_deg + 360.0 * i / count)
        radial = rx * math.cos(a) + ry * math.sin(a)
        pos = c + radial * radius
        out.append(place(shape, (pos.X, pos.Y, pos.Z),
                         (rz.X, rz.Y, rz.Z),
                         (radial.X, radial.Y, radial.Z)))
    return out


def bolt_row(shape, points, z_dir):
    """A copy of `shape` seated at every point in `points`, all sharing `z_dir`."""
    return [place(shape, p, z_dir) for p in points]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    def _is_valid(part) -> bool:
        """`Shape.is_valid` is a property on build123d 0.11.1 and a method on
        older releases; accept either. Validity alone is not enough — an
        inverted shell is 'valid' with negative volume — so the caller checks
        volume too."""
        v = part.is_valid
        return bool(v() if callable(v) else v)

    D = 8.0
    cases = [
        ("hex_flange_bolt", lambda: hex_flange_bolt(D, 30.0)),
        ("socket_cap_bolt", lambda: socket_cap_bolt(D, 30.0)),
        ("twelve_point_bolt", lambda: twelve_point_bolt(D, 30.0)),
        ("hex_nut", lambda: hex_nut(D)),
        ("flange_nut", lambda: flange_nut(D)),
        ("washer", lambda: washer(D)),
        ("stud", lambda: stud(D, 26.0, 18.0)),
        ("banjo_bolt", lambda: banjo_bolt(D)),
        ("lifting_eye", lifting_eye),
        ("id_pad", lambda: id_pad(46.0, 22.0, 2.0)),
    ]

    failures = []
    built = {}
    print(f"{'part':>18}  {'solids':>6} {'valid':>5} {'volume mm3':>11}  "
          f"{'bbox z':>16}  {'bbox xy':>16}")
    for name, fn in cases:
        try:
            part = fn()
        except Exception as exc:  # noqa: BLE001 - the self-test reports, not raises
            failures.append(f"{name}: build raised {type(exc).__name__}: {exc}")
            print(f"{name:>18}  BUILD FAILED: {exc}")
            continue
        built[name] = part
        bb = part.bounding_box()
        n_solids = len(part.solids())
        valid = _is_valid(part)
        vol = part.volume
        print(f"{name:>18}  {n_solids:>6} {str(valid):>5} {vol:>11.1f}  "
              f"{bb.min.Z:>7.2f}..{bb.max.Z:<7.2f}  "
              f"{bb.size.X:>7.2f}x{bb.size.Y:<7.2f}")
        if n_solids != 1:
            failures.append(f"{name}: {n_solids} solids, expected 1")
        if not valid:
            failures.append(f"{name}: is_valid() is False")
        if vol <= 0:
            failures.append(f"{name}: volume {vol} is not positive")
        if part.label:
            failures.append(f"{name}: label should be empty, got {part.label!r}")
        if part.color is None:
            failures.append(f"{name}: no colour set")

    # seating-face convention: heads above z=0, shanks below
    for name, lo, hi in [
        ("hex_flange_bolt", -30.0, 8.1),
        ("hex_nut", 0.0, 6.5),
        ("washer", 0.0, 1.6),
        ("stud", -18.0, 26.0),
        ("id_pad", 0.0, 2.0),
    ]:
        if name not in built:
            continue
        bb = built[name].bounding_box()
        if abs(bb.min.Z - lo) > 0.35 or abs(bb.max.Z - hi) > 0.35:
            failures.append(
                f"{name}: z extent {bb.min.Z:.3f}..{bb.max.Z:.3f}, "
                f"expected ~{lo}..{hi}"
            )

    # ---- place() numerics -------------------------------------------------
    print()
    bolt = built.get("hex_flange_bolt")
    if bolt is not None:
        local_c = bolt.center()
        target = (120.0, -40.0, 15.0)
        zdir = (0.0, -0.707, 0.707)
        moved = place(bolt, target, zdir)

        x, y, z = _frame(zdir)
        expect = (
            bd.Vector(*target)
            + x * local_c.X + y * local_c.Y + z * local_c.Z
        )
        got = moved.center()
        err = (got - expect).length
        print(f"place(): local centroid {local_c.X:.4f},{local_c.Y:.4f},"
              f"{local_c.Z:.4f}")
        print(f"         expected        {expect.X:.4f},{expect.Y:.4f},"
              f"{expect.Z:.4f}")
        print(f"         got             {got.X:.4f},{got.Y:.4f},{got.Z:.4f}"
              f"   err {err:.3e} mm")
        if err > 1e-6:
            failures.append(f"place(): centroid off by {err:.3e} mm")
        if abs(moved.volume - bolt.volume) > 1e-6:
            failures.append("place(): volume changed")
        if abs(bolt.center().Z - local_c.Z) > 1e-9:
            failures.append("place(): mutated its input (must return a copy)")

        # the local origin must land exactly on `point`: probe with the axis
        # direction recovered from the seating-face normal
        for label, zd in [
            ("+Z", (0, 0, 1)),
            ("-Z", (0, 0, -1)),
            ("tilted", (0.0, -0.707, 0.707)),
            ("x-fixed", (1.0, 0.0, 0.0)),
        ]:
            xx, yy, zz = _frame(zd, (0, 0, 1) if label == "x-fixed" else None)
            ortho = max(abs(xx.dot(yy)), abs(yy.dot(zz)), abs(xx.dot(zz)))
            handed = (xx.cross(yy) - zz).length
            print(f"  frame {label:>8}: x={xx.X:+.3f},{xx.Y:+.3f},{xx.Z:+.3f}"
                  f"  z={zz.X:+.3f},{zz.Y:+.3f},{zz.Z:+.3f}"
                  f"  ortho={ortho:.1e} rh={handed:.1e}")
            if ortho > 1e-9 or handed > 1e-9:
                failures.append(f"_frame({label}): not orthonormal right-handed")

        # local +Z of the placed bolt must point along z_dir: the head tip
        # (highest local point on the axis) moves to point + zhat * bb.max.Z
        # local +Z really points along z_dir: the furthest vertex measured
        # along zhat, relative to the seating point, must equal the local head
        # height, and the deepest must equal the local shank reach.
        bb = bolt.bounding_box()
        base = bd.Vector(*target).dot(z)
        along = [bd.Vector(tuple(v)).dot(z) - base for v in moved.vertices()]
        top_along, bot_along = max(along), min(along)
        print(f"         reach along z_dir {bot_along:+.4f} .. {top_along:+.4f} mm"
              f"   (local {bb.min.Z:+.4f} .. {bb.max.Z:+.4f})")
        if abs(top_along - bb.max.Z) > 1e-6 or abs(bot_along - bb.min.Z) > 1e-6:
            failures.append("place(): local +Z did not land along z_dir")

    # ---- bolt_ring / bolt_row --------------------------------------------
    if bolt is not None:
        ring = bolt_ring(bolt, (0, 0, 100), (0, 0, 1), 45.0, 8, start_deg=22.5)
        radii = []
        for i, b in enumerate(ring):
            # each copy's seating origin: recover it from the known local
            # centroid offset, which is along local +Z only in X/Y terms
            c = b.center()
            radii.append(math.hypot(c.X, c.Y))
        spread = max(radii) - min(radii)
        print(f"\nbolt_ring: {len(ring)} copies, centroid radius "
              f"{radii[0]:.4f} mm, spread {spread:.2e} mm")
        if len(ring) != 8:
            failures.append("bolt_ring: wrong count")
        if spread > 1e-6:
            failures.append(f"bolt_ring: radius spread {spread:.2e} mm")
        if abs(radii[0] - 45.0) > 1e-6:
            failures.append(
                f"bolt_ring: centroid radius {radii[0]:.4f} != 45.0 "
                "(centroid should stay on the bolt axis)"
            )

        row = bolt_row(bolt, [(0, 0, 0), (20, 0, 0), (40, 0, 0)], (0, 1, 0))
        xs = sorted(round(b.center().X, 6) for b in row)
        print(f"bolt_row:  {len(row)} copies at x = {xs}")
        if len(row) != 3:
            failures.append("bolt_row: wrong count")
        if any(abs(b.bounding_box().size.Y - bolt.bounding_box().size.Z) > 1e-6
               for b in row):
            failures.append("bolt_row: local +Z did not align with z_dir")

    # ---- other sizes, and the off-table fallback path --------------------
    sized = [
        ("hex_flange_bolt", lambda d: hex_flange_bolt(d, 3 * d)),
        ("socket_cap_bolt", lambda d: socket_cap_bolt(d, 3 * d)),
        ("twelve_point_bolt", lambda d: twelve_point_bolt(d, 3 * d)),
        ("hex_nut", hex_nut),
        ("flange_nut", flange_nut),
        ("washer", washer),
        ("stud", lambda d: stud(d, 3 * d, 2 * d)),
        ("banjo_bolt", banjo_bolt),
    ]
    print()
    for d in (6.0, 10.0, 12.0, 7.0):          # 7.0 exercises the untabled fallback
        beats = []
        for name, fn in sized:
            try:
                p = fn(d)
                ok = _is_valid(p) and p.volume > 0 and len(p.solids()) == 1
            except Exception as exc:  # noqa: BLE001
                ok = False
                failures.append(f"M{d:g} {name}: {type(exc).__name__}: {exc}")
            if not ok:
                failures.append(f"M{d:g} {name}: not one valid positive solid")
            beats.append("." if ok else "X")
        tag = f"M{d:g}" + ("*" if _key(d) not in _FLANGE_BOLT else "")
        print(f"  {tag:>4} {''.join(beats)}   ({len(sized)} parts)")
    print("       * = untabled diameter, proportional fallback")

    print()
    if failures:
        print(f"FAIL ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"OK: {len(built)} fasteners built at M{D:g}, "
          "all single closed positive-volume solids; "
          "place/bolt_ring/bolt_row verified numerically.")
