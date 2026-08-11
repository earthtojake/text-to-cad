"""Gearbox, clutch, gear cluster, differential, driveshafts, crash structure.

The structural rear end of the car. Everything aft of the engine's rear face
hangs off this module, so it is modelled as one continuous load path:

    engine rear face (x = GEARBOX_FRONT_X)
      -> bolt flange + bellhousing bell
      -> waisted, ribbed magnesium casing (pinched for the tunnel roofs)
      -> differential cartridge on the rear axle line
      -> carbon rear impact structure -> rear wing pylon pad

The rear suspension picks up on eight inboard hardpoints stated in `spec`.
Every one of them is carried by a machined boss or clevis that is fused into
the casing (the five forward ones) or into the cast rear pickup carrier (the
three aft ones), so the point physically sits in metal — `REAR_PICKUPS` and
`pickup_boss()` exist so that can be checked numerically.

Internal layout (drivetrain-local, all derived from `spec` datums):

    clutch / primary shaft   z = spec.CRANK_Z   (coaxial with the crank)
    drop pair                lifts the drive to the input shaft
    input  (upper) shaft     z = _INPUT_Z
    output (lower) shaft     z = _OUTPUT_Z      (centre distance 68 mm)
    differential             z = _DIFF_Z on x = spec.REAR_AXLE_X

The shafts are stacked high because the diffuser tunnel roofs climb under the
casing: the underside stays above z=150 at x=-3000 and above z=230 by x=-3500.
"""

from __future__ import annotations

import math

from build123d import (
    Box,
    Compound,
    Plane,
    Pos,
    Solid,
    Spline,
    Vector,
    make_face,
)

from . import lib, spec

# ==========================================================================
# datums
# ==========================================================================

_BOX_FWD = spec.GEARBOX_FRONT_X  # -2880, bolt face to the engine
_BOX_AFT = spec.GEARBOX_REAR_X  # -3560
_TAIL_AFT = spec.CRASH_STRUCTURE_REAR_X  # -3980
_AXLE = spec.REAR_AXLE_X  # -3600

_CLUTCH_Z = spec.CRANK_Z  # 220
_INPUT_Z = 334.0
_OUTPUT_Z = 266.0
_CENTRE_DIST = _INPUT_Z - _OUTPUT_Z  # 68
_DIFF_Z = 292.0
_DIFF_R = 64.0

_N_GEARS = 8
_GEAR_X_FWD = -3200.0
_GEAR_X_AFT = -3480.0
_GEAR_ROOT_R = 44.0
_GEAR_RATIO = 0.90  # spec rule 5: rhythmic geometric progression
_GEAR_W = 26.0

_DROP_X = -3000.0
_DROP_R_LOW = 42.0
_DROP_R_HIGH = _INPUT_Z - _CLUTCH_Z - _DROP_R_LOW  # 68

_WALL_PAD = 8.0

# The casing's evolving cross-section: a broad squared bell at the engine
# face, pinched to a deep narrow waist over the tunnel roofs, flaring again
# into the differential and the rear suspension pickups.
#         x        hw      z0      z1    waist  n_bot  n_top
_CASING = (
    (-2880.0, 208.0, 152.0, 440.0, 0.44, 3.40, 3.80),
    (-2946.0, 200.0, 154.0, 434.0, 0.44, 3.30, 3.80),
    (-3012.0, 184.0, 158.0, 426.0, 0.45, 3.10, 3.70),
    (-3080.0, 164.0, 164.0, 416.0, 0.46, 2.90, 3.60),
    (-3160.0, 145.0, 176.0, 408.0, 0.47, 2.70, 3.50),
    (-3240.0, 130.0, 190.0, 404.0, 0.49, 2.60, 3.40),
    (-3320.0, 122.0, 204.0, 402.0, 0.51, 2.50, 3.40),
    (-3400.0, 128.0, 216.0, 402.0, 0.53, 2.60, 3.50),
    (-3470.0, 142.0, 228.0, 406.0, 0.54, 2.80, 3.60),
    (-3520.0, 156.0, 236.0, 414.0, 0.55, 3.00, 3.70),
    (-3560.0, 168.0, 246.0, 424.0, 0.55, 3.20, 3.80),
)

# Bell mouth -> shaft bores -> gear cluster tunnel. Kept as an explicit
# envelope (not a skin offset) so the casing keeps solid metal where the
# suspension and damper bosses have to be machined into it.
_BELL_CAVITY = (
    (-2872.0, 184.0, 168.0, 424.0, 0.46, 3.10, 3.30),
    (-2960.0, 164.0, 170.0, 416.0, 0.46, 2.95, 3.15),
    (-3020.0, 110.0, 174.0, 408.0, 0.47, 2.70, 2.95),
    (-3070.0, 62.0, 200.0, 372.0, 0.50, 2.40, 2.60),
)
_CLUSTER_CAVITY = (
    (-3200.0, 56.0, 214.0, 368.0, 0.50, 2.30, 2.40),
    (-3300.0, 56.0, 220.0, 370.0, 0.50, 2.30, 2.40),
    (-3400.0, 56.0, 228.0, 376.0, 0.50, 2.30, 2.40),
    (-3480.0, 56.0, 236.0, 384.0, 0.50, 2.30, 2.40),
    (-3545.0, 46.0, 250.0, 386.0, 0.50, 2.30, 2.40),
)

# Carbon rear impact structure: deep at the gearbox face, tapering into a
# rolled blade tail. The shoulder line hands off at (-3800, 62, 386).
#         x        hw      z0      z1    waist  n_bot  n_top
_TAIL = (
    (-3560.0, 116.0, 364.0, 434.0, 0.58, 2.70, 2.50),
    (-3650.0, 104.0, 358.0, 428.0, 0.61, 2.60, 2.40),
    (-3740.0, 90.0, 352.0, 416.0, 0.64, 2.50, 2.30),
    (-3820.0, 76.0, 348.0, 406.0, 0.68, 2.40, 2.20),
    (-3890.0, 62.0, 346.0, 396.0, 0.72, 2.30, 2.10),
    (-3945.0, 56.0, 344.0, 396.0, 0.72, 2.20, 2.00),
    (-3972.0, 52.0, 346.0, 394.0, 0.73, 2.10, 2.00),
    (-3980.0, 38.0, 354.0, 388.0, 0.75, 2.00, 2.00),
)

_PYLON_PAD_X = -3900.0
_PYLON_PAD_Z = 390.0  # the rear-wing pylon lands on this face


# ==========================================================================
# section machinery
# ==========================================================================


def _interp_table(table, x):
    """Interpolate a (x, hw, z0, z1, waist, n_bot, n_top) station table."""
    if x >= table[0][0]:
        return table[0][1:]
    if x <= table[-1][0]:
        return table[-1][1:]
    for i in range(len(table) - 1):
        x0, x1 = table[i][0], table[i + 1][0]
        if x1 <= x <= x0:
            t = (x0 - x) / (x0 - x1)
            return tuple(
                spec.lerp(table[i][j + 1], table[i + 1][j + 1], t) for j in range(6)
            )
    return table[-1][1:]


def _sect_pts(hw, z0, z1, waist, n_bot, n_top, samples=21):
    """Left-side outline of a casing section: bottom centreline -> top.

    Resampled to EQUAL ARC LENGTH. A squared-off superellipse sampled at
    uniform angle bunches nearly all its points on the flanks and leaves a
    single huge step across the flat top and bottom; the periodic spline that
    closes the section then overshoots by ~100 mm. Equal spacing fixes it.
    """
    cz = z0 + (z1 - z0) * waist
    hb, ht = cz - z0, z1 - cz
    dense = []
    steps = 480
    for i in range(steps + 1):
        a = -math.pi / 2.0 + math.pi * i / steps
        ca, sa = math.cos(a), math.sin(a)
        n = n_top if sa >= 0 else n_bot
        hh = ht if sa >= 0 else hb
        y = hw * abs(ca) ** (2.0 / n)
        z = cz + hh * math.copysign(abs(sa) ** (2.0 / n), sa)
        dense.append((y, z))
    dense[0] = (0.0, z0)
    dense[-1] = (0.0, z1)

    cum = [0.0]
    for i in range(1, len(dense)):
        cum.append(cum[-1] + math.dist(dense[i - 1], dense[i]))
    total = cum[-1]

    out = []
    j = 0
    for k in range(samples):
        target = total * k / (samples - 1)
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg <= 1e-12 else (target - cum[j]) / seg
        out.append(
            (
                dense[j][0] + (dense[j + 1][0] - dense[j][0]) * t,
                dense[j][1] + (dense[j + 1][1] - dense[j][1]) * t,
            )
        )
    out[0] = (0.0, z0)
    out[-1] = (0.0, z1)
    return out


def _sect_face(table, x, grow=0.0, samples=15):
    hw, z0, z1, waist, n_bot, n_top = _interp_table(table, x)
    return lib.half_section_face(
        x, _sect_pts(hw + grow, z0 - grow, z1 + grow, waist, n_bot, n_top, samples)
    )


def _table_loft(table, grow=0.0, extra_x=(), samples=15):
    xs = [row[0] for row in table] + list(extra_x)
    xs = sorted(set(xs), reverse=True)
    return lib.body_loft([_sect_face(table, x, grow, samples) for x in xs])


def _surface_z(x, y, table=_CASING):
    """Height of the casing's UPPER surface at station x, offset y."""
    hw, z0, z1, waist, n_bot, n_top = _interp_table(table, x)
    ay = min(abs(y), hw * 0.999)
    ca = (ay / hw) ** (n_top / 2.0)
    sa = math.sqrt(max(0.0, 1.0 - ca * ca))
    cz = z0 + (z1 - z0) * waist
    return cz + (z1 - cz) * sa ** (2.0 / n_top)


def _surface_y(x, z, table=_CASING):
    """Half-width of the casing at station x, height z."""
    hw, z0, z1, waist, n_bot, n_top = _interp_table(table, x)
    cz = z0 + (z1 - z0) * waist
    if z >= cz:
        n, hh = n_top, z1 - cz
    else:
        n, hh = n_bot, cz - z0
    sa = min(abs(z - cz) / max(hh, 1e-6), 0.999)
    ca = math.sqrt(max(0.0, 1.0 - sa ** n))
    return hw * ca ** (2.0 / n) if ca > 0 else 0.0


# ==========================================================================
# small solid helpers
# ==========================================================================


def _v(p):
    if isinstance(p, Vector):
        return p
    return Vector(p[0], p[1], p[2])


def _cyl(p0, p1, r):
    a, b = _v(p0), _v(p1)
    d = b - a
    return Solid.make_cylinder(r, d.length, Plane(origin=a, z_dir=d))


def _cone(p0, p1, r0, r1):
    a, b = _v(p0), _v(p1)
    d = b - a
    return Solid.make_cone(r0, r1, d.length, Plane(origin=a, z_dir=d))


def _ball(p, r):
    return Solid.make_sphere(r, Plane(origin=_v(p)))


def _rbox(cx, cy, cz, lx, ly, lz):
    return Pos(cx, cy, cz) * Box(lx, ly, lz)


def _rrect_pts(length, height, corner, arc=5, edge=4):
    """Rounded-rectangle outline sampled on the STRAIGHT edges as well as the
    corner arcs.

    A periodic spline through corner points alone has nothing to hold the long
    sides down and bows out by tens of millimetres — a pocket cut that way
    swallows the whole casting.
    """
    hl, hh = length / 2.0, height / 2.0
    r = min(corner, hl * 0.9, hh * 0.9)
    corners = [
        (hl - r, hh - r, 0.0),
        (-hl + r, hh - r, math.pi / 2.0),
        (-hl + r, -hh + r, math.pi),
        (hl - r, -hh + r, 3.0 * math.pi / 2.0),
    ]
    pts = []
    for i, (cu, cv, a0) in enumerate(corners):
        for k in range(arc + 1):
            a = a0 + (math.pi / 2.0) * k / arc
            pts.append((cu + r * math.cos(a), cv + r * math.sin(a)))
        ea = a0 + math.pi / 2.0
        nu, nv, _ = corners[(i + 1) % 4]
        p0 = (cu + r * math.cos(ea), cv + r * math.sin(ea))
        p1 = (nu + r * math.cos(ea), nv + r * math.sin(ea))
        for k in range(1, edge):
            t = k / edge
            pts.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return pts


def _plate_face(plane, length, height, corner, arc=5, edge=4):
    pts = _rrect_pts(length, height, corner, arc, edge)
    return plane * make_face(Spline(*pts, periodic=True))


def _y_plane(cx, y, cz):
    """Plane normal to Y with local u along +X and v along +Z."""
    return Plane(origin=(cx, y, cz), x_dir=(1, 0, 0), z_dir=(0, -1, 0))


def _y_prism(stations, corner=18.0):
    """Loft rounded rectangles on planes normal to Y.

    Each station: (y, cx, cz, length, height).
    """
    faces = [
        _plate_face(_y_plane(cx, y, cz), length, height, corner)
        for (y, cx, cz, length, height) in stations
    ]
    return lib.body_loft(faces)


def _x_plane(x, cy, cz):
    """Plane normal to X with local u along +Y and v along +Z."""
    return Plane(origin=(x, cy, cz), x_dir=(0, 1, 0), z_dir=(1, 0, 0))


def _x_prism(stations, corner=10.0):
    """Loft rounded rectangles on planes normal to X.

    Each station: (x, cy, cz, width_y, height_z).
    """
    faces = [
        _plate_face(_x_plane(x, cy, cz), w, h, corner)
        for (x, cy, cz, w, h) in stations
    ]
    return lib.body_loft(faces)


def _tube(points, radius):
    """A slim run of pipe through a polyline, rounded at every bend."""
    parts = [_cyl(points[i], points[i + 1], radius) for i in range(len(points) - 1)]
    parts += [_ball(p, radius) for p in points[1:-1]]
    return _fuse(parts)


def _one(out):
    """Normalise a boolean result (build123d hands back a list when the
    result is disjoint) into a single Shape."""
    if isinstance(out, (list, tuple)) or type(out).__name__ == "ShapeList":
        solids = []
        for s in out:
            solids.extend(s.solids())
        if len(solids) == 1:
            return solids[0]
        return Compound(children=solids)
    return out


def _tidy(shape):
    """`clean()` (unify-same-domain) sometimes throws most of a big casting
    away. Keep the tidied shape only when it preserves the volume."""
    try:
        out = _one(shape.clean())
        if out.volume >= shape.volume * 0.999:
            return out
    except Exception:
        pass
    return shape


def _fuse(parts):
    """Boolean union of a list of solids.

    The multi-argument fuse is much cheaper than chaining `+`, but when the
    tools also overlap each other (ribs crossed by the spine) it can quietly
    return a fragment of the input. Volume is the tell: the union can never be
    smaller than its largest operand, so check and fall back to a sequential
    pairwise fuse when it is.
    """
    ps = [p for p in parts if p is not None]
    if not ps:
        return None
    if len(ps) == 1:
        return ps[0]
    biggest = max(p.volume for p in ps)
    out = _one(ps[0].fuse(*ps[1:]))
    if out.volume < biggest * 0.999:
        alt = ps[0]
        for p in ps[1:]:
            alt = _one(alt.fuse(p))
        if alt.volume > out.volume:
            out = alt
    return _tidy(out)


def _cut(body, tools):
    ts = [t for t in tools if t is not None]
    if not ts:
        return body
    out = _one(body.cut(*ts))
    return _tidy(out)


def _unit(a, b):
    d = _v(b) - _v(a)
    return d.normalized()


def _along(p0, u, t):
    q = _v(p0) + u * t
    return (q.X, q.Y, q.Z)


def _strut(p0, p1, c0, c1, back=10.0, fwd=10.0, thickness_ratio=0.32):
    """Tapered blade run past both joints.

    Members that meet exactly at a shared point give OCC a degenerate
    intersection and the fuse comes back with an unorientable face, so every
    joint in the cast structures is a genuine overlap.
    """
    u = _unit(p0, p1)
    return lib.blade_member(
        _along(p0, u, -back),
        _along(p1, u, fwd),
        c0,
        c1,
        thickness_ratio=thickness_ratio,
    )


# ==========================================================================
# rear suspension pickups
# ==========================================================================


def _norm3(a, b):
    d = _unit(a, b)
    return (d.X, d.Y, d.Z)


_LOWER_PIVOT_AXIS = _norm3(spec.R_LOWER_IN_FWD, spec.R_LOWER_IN_AFT)
_UPPER_PIVOT_AXIS = _norm3(spec.R_UPPER_IN_FWD, spec.R_UPPER_IN_AFT)

# name, hardpoint, pin axis, boss root (inside the parent casting),
# root chord, tip chord, cheek radius, clevis gap, pin radius
REAR_PICKUPS = (
    (
        "lower_in_fwd",
        spec.R_LOWER_IN_FWD,
        _LOWER_PIVOT_AXIS,
        (-3298.0, 68.0, 226.0),
        104.0,
        46.0,
        19.0,
        24.0,
        9.0,
    ),
    (
        "lower_in_aft",
        spec.R_LOWER_IN_AFT,
        _LOWER_PIVOT_AXIS,
        None,  # the carrier's post and lower leg both land on this point
        76.0,
        44.0,
        18.0,
        24.0,
        9.0,
    ),
    (
        "upper_in_fwd",
        spec.R_UPPER_IN_FWD,
        _UPPER_PIVOT_AXIS,
        (-3286.0, 78.0, 380.0),
        96.0,
        44.0,
        18.0,
        22.0,
        8.5,
    ),
    (
        "upper_in_aft",
        spec.R_UPPER_IN_AFT,
        _UPPER_PIVOT_AXIS,
        None,  # the carrier's upper leg and post both land on this point
        72.0,
        42.0,
        17.0,
        22.0,
        8.5,
    ),
    (
        "toelink_in",
        spec.R_TOELINK_IN,
        (0.0, 0.0, 1.0),
        (-3818.0, 229.0, 256.0),
        46.0,
        34.0,
        16.0,
        20.0,
        8.0,
    ),
    (
        "pullrod_in",
        spec.R_PULLROD_IN,
        (1.0, 0.0, 0.0),
        (-3300.0, 72.0, 248.0),
        80.0,
        40.0,
        17.0,
        26.0,
        8.5,
    ),
    (
        "rocker_pivot",
        spec.R_ROCKER_PIVOT,
        spec.R_ROCKER_AXIS,
        (-3272.0, 84.0, 268.0),
        92.0,
        52.0,
        26.0,
        0.0,
        11.0,
    ),
    (
        "damper_in",
        spec.R_DAMPER_IN,
        (1.0, 0.0, 0.0),
        (-3120.0, 30.0, 300.0),
        44.0,
        34.0,
        18.0,
        26.0,
        9.0,
    ),
)


def _clevis(point, axis, cheek_r, gap, pin_r):
    """Two machined ears with a pin through them, centred on `point`.

    The pin is a solid barrel whose axis passes exactly through the
    hardpoint, so the hardpoint is inside the machined boss.
    """
    u = _v(axis).normalized()
    if gap <= 0.0:
        # plain bearing barrel (rocker bearing)
        half = cheek_r * 1.15
        return _fuse(
            [
                _cyl(_along(point, u, -half), _along(point, u, half), cheek_r),
                _cyl(
                    _along(point, u, -half - 6.0),
                    _along(point, u, half + 6.0),
                    pin_r,
                ),
            ]
        )
    ears = []
    for s in (-1.0, 1.0):
        a = _along(point, u, s * gap / 2.0)
        b = _along(point, u, s * (gap / 2.0 + cheek_r * 0.62))
        ears.append(_cone(a, b, cheek_r, cheek_r * 0.86))
    pin = _cyl(
        _along(point, u, -(gap / 2.0 + cheek_r * 0.62 + 5.0)),
        _along(point, u, gap / 2.0 + cheek_r * 0.62 + 5.0),
        pin_r,
    )
    return _fuse(ears + [pin])


def pickup_boss(name):
    """The machined boss carrying one rear inboard hardpoint, as one solid."""
    for entry in REAR_PICKUPS:
        if entry[0] != name:
            continue
        _, point, axis, root, c0, c1, cheek_r, gap, pin_r = entry
        clevis = _clevis(point, axis, cheek_r, gap, pin_r)
        if root is None:
            return clevis
        arm = _strut(root, point, c0, c1, back=0.0, fwd=cheek_r * 0.8,
                     thickness_ratio=0.34)
        return _fuse([arm, clevis])
    raise KeyError(name)


def _forward_pickup_names():
    return ("lower_in_fwd", "upper_in_fwd", "pullrod_in", "rocker_pivot", "damper_in")


def _aft_pickup_names():
    return ("lower_in_aft", "upper_in_aft", "toelink_in")


# ==========================================================================
# 1 / 2 / 9 — gearbox casing, bellhousing, engine-mount hardware
# ==========================================================================


def _casing_outer():
    return _table_loft(_CASING, extra_x=(-3040.0, -3120.0, -3200.0, -3280.0,
                                        -3360.0, -3440.0, -3500.0))


def _casing_cavity():
    bell = _table_loft(_BELL_CAVITY, extra_x=(-2916.0, -2990.0, -3046.0))
    cluster = _table_loft(_CLUSTER_CAVITY, extra_x=(-3250.0, -3350.0, -3440.0,
                                                    -3515.0))
    bore_hi = _cyl((-3068.0, 0.0, _INPUT_Z), (-3196.0, 0.0, _INPUT_Z), 26.0)
    bore_lo = _cyl((-3068.0, 0.0, _OUTPUT_Z), (-3196.0, 0.0, _OUTPUT_Z), 28.0)
    # selector-barrel gallery, joined to the main tunnel
    gallery = _rbox(-3340.0, 0.0, 300.0, 340.0, 208.0, 52.0)
    return _fuse([bell, cluster, bore_hi, bore_lo, gallery])


# circumferential stiffening ribs, rhythmic (110/105/100/95/90 spacing)
_RIB_XS = (-2985.0, -3095.0, -3200.0, -3300.0, -3395.0, -3485.0)


def _ring_rib(x, thickness=10.0, proud=9.0):
    return lib.body_loft(
        [
            _sect_face(_CASING, x + thickness / 2.0, grow=proud),
            _sect_face(_CASING, x - thickness / 2.0, grow=proud),
        ]
    )


def _top_spine():
    """Raised keel down the centre of the top deck.

    Cut out of a uniformly grown copy of the casing, so it follows the deck
    exactly and dies into the front flange and the rear face.
    """
    grown = _table_loft(_CASING, grow=11.0, extra_x=(-3120.0, -3280.0, -3440.0))
    return _one(grown.intersect(_rbox(-3225.0, 0.0, 420.0, 660.0, 52.0, 320.0)))


def _casing_outer_ribbed():
    """Outer skin with every cast rib already unioned in.

    The ribs are full bands that swallow the local section, so this is a
    containment union — cheap. Building the ribs as thin shells and fusing
    them onto the finished casing instead means coincident faces everywhere,
    which costs about a minute of OCC time for the same result.
    """
    return _fuse([_casing_outer()] + [_ring_rib(x) for x in _RIB_XS])


def _damper_bay(side):
    """Deep machined scallop in each flank; the rear damper lies in it."""
    s = 1.0 if side > 0 else -1.0
    return _y_prism(
        [
            (s * 270.0, -3160.0, 312.0, 320.0, 124.0),
            (s * 160.0, -3150.0, 312.0, 262.0, 104.0),
            (s * 96.0, -3140.0, 312.0, 200.0, 84.0),
            (s * 44.0, -3126.0, 312.0, 120.0, 64.0),
        ],
        corner=24.0,
    )


def _diff_socket():
    return _cyl((_AXLE, -170.0, _DIFF_Z), (_AXLE, 170.0, _DIFF_Z), _DIFF_R)


def _gearbox_casing(outer_ribbed):
    body = _cut(
        outer_ribbed,
        [
            _casing_cavity(),
            _damper_bay(1),
            _damper_bay(-1),
            _diff_socket(),
        ],
    )
    # every forward suspension pickup is cast integral with the casing,
    # on both sides
    bosses = []
    for name in _forward_pickup_names():
        left = pickup_boss(name)
        bosses += [left, lib.mirror_y(left)]
    return _fuse([body] + bosses)


def _front_flange(outer):
    plate = lib.body_loft(
        [
            _sect_face(_CASING, _BOX_FWD, grow=30.0),
            _sect_face(_CASING, _BOX_FWD - 20.0, grow=30.0),
        ]
    )
    return plate - outer


def _flange_ring_pts(n, grow):
    """`n` points marching around the front-flange section, evenly in angle."""
    hw, z0, z1, waist, n_bot, n_top = _interp_table(_CASING, _BOX_FWD)
    hw += grow
    z0 -= grow
    z1 += grow
    cz = z0 + (z1 - z0) * waist
    hb, ht = cz - z0, z1 - cz
    out = []
    for i in range(n):
        a = 2.0 * math.pi * (i + 0.5) / n
        ca, sa = math.cos(a), math.sin(a)
        nn = n_top if sa >= 0 else n_bot
        hh = ht if sa >= 0 else hb
        y = hw * math.copysign(abs(ca) ** (2.0 / nn), ca)
        z = cz + hh * math.copysign(abs(sa) ** (2.0 / nn), sa)
        out.append((y, z))
    return out


def _engine_mount_hardware():
    bolts, dowels = [], []
    ring = _flange_ring_pts(22, 17.0)
    for i, (y, z) in enumerate(ring):
        p0 = (_BOX_FWD - 20.0, y, z)
        p1 = (_BOX_FWD - 32.0, y, z)
        bolts.append(_cone(p0, p1, 9.5, 8.2))
        bolts.append(_cyl(p0, (_BOX_FWD - 23.5, y, z), 11.5))
        if i % 6 == 3:
            dowels.append(_cyl(p0, (_BOX_FWD - 38.0, y, z), 7.5))
    return _fuse(bolts), _fuse(dowels)


# ==========================================================================
# 2 — clutch
# ==========================================================================


def _clutch():
    z = _CLUTCH_Z
    parts = [
        _cyl((_BOX_FWD - 4.0, 0.0, z), (_BOX_FWD - 104.0, 0.0, z), 22.0),
        _cone((_BOX_FWD - 4.0, 0.0, z), (_BOX_FWD - 18.0, 0.0, z), 44.0, 30.0),
        _cyl((_BOX_FWD - 96.0, 0.0, z), (_BOX_FWD - 118.0, 0.0, z), 15.0),
    ]
    for i in range(14):  # splines
        a = 2.0 * math.pi * i / 14.0
        y, zz = 26.0 * math.cos(a), z + 26.0 * math.sin(a)
        parts.append(_cyl((_BOX_FWD - 18.0, y, zz), (_BOX_FWD - 96.0, y, zz), 4.2))
    hub = _fuse(parts)

    plates = []
    for i in range(6):
        x = _BOX_FWD - 24.0 - 12.0 * i
        disc = _cyl((x, 0.0, z), (x - 4.2, 0.0, z), 46.0)
        plates.append(disc - _cyl((x + 2.0, 0.0, z), (x - 6.2, 0.0, z), 29.0))

    ring = _cyl((_BOX_FWD - 12.0, 0.0, z), (_BOX_FWD - 22.0, 0.0, z), 55.0)
    ring = ring - _cyl((_BOX_FWD - 10.0, 0.0, z), (_BOX_FWD - 24.0, 0.0, z), 34.0)
    lugs = [
        _ball(
            (
                _BOX_FWD - 12.0,
                51.0 * math.cos(2.0 * math.pi * i / 8.0 + 0.2),
                z + 51.0 * math.sin(2.0 * math.pi * i / 8.0 + 0.2),
            ),
            7.0,
        )
        for i in range(8)
    ]
    return hub, plates, _fuse([ring] + lugs)


# ==========================================================================
# 3 — gear cluster, selector barrels, shift forks
# ==========================================================================


def _gear_radii():
    lo = [_GEAR_ROOT_R * _GEAR_RATIO**i for i in range(_N_GEARS)]
    hi = [_CENTRE_DIST - r for r in lo]
    xs = [
        _GEAR_X_FWD + (_GEAR_X_AFT - _GEAR_X_FWD) * i / (_N_GEARS - 1)
        for i in range(_N_GEARS)
    ]
    return xs, lo, hi


def _gear_parts(x, z, r, width=_GEAR_W):
    """A stepped machined gear: relieved rim, web, hub collar."""
    web_r = max(r - 7.0, 6.0)
    rim = _cyl((x + width / 2.0, 0.0, z), (x - width / 2.0, 0.0, z), r)
    rim = rim - _cyl(
        (x + width * 0.26, 0.0, z), (x - width * 0.26, 0.0, z), web_r
    )
    return [
        rim,
        _cyl((x + width * 0.24, 0.0, z), (x - width * 0.24, 0.0, z), web_r),
        _cyl(
            (x + width * 0.78, 0.0, z),
            (x - width * 0.78, 0.0, z),
            max(r * 0.40, 12.0),
        ),
    ]


def _dog_ring_parts(x, z, r=30.0, width=16.0):
    parts = [_cyl((x + width / 2.0, 0.0, z), (x - width / 2.0, 0.0, z), r)]
    for i in range(9):
        a = 2.0 * math.pi * i / 9.0
        y, zz = (r - 3.0) * math.cos(a), z + (r - 3.0) * math.sin(a)
        parts.append(
            _cyl(
                (x + width / 2.0 + 7.0, y, zz), (x + width / 2.0 - 2.0, y, zz), 4.4
            )
        )
    return parts


def _gear_cluster():
    xs, lo, hi = _gear_radii()

    up = [_cyl((-2988.0, 0.0, _INPUT_Z), (-3500.0, 0.0, _INPUT_Z), 15.0)]
    up += _gear_parts(_DROP_X, _INPUT_Z, _DROP_R_HIGH, 30.0)
    for x, r in zip(xs, hi):
        up += _gear_parts(x, _INPUT_Z, r)

    dn = [_cyl((-3170.0, 0.0, _OUTPUT_Z), (-3506.0, 0.0, _OUTPUT_Z), 16.0)]
    for x, r in zip(xs, lo):
        dn += _gear_parts(x, _OUTPUT_Z, r)
    span = xs[1] - xs[0]
    for i in range(1, _N_GEARS, 2):
        dn += _dog_ring_parts(xs[i] - span / 2.0, _OUTPUT_Z)
    pr = [
        _cyl(
            (_BOX_FWD - 100.0, 0.0, _CLUTCH_Z),
            (_DROP_X - 24.0, 0.0, _CLUTCH_Z),
            17.0,
        )
    ]
    pr += _gear_parts(_DROP_X, _CLUTCH_Z, _DROP_R_LOW, 30.0)

    return _fuse(up), _fuse(dn), _fuse(pr)


def _selector(side):
    s = 1.0 if side > 0 else -1.0
    y = s * 78.0
    z = 300.0
    barrel = _fuse(
        [
            _cone((-3186.0, y, z), (-3212.0, y, z), 13.0, 18.0),
            _cyl((-3212.0, y, z), (-3468.0, y, z), 18.0),
            _cone((-3468.0, y, z), (-3492.0, y, z), 18.0, 12.0),
        ]
    )
    # helical selector tracks, read as a rhythm of machined grooves
    barrel = _cut(
        barrel,
        [
            _ball(
                (
                    -3232.0 - 42.0 * i,
                    y + 17.0 * math.cos(0.9 * i),
                    z + 17.0 * math.sin(0.9 * i),
                ),
                8.0,
            )
            for i in range(6)
        ],
    )
    xs, lo, _hi = _gear_radii()
    span = xs[1] - xs[0]
    forks = []
    for i in range(1, _N_GEARS, 2):
        if (i // 2) % 2 == (0 if s > 0 else 1):
            continue
        fx = xs[i] - span / 2.0
        arm = lib.blade_member(
            (fx, y, z), (fx, s * 22.0, _OUTPUT_Z + 4.0), 44.0, 32.0,
            thickness_ratio=0.26,
        )
        collar = _cyl((fx + 6.0, 0.0, _OUTPUT_Z), (fx - 6.0, 0.0, _OUTPUT_Z), 38.0)
        collar = _cut(
            collar,
            [
                _cyl(
                    (fx + 8.0, 0.0, _OUTPUT_Z), (fx - 8.0, 0.0, _OUTPUT_Z), 31.0
                ),
                _rbox(fx, -s * 60.0, _OUTPUT_Z, 40.0, 100.0, 100.0),
            ],
        )
        forks += [arm, collar]
    return _fuse([barrel] + forks)


# ==========================================================================
# 4 / 5 — differential and driveshafts
# ==========================================================================


def _differential():
    parts = [_cyl((_AXLE, -150.0, _DIFF_Z), (_AXLE, 150.0, _DIFF_Z), _DIFF_R - 2.0)]
    for s in (-1.0, 1.0):
        parts.append(
            _cyl((_AXLE, s * 118.0, _DIFF_Z), (_AXLE, s * 150.0, _DIFF_Z), _DIFF_R)
        )
        parts.append(
            _cone(
                (_AXLE, s * 150.0, _DIFF_Z),
                (_AXLE, s * 168.0, _DIFF_Z),
                _DIFF_R - 2.0,
                46.0,
            )
        )
        # mounting ears back to the casing rear face
        for zz in (_DIFF_Z - 44.0, _DIFF_Z + 44.0):
            parts.append(
                _cyl(
                    (_AXLE - 6.0, s * 96.0, zz), (_BOX_AFT + 4.0, s * 96.0, zz), 15.0
                )
            )
    # crown-wheel bulge
    parts.append(
        _cone(
            (_AXLE + 26.0, -46.0, _DIFF_Z), (_AXLE + 4.0, -46.0, _DIFF_Z), 30.0, 52.0
        )
    )
    # cast cooling ribs around the barrel, and the cartridge bolt ring
    for i in range(7):
        a = math.pi * (0.5 + i) / 7.0
        dx, dz = math.cos(a), math.sin(a)
        for sy in (-1.0, 1.0):
            parts.append(
                _cyl(
                    (_AXLE + dx * 52.0, sy * 34.0, _DIFF_Z + dz * 52.0),
                    (_AXLE + dx * 52.0, sy * 138.0, _DIFF_Z + dz * 52.0),
                    13.0,
                )
            )
    for i in range(12):
        a = 2.0 * math.pi * (i + 0.5) / 12.0
        for sy in (-1.0, 1.0):
            parts.append(
                _cyl(
                    (_AXLE + math.cos(a) * 46.0, sy * 150.0,
                     _DIFF_Z + math.sin(a) * 46.0),
                    (_AXLE + math.cos(a) * 46.0, sy * 162.0,
                     _DIFF_Z + math.sin(a) * 46.0),
                    8.0,
                )
            )
    return _fuse(parts)


_DS_ROOT = (_AXLE, 186.0, _DIFF_Z)
_DS_HUB = (_AXLE, spec.REAR_HUB_Y, spec.HUB_Z)
_DS_U = _unit(_DS_ROOT, _DS_HUB)
_DS_L = (_v(_DS_HUB) - _v(_DS_ROOT)).length


def _ds(t):
    return _along(_DS_ROOT, _DS_U, t)


def _driveshaft_set():
    """Inner tripod housing, tapered shaft, open outer CV, hub stub."""
    n = _v(_DS_U)
    e1 = Vector(1, 0, 0)
    e2 = n.cross(e1).normalized()

    def ring(t, radius, a):
        p = _v(_ds(t)) + e1 * (radius * math.cos(a)) + e2 * (radius * math.sin(a))
        return (p.X, p.Y, p.Z)

    inner = _fuse(
        [
            _cone(_ds(-6.0), _ds(18.0), 40.0, 54.0),
            _cone(_ds(18.0), _ds(58.0), 54.0, 44.0),
            _cone(_ds(58.0), _ds(74.0), 44.0, 30.0),
        ]
    )
    inner = _cut(
        inner,
        [
            _cyl(
                ring(30.0, 46.0, 2.0 * math.pi * i / 3.0 + 0.4),
                ring(6.0, 46.0, 2.0 * math.pi * i / 3.0 + 0.4),
                13.0,
            )
            for i in range(3)
        ],
    )

    shaft = _fuse(
        [
            _cone(_ds(74.0), _ds(150.0), 26.0, 20.0),
            _cyl(_ds(150.0), _ds(400.0), 20.0),
            _cone(_ds(400.0), _ds(470.0), 20.0, 25.0),
            _cyl(_ds(470.0), _ds(486.0), 25.0),
        ]
    )

    outer = _fuse(
        [
            _cone(_ds(486.0), _ds(506.0), 30.0, 46.0),
            _cyl(_ds(506.0), _ds(548.0), 46.0),
            _cone(_ds(548.0), _ds(566.0), 46.0, 36.0),
            _cyl(_ds(566.0), _ds(_DS_L + 4.0), 26.0),
        ]
    )
    outer = _cut(
        outer,
        [
            _cyl(
                ring(512.0, 44.0, 2.0 * math.pi * i / 6.0),
                ring(544.0, 44.0, 2.0 * math.pi * i / 6.0),
                8.0,
            )
            for i in range(6)
        ],
    )
    return inner, shaft, outer


# ==========================================================================
# 6 / 7 — rear crash structure, pylon pad, rear light
# ==========================================================================


def _crash_structure(cut_tool):
    body = _table_loft(
        _TAIL, extra_x=(-3600.0, -3700.0, -3780.0, -3860.0, -3920.0, -3960.0)
    )
    return _cut(
        body,
        [
            # machined seat for the rear wing pylon
            _rbox(_PYLON_PAD_X, 0.0, 440.0, 90.0, 80.0, 112.0),
            # rear light aperture
            _rbox(-3986.0, 0.0, 371.0, 44.0, 68.0, 30.0),
            cut_tool,
        ],
    )


def _pylon_pad():
    pad = _fuse(
        [
            _rbox(_PYLON_PAD_X, 0.0, 385.0, 84.0, 74.0, 10.0),
            _rbox(_PYLON_PAD_X, 0.0, 379.0, 66.0, 58.0, 14.0),
        ]
    )
    return _cut(
        pad,
        [
            _cyl(
                (_PYLON_PAD_X + sx * 30.0, sy * 26.0, 392.0),
                (_PYLON_PAD_X + sx * 30.0, sy * 26.0, 376.0),
                5.0,
            )
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
        ],
    )


def _rear_light():
    bezel = _rbox(-3967.0, 0.0, 371.0, 8.0, 64.0, 26.0)
    bezel = bezel - _rbox(-3967.0, 0.0, 371.0, 12.0, 50.0, 14.0)
    lens = _rbox(-3969.0, 0.0, 371.0, 5.0, 49.0, 13.0)
    return bezel, lens


def _rear_pickup_carrier(side):
    """Cast yoke carrying the three aft inboard hardpoints."""
    s = 1.0 if side > 0 else -1.0

    def m(p):
        return (p[0], s * p[1], p[2])

    up = m(spec.R_UPPER_IN_AFT)
    lo = m(spec.R_LOWER_IN_AFT)
    root_hi = m((-3706.0, 66.0, 386.0))
    root_lo = m((-3700.0, 48.0, 366.0))

    parts = [
        _strut(root_hi, up, 104.0, 54.0, back=0.0, fwd=24.0),  # upper leg
        _strut(up, lo, 62.0, 58.0, back=24.0, fwd=24.0, thickness_ratio=0.34),
        _strut(root_lo, lo, 96.0, 62.0, back=0.0, fwd=24.0),  # lower leg
    ]
    for name in _aft_pickup_names():
        entry = next(e for e in REAR_PICKUPS if e[0] == name)
        _, point, axis, root, c0, c1, cheek_r, gap, pin_r = entry
        p = m(point)
        a = (axis[0], s * axis[1], axis[2])
        if root is not None:
            parts.append(
                _strut(m(root), p, c0, c1, back=0.0, fwd=cheek_r * 0.8,
                       thickness_ratio=0.34)
            )
        parts.append(_clevis(p, a, cheek_r, gap, pin_r))
    return _fuse(parts)


# ==========================================================================
# 8 — oil / hydraulic ancillaries
# ==========================================================================


def _oil_pump(outer):
    x, z = -3016.0, 202.0
    y0 = _surface_y(x, z) - 26.0
    body = _fuse(
        [
            _cyl((x, -y0, z), (x, -(y0 + 54.0), z), 38.0),
            _cone((x, -(y0 + 54.0), z), (x, -(y0 + 70.0), z), 38.0, 26.0),
            _cyl(
                (x - 54.0, -(y0 + 4.0), z + 14.0),
                (x - 54.0, -(y0 + 46.0), z + 14.0),
                20.0,
            ),
            _rbox(x - 26.0, -(y0 + 12.0), z, 108.0, 24.0, 92.0),
        ]
    )
    return body - outer


def _hydraulic_pack(outer):
    x0, x1 = -3348.0, -3474.0
    y = _surface_y(-3410.0, 366.0) + 16.0
    ymb = _surface_y(-3400.0, 314.0) + 4.0
    body = _fuse(
        [
            _cyl((x0, y, 366.0), (x1, y, 366.0), 27.0),
            _ball((x0, y, 366.0), 27.0),
            _ball((x1, y, 366.0), 27.0),
            _rbox(-3398.0, ymb + 16.0, 314.0, 96.0, 46.0, 56.0),
            _rbox(-3398.0, ymb + 34.0, 314.0, 72.0, 14.0, 40.0),
            _cyl((-3398.0, ymb + 12.0, 336.0), (-3398.0, y, 358.0), 11.0),
        ]
    )
    return body - outer


_LINE_YS = (46.0, 68.0, 90.0)  # outboard of the top spine
_LINE_RS = (7.5, 6.0, 4.8)
_LINE_LIFT = 19.0  # clears the 9 mm ring ribs


def _line_z(x, k):
    return _surface_z(x, _LINE_YS[k]) + _LINE_LIFT + 2.8 * k


def _line_bracket(x):
    pts = [(x, 34.0, _surface_z(x, 34.0) + 8.0)]
    pts += [(x, y, _line_z(x, k)) for k, y in enumerate(_LINE_YS)]
    pts.append((x, 102.0, _surface_z(x, 102.0) + 8.0))
    return _tube(pts, 5.0)


def _hydraulic_lines():
    lines = []
    for k, (y, r) in enumerate(zip(_LINE_YS, _LINE_RS)):
        xs = [-3430.0 + 89.0 * i for i in range(7)]
        lines.append(_tube([(x, y, _line_z(x, k)) for x in xs], r))
    # feed from the hydraulic pack up to the spine
    ymb = _surface_y(-3400.0, 314.0) + 4.0
    feed = _tube(
        [
            (-3406.0, ymb + 20.0, 322.0),
            (-3414.0, 110.0, 378.0),
            (-3424.0, 70.0, _line_z(-3424.0, 2) - 4.0),
            (-3430.0, 50.0, _line_z(-3430.0, 1)),
        ],
        6.0,
    )
    clips = [_line_bracket(x) for x in (-3350.0, -3260.0, -3150.0, -3040.0)]
    return _fuse(lines + [feed] + clips)


def _arb_platform(side, outer):
    s = 1.0 if side > 0 else -1.0
    slab = _y_prism(
        [
            (s * 100.0, -3222.0, 356.0, 62.0, 60.0),
            (s * 128.0, -3222.0, 356.0, 58.0, 56.0),
            (s * 146.0, -3222.0, 356.0, 48.0, 46.0),
        ],
        corner=16.0,
    )
    boss = [
        _cyl(
            (-3222.0, s * 120.0, spec.R_ARB_Z),
            (-3222.0, s * 172.0, spec.R_ARB_Z),
            24.0,
        ),
        _cone(
            (-3222.0, s * 172.0, spec.R_ARB_Z),
            (-3222.0, s * 182.0, spec.R_ARB_Z),
            24.0,
            18.0,
        ),
    ]
    return _fuse([slab] + boss) - outer


def _flank_pad(side, outer):
    s = 1.0 if side > 0 else -1.0
    slab = _y_prism(
        [
            (s * 90.0, -3430.0, 316.0, 128.0, 96.0),
            (s * 126.0, -3430.0, 316.0, 120.0, 90.0),
            (s * 142.0, -3430.0, 316.0, 104.0, 76.0),
        ],
        corner=24.0,
    )
    slab = _cut(
        slab,
        [
            _cyl(
                (
                    -3430.0 + 44.0 * math.cos(math.pi / 2.0 * i + math.pi / 4.0),
                    s * 160.0,
                    316.0 + 32.0 * math.sin(math.pi / 2.0 * i + math.pi / 4.0),
                ),
                (
                    -3430.0 + 44.0 * math.cos(math.pi / 2.0 * i + math.pi / 4.0),
                    s * 100.0,
                    316.0 + 32.0 * math.sin(math.pi / 2.0 * i + math.pi / 4.0),
                ),
                6.0,
            )
            for i in range(4)
        ],
    )
    return slab - outer


# ==========================================================================
# assembly
# ==========================================================================


def build_drivetrain():
    kids = []

    outer_ref = _casing_outer_ribbed()

    # Everything bolted to the casing is trimmed against the outer skin, so
    # the bolt-on hardware sits exactly on the casting and never shares
    # volume with it.
    oil_pump = _oil_pump(outer_ref)
    hyd_pack = _hydraulic_pack(outer_ref)
    hyd_lines = _hydraulic_lines()
    arb_l = _arb_platform(1, outer_ref)
    arb_r = _arb_platform(-1, outer_ref)
    pad_l = _flank_pad(1, outer_ref)
    pad_r = _flank_pad(-1, outer_ref)
    flange = _front_flange(outer_ref)
    bolts, dowels = _engine_mount_hardware()

    casing = _gearbox_casing(outer_ref)
    kids.append(lib.styled(casing, "gearbox_casing", spec.MAGNESIUM))
    kids.append(lib.styled(flange, "bellhousing_flange", spec.ANODIZED))
    kids.append(lib.styled(bolts, "engine_mount_bolts", spec.STEEL))
    kids.append(lib.styled(dowels, "engine_mount_dowels", spec.ALLOY))

    # --- clutch ---------------------------------------------------------
    hub, plates, pressure = _clutch()
    kids.append(lib.styled(hub, "clutch_hub", spec.ALLOY))
    for i, p in enumerate(plates):
        kids.append(lib.styled(p, f"clutch_plate_{i + 1}", spec.CARBON_DISC))
    kids.append(lib.styled(pressure, "clutch_pressure_ring", spec.ALLOY))

    # --- gear cluster ---------------------------------------------------
    upper, lower, primary = _gear_cluster()
    kids.append(lib.styled(upper, "input_shaft_cluster", spec.STEEL))
    kids.append(lib.styled(lower, "output_shaft_cluster", spec.STEEL))
    kids.append(lib.styled(primary, "primary_shaft_drop_gear", spec.STEEL))
    kids.append(lib.styled(_selector(1), "selector_barrel:left", spec.ALLOY))
    kids.append(lib.styled(_selector(-1), "selector_barrel:right", spec.ALLOY))

    # --- differential + driveshafts -------------------------------------
    kids.append(lib.styled(_differential(), "differential_housing", spec.MAGNESIUM))
    inner, shaft, outer_cv = _driveshaft_set()
    kids += lib.pair(inner, "cv_inner", spec.ANODIZED)
    kids += lib.pair(shaft, "driveshaft", spec.ALLOY)
    kids += lib.pair(outer_cv, "cv_outer", spec.ALLOY)

    # --- rear structure --------------------------------------------------
    carrier_l = _rear_pickup_carrier(1)
    carrier_r = _rear_pickup_carrier(-1)
    pad = _pylon_pad()
    bezel, lens = _rear_light()
    tail_cut = _fuse([carrier_l, carrier_r, pad, bezel, lens])
    kids.append(lib.styled(_crash_structure(tail_cut), "crash_structure", spec.CARBON))
    kids.append(lib.styled(pad, "rear_wing_pylon_pad", spec.ANODIZED))
    kids.append(lib.styled(bezel, "rear_light_bezel", spec.ANODIZED))
    kids.append(lib.styled(lens, "rear_light", spec.ACCENT))
    kids.append(lib.styled(carrier_l, "rear_pickup_carrier:left", spec.MAGNESIUM))
    kids.append(lib.styled(carrier_r, "rear_pickup_carrier:right", spec.MAGNESIUM))

    # --- ancillaries ------------------------------------------------------
    kids.append(lib.styled(oil_pump, "gearbox_oil_pump", spec.ALLOY))
    kids.append(lib.styled(hyd_pack, "hydraulic_power_pack", spec.ANODIZED))
    kids.append(lib.styled(hyd_lines, "hydraulic_lines", spec.TITANIUM))
    kids.append(lib.styled(arb_l, "arb_mount_platform:left", spec.ANODIZED))
    kids.append(lib.styled(arb_r, "arb_mount_platform:right", spec.ANODIZED))
    kids.append(lib.styled(pad_l, "casing_machined_pad:left", spec.ANODIZED))
    kids.append(lib.styled(pad_r, "casing_machined_pad:right", spec.ANODIZED))

    return lib.group("drivetrain", kids)
