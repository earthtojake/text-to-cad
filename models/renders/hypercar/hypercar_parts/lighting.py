"""Lighting -- the car's face.

The signature is ONE gesture per corner: a slim light-guide blade that runs
aft along the prow just under the fender crest, then turns hard down over the
crown of the front fender and dives into the corner intake.  Head-on the two
blades read as a pair of wide brackets framing the nose; in three-quarter view
the down-stroke is the event.

**A lamp graphic is only ever as good as the form it is cut into.**  A light
line drawn on an undifferentiated dome floats, because there is nothing for it
to be *parallel to* and nothing for it to *terminate into*.  So this module
also carries the three hard lines that give the prow its structure, and it
owns them because every one of them starts at the lamp:

``crown_crease``  sits exactly on the master surface's fender crest and runs
                  from the prow tip aft to the front-fascia shutline.  The
                  crest is already a ~90 deg corner in the master section; the
                  crease closes it to ~46 deg, which turns a soft outline into
                  a fender crown, and gives the DRL blade a line to run
                  beneath.  Two parallel lines read as structure; one line
                  alone reads as a decal.

``hood_crease``   the one that actually breaks the dome.  The crest is the
                  silhouette in every three-quarter view, so sharpening it
                  leaves the 700 mm of upper surface inboard of it untouched
                  -- and that expanse was the bloat.  This line branches off
                  the crown crease at the prow, diverges aft across the top
                  surface, and lands on (BX_FASCIA_F, BY_HOOD), the exact
                  corner where the hood|fender shutline starts, so the line
                  the eye is following becomes the panel gap and carries on
                  down the car.  Between the two creases the fender crown is a
                  defined wedge; inboard of them the hood valley is a defined
                  panel.

``cheek_crease``  picks up where the blade's down-stroke stops -- previously it
                  faded into nothing, which the brief forbids -- and carries it
                  aft and down into the leading edge of the front wheel arch.
                  That is the transition from the fender volume into the
                  corner intake.

All three are body-coloured and grown off the master surface, so they read as
the form tightening rather than as trim laid on top of it.

Everything else is subordinate.  The lamp aperture is a slim almond slung
directly under the blade holding four machined projector jewels with bronze
retaining rings.  The tail echoes the front exactly: one continuous blade
across the full width whose ends turn down and hook around the rear corners,
with a comb of fine vertical light guides recessed beneath it.

Construction notes
------------------
* The blades are lofted through frames built on the master surface, so they
  hug the body instead of floating on a plane.
* The creases are lofted through frames built on the crest *corner* of the
  master section, with the ridge normal taken as the bisector of the two
  surface normals meeting there, so a crease is a real sharpening of the
  master form rather than a strip laid on top of it.
* The lamp apertures are lofted through *section* profiles offset inside their
  own YZ plane, with the offset scaled by 1/(m.n) so the result is a true
  normal offset of the master surface.
* Nothing is filleted after a boolean.
"""

from __future__ import annotations

import math
from functools import lru_cache

from build123d import (
    Align,
    Box,
    Cone,
    Cylinder,
    Line,
    Plane,
    Pos,
    Spline,
    Torus,
    Vector,
    extrude,
    loft,
    make_face,
)

from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style
from hypercar_parts import palette as P


# ---------------------------------------------------------------------------
# master-surface queries
# ---------------------------------------------------------------------------

_OUTLINE_SAMPLES = 26


@lru_cache(maxsize=8192)
def _outline(x_quarter):
    """Dense (y, z) samples of the outer half-section, centreline -> floor.

    Rebuilt from ``surfaces.body_section_bands`` with the *same* end tangents
    ``surfaces._mirrored_face`` uses, so this is the real body outline and not
    an approximation of it.
    """
    x = x_quarter / 4.0
    bands = S.body_section_bands(x)
    last = len(bands) - 1
    pts = []
    for i, band in enumerate(bands):
        if i == 0 and last == 0:
            edge = Spline(*band, tangents=((1, 0), (-1, 0)))
        elif i == 0:
            edge = Spline(*band, tangents=((1, 0), S._dir(band[-2], band[-1])))
        elif i == last:
            edge = Spline(*band, tangents=(S._dir(band[0], band[1]), (-1, 0)))
        else:
            edge = Spline(*band)
        for k in range(_OUTLINE_SAMPLES + 1):
            if i and k == 0:
                continue
            v = edge @ (k / _OUTLINE_SAMPLES)
            pts.append((v.X, v.Y))
    return tuple(pts)


def _flank_y(x, z):
    """Outermost half-width of the body at station ``x``, height ``z``."""
    pts = _outline(round(x * 4.0))
    best = None
    for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
        if z0 == z1 or (z0 - z) * (z1 - z) > 0.0:
            continue
        y = y0 + (z - z0) / (z1 - z0) * (y1 - y0)
        if best is None or y > best:
            best = y
    if best is None:
        raise RuntimeError(f"no body section at x={x:.1f} z={z:.1f}")
    return best


_D = 4.0


def _slopes(x, z):
    dydx = (_flank_y(x + _D, z) - _flank_y(x - _D, z)) / (2.0 * _D)
    dydz = (_flank_y(x, z + _D) - _flank_y(x, z - _D)) / (2.0 * _D)
    return dydx, dydz


def _surf(x, z, side=1):
    """3D point + outward unit normal on the flank."""
    dydx, dydz = _slopes(x, z)
    y = _flank_y(x, z)
    n = Vector(-dydx, 1.0, -dydz).normalized()
    if side < 0:
        return Vector(x, -y, z), Vector(n.X, -n.Y, n.Z)
    return Vector(x, y, z), n


def _n2d(a, b):
    """Outward 2D normal of the section polyline segment ``a`` -> ``b``.

    A half-section is walked centreline-top -> outboard -> down -> centreline-
    floor, so rotating the tangent by +90 deg always points out of the body.
    """
    dy, dz = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dy, dz) or 1.0
    return (-dz / n, dy / n)


@lru_cache(maxsize=8192)
def _crest_raw(x_quarter):
    """(y, z, my, mz) of the fender-crest CORNER of the section at ``x``.

    ``surfaces.body_section_bands`` deliberately meets the top band and the
    flank band with free tangents, so the crest is a genuine ~90 deg corner in
    the master surface rather than a blend.  ``_flank_y`` cannot be used to
    find it: the crest is the highest point of the section, so a station a few
    millimetres forward -- where the crest has already dropped -- has no
    material at that height at all.  Read the corner off the bands instead,
    and take its normal as the bisector of the two surface normals that meet
    there, which is the direction a crease riding on that corner must grow in.
    """
    x = x_quarter / 4.0
    top, flank, _ = S.body_section_bands(x)
    y, z = top[-1]
    n1 = _n2d(top[-2], top[-1])
    n2 = _n2d(flank[0], flank[1])
    my, mz = n1[0] + n2[0], n1[1] + n2[1]
    m = math.hypot(my, mz) or 1.0
    return (y, z, my / m, mz / m)


def _crest_frame(x, side=1, d=5.0):
    """3D point + outward unit normal on the crest, square to the crest line.

    The bisector lives in the station plane, so it is orthogonalised against
    the crest's own tangent before use.  Without that the section planes fan
    as the crest sweeps outboard through the prow -- 1.4 mm of y per mm of x
    there -- and the loft wanders off the corner.
    """
    y0, z0, my, mz = _crest_raw(round(x * 4.0))
    ya, za, _, _ = _crest_raw(round((x - d) * 4.0))
    yb, zb, _, _ = _crest_raw(round((x + d) * 4.0))
    t = Vector(2.0 * d, yb - ya, zb - za).normalized()
    m = Vector(0.0, my, mz)
    n = (m - t * m.dot(t)).normalized()
    if side < 0:
        return Vector(x, -y0, z0), Vector(n.X, -n.Y, n.Z)
    return Vector(x, y0, z0), n


def _top_pt(x, t):
    """(y, z) on the UPPER surface at station ``x``, ``t`` of the way out.

    The same expression ``surfaces.body_section_bands`` samples its top band
    from, evaluated continuously instead of at eight points, so a curve built
    on it lies on the lofted surface rather than near it.
    """
    deck = S.DECK_Z(x)
    crest = S.CREST_Z(x)
    crest_y = 0.952 * S.HALF_WIDTH(x)
    z = deck + (crest - deck) * S._top_shape(t)
    ridge_h = S.RIDGE_H(x)
    if ridge_h > 0.01:
        z += ridge_h * math.exp(
            -(((t - S.RIDGE_POS(x)) / S.RIDGE_WIDTH(x)) ** 2))
    return crest_y * t, z


def _top_frame(x, t, side=1, dt=0.014, dx=5.0):
    """3D point + outward unit normal on the upper surface at (x, t)."""
    y0, z0 = _top_pt(x, t)
    ya, za = _top_pt(x, max(t - dt, 0.0))
    yb, zb = _top_pt(x, min(t + dt, 1.0))
    y1, z1 = _top_pt(x - dx, t)
    y2, z2 = _top_pt(x + dx, t)
    u = Vector(2.0 * dx, y2 - y1, z2 - z1)      # surface direction, forward
    v = Vector(0.0, yb - ya, zb - za)           # surface direction, outboard
    n = u.cross(v).normalized()
    if side < 0:
        return Vector(x, -y0, z0), Vector(n.X, -n.Y, n.Z)
    return Vector(x, y0, z0), n


def _off_yz(x, z, off, side=1):
    """(y, z) at a true normal offset ``off``, expressed in the station plane.

    Offsetting inside the section plane only moves along the 2D section normal
    ``m``; scaling by 1/(m.n) puts the resulting point at distance ``off`` from
    the real surface, which is what "1 mm proud" has to mean on a body whose
    sections sweep in X as hard as this nose does.
    """
    dydx, dydz = _slopes(x, z)
    y = _flank_y(x, z)
    s2 = math.hypot(1.0, dydz)
    d = off * math.sqrt(1.0 + dydx * dydx + dydz * dydz) / s2
    return (side * (y + d / s2), z - d * dydz / s2)


# ---------------------------------------------------------------------------
# centripetal Catmull-Rom -- smooth paths from a handful of waypoints
# ---------------------------------------------------------------------------


def _cr_point(p0, p1, p2, p3, t, alpha=0.5):
    def nxt(ti, a, b):
        return ti + max(math.dist(a, b), 1e-6) ** alpha

    t0 = 0.0
    t1 = nxt(t0, p0, p1)
    t2 = nxt(t1, p1, p2)
    t3 = nxt(t2, p2, p3)
    tt = t1 + (t2 - t1) * t

    def lerp(a, b, ta, tb):
        w = (tt - ta) / (tb - ta)
        return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)

    a1 = lerp(p0, p1, t0, t1)
    a2 = lerp(p1, p2, t1, t2)
    a3 = lerp(p2, p3, t2, t3)
    b1 = lerp(a1, a2, t0, t2)
    b2 = lerp(a2, a3, t1, t3)
    return lerp(b1, b2, t1, t2)


def _resample(way, n):
    """Smooth ``way`` into ~n well-spread points (endpoints preserved)."""

    def reflect(a, b):
        return (2.0 * a[0] - b[0], 2.0 * a[1] - b[1])

    ext = [reflect(way[0], way[1])] + list(way) + [reflect(way[-1], way[-2])]
    segs = [(ext[i - 1], ext[i], ext[i + 1], ext[i + 2])
            for i in range(1, len(ext) - 2)]
    lens = [max(math.dist(s[1], s[2]), 1e-6) for s in segs]
    total = sum(lens)
    out = []
    for i, (seg, ln) in enumerate(zip(segs, lens)):
        k = max(2, int(round(n * ln / total)))
        stop = k + 1 if i == len(segs) - 1 else k
        for j in range(stop):
            out.append(_cr_point(*seg, j / k))
    return out


# ---------------------------------------------------------------------------
# the light-guide blade: a thin section swept along a surface-hugging path
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _slat(half_w, half_h, power, n=40):
    """Closed superellipse face: a machined slat with softened corners.

    One periodic spline edge rather than the eight of ``RectangleRounded``.
    That matters: ThruSections goes numerically unstable lofting dozens of
    eight-edge wires and throws the surface ~20 mm off the section planes,
    while a single-edge section lofts exactly and roughly twice as fast.
    """
    pts = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        c, s = math.cos(th), math.sin(th)
        pts.append((
            half_w * math.copysign(abs(c) ** (2.0 / power), c),
            half_h * math.copysign(abs(s) ** (2.0 / power), s),
        ))
    return make_face(Spline(*pts, periodic=True))


def _blade(pts, nrms, depth, height, off, scale=None, power=3.2):
    """Loft a slat section along a 3D path.

    ``off`` is the standoff of the OUTER face from the surface; the section
    grows inward from there, so the blade never sinks into the panel it lies
    on however the surface rolls underneath it.
    """
    secs = []
    m = len(pts)
    for i in range(m):
        p, nv = pts[i], nrms[i]
        if i == 0:
            t = pts[1] - pts[0]
        elif i == m - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        t = t.normalized()
        xd = -nv
        xd = (xd - t * xd.dot(t)).normalized()
        f = 1.0 if scale is None else scale(i / (m - 1))
        w = depth * (0.42 + 0.58 * f)
        h = height * f
        pl = Plane(origin=p + nv * (off - w / 2.0), x_dir=xd, z_dir=t)
        secs.append(
            (pl * _slat(round(w / 2.0, 3), round(h / 2.0, 3), power)).faces()[0]
        )
    return loft(secs)


def _flank_panel(stations, z_lo, z_hi, off_a, off_b, side, nz=14):
    """Slab hugging the flank between two normal offsets over a z band."""
    faces = []
    for x in stations:
        lo, hi = z_lo(x), z_hi(x)
        outer, inner = [], []
        for k in range(nz + 1):
            z = lo + (hi - lo) * k / nz
            outer.append(_off_yz(x, z, off_a, side))
            inner.append(_off_yz(x, z, off_b, side))
        wire = (
            Spline(*outer)
            + Line(outer[-1], inner[-1])
            + Spline(*list(reversed(inner)))
            + Line(inner[0], outer[0])
        )
        faces.append(Plane.YZ.offset(x) * make_face(wire))
    return loft(faces)


# ---------------------------------------------------------------------------
# FRONT -- signature blade + lamp internals
# ---------------------------------------------------------------------------

# (x, z) waypoints, forward tip first.  The turn is deliberately wide: a tight
# one folds the blade back on itself and the sliver of body trapped inside the
# fold reads as an accident rather than a hook.
#
# The apex used to be pushed right up onto the crest.  It now tops out ~25 mm
# under it, which is the clearance the crown crease needs: the crease owns the
# crest, the light runs beneath it, and the two stay parallel through the turn
# instead of colliding at the one point where the eye is looking hardest.
_FRONT_WAY = [
    (2248, 400),
    (2224, 417),
    (2194, 437),
    (2158, 459),
    (2118, 481),
    (2076, 506),
    (2036, 532),
    (2000, 559),
    (1970, 583),
    (1948, 603),
    (1932, 620),
    (1918, 630),
    (1900, 632),
    (1884, 623),
    (1872, 604),
    (1863, 578),
    (1857, 545),
    (1855, 506),
    (1856, 462),
    (1861, 415),
    (1869, 368),
]

_FRONT_N = 60
_RUN_X_MIN = 1940.0

LAMP_X0, LAMP_X1 = 1982.0, 2180.0
LAMP_DROP = 8.0         # aperture top, below the blade centreline
LAMP_HEIGHT = 64.0
LAMP_STATIONS = 15

_PROJECTORS = ((2020.0, 18.5), (2060.0, 19.0), (2100.0, 18.0), (2140.0, 16.0))


def _front_scale(s):
    a = min(s / 0.085, 1.0)
    b = min((1.0 - s) / 0.10, 1.0)
    return 0.30 + 0.70 * min(a, b) ** 0.55


@lru_cache(maxsize=4)
def _front_path():
    dense = _resample(_FRONT_WAY, _FRONT_N)
    run = sorted((p for p in dense if p[0] >= _RUN_X_MIN), key=lambda p: p[0])
    return tuple(dense), tuple(run)


def _blade_z(x):
    _, run = _front_path()
    if x <= run[0][0]:
        return run[0][1]
    if x >= run[-1][0]:
        return run[-1][1]
    for (x0, z0), (x1, z1) in zip(run, run[1:]):
        if x0 <= x <= x1 and x1 > x0:
            return z0 + (x - x0) / (x1 - x0) * (z1 - z0)
    return run[-1][1]


def _lamp_taper(x):
    s = min(max((x - LAMP_X0) / (LAMP_X1 - LAMP_X0), 0.0), 1.0)
    return 0.20 + 0.80 * (4.0 * s * (1.0 - s)) ** 0.42


def _lamp_hi(x):
    return _blade_z(x) - LAMP_DROP


def _lamp_lo(x):
    return _lamp_hi(x) - LAMP_HEIGHT * _lamp_taper(x)


def _lamp_stations():
    return [LAMP_X0 + (LAMP_X1 - LAMP_X0) * i / (LAMP_STATIONS - 1)
            for i in range(LAMP_STATIONS)]


def _projector(x, side, r_out, kids):
    """One jewel, packaged SHALLOW.

    A lamp buried 50 mm behind the skin is invisible from every angle a car is
    ever photographed at.  The cluster sits in the first 35 mm instead, so the
    bronze rings land a couple of millimetres under the lens plane.
    """
    z = 0.5 * (_lamp_hi(x) + _lamp_lo(x))
    p, n = _surf(x, z, side)
    tag = f"{int(x)}_{'left' if side > 0 else 'right'}"

    barrel = Plane(origin=p + n * -34.0, z_dir=n) * Cylinder(
        r_out + 3.5, 32.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    kids.append(style(barrel, f"projector_barrel:{tag}", P.ALUMINIUM_DARK))

    cup = Plane(origin=p + n * -24.0, z_dir=n) * Cone(
        0.38 * r_out, r_out, 22.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN))
    kids.append(style(cup, f"projector_cup:{tag}", P.ALUMINIUM))

    # A sphere here shows only a 4 mm crown once it is packaged flush, which
    # reads as a dark hole.  A disc face brought to the lens plane reads as
    # what it is: a lit module, ringed in bronze.
    lens = Plane(origin=p + n * -11.0, z_dir=n) * Cylinder(
        0.74 * r_out, 11.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    kids.append(style(lens, f"projector_lens:{tag}", P.LAMP_HOT))

    ring = Plane(origin=p + n * -1.8, z_dir=n) * Torus(r_out + 1.4, 2.1)
    kids.append(style(ring, f"projector_ring:{tag}", P.BRONZE))


# ---------------------------------------------------------------------------
# the structure the lamp graphic sits in
# ---------------------------------------------------------------------------
#
# These are creases, not trim: body-coloured, sharp-ridged, and grown straight
# off the master surface, so they read as the form tightening rather than as a
# strip glued to it.  A crease has to be a *solid* here -- the body is opaque,
# so a recess would simply be invisible -- hence a section whose apex stands
# *_PROUD off the surface and whose flanks run back into it.
#
# Two things decide whether that reads as a crease or as a rod lying on the
# panel, and both had to be found the hard way:
#
#   * POWER.  _slat's superellipse is |x/a|^p + |y/b|^p = 1, so near the apex
#     x ~= a - a(|y|/b)^p and dx/dy -> 0 for any p > 1: every p above 1 gives a
#     FLAT top, not a ridge.  Only p = 1 -- a true diamond -- puts a corner
#     there.  (The periodic spline through the sampled points still relieves it
#     to a few millimetres of radius, which is what a real crease has.)
#   * ASPECT.  Proudness must be small against width or the section reads as a
#     tube.  At 11 proud x 42 wide it looked like a rod laid on the hood; at
#     9 proud x 86 wide the flanks fall at ~16 deg and it reads as the surface
#     itself breaking.

CROWN_X_TIP = 2291.0     # prow -- terminates on the nose cap edge (x = 2300);
                         # the end cap is raked ~45 deg in plan, so this is as
                         # far forward as the crease can go without a sliver of
                         # it hanging off the front of the car
CROWN_X_AFT = 1810.5     # loft end station.  The section is raked ~45 deg to the
                         # crest, so the end CAP reaches back to BX_FASCIA_F + _G =
                         # 1797.5 -- the aft edge of the fascia panel.  Ending the
                         # loft at 1795 instead put 15 mm of solid across the
                         # 5 mm hood shutline and plugged it.
CROWN_N = 58
CROWN_DEPTH = 26.0       # section depth along the surface normal
CROWN_WIDTH = 64.0       # section width across the crest
CROWN_PROUD = 8.0        # ridge standoff from the master surface
CREASE_POWER = 1.0


def _crown_scale(s):
    """s = 0 at the prow tip, 1 at the shutline.

    Full section for the whole run over the fender; only the prow, where the
    crest corner itself is barely 87 deg and the section is 220 mm wide, is
    taken down -- a full-size ridge there reads as a spike on the point of the
    nose.  It stops at 0.46, not 0, because a crease must terminate ON
    something and this one terminates on the nose cap edge.
    """
    return 0.46 + 0.54 * min(s / 0.42, 1.0) ** 0.7


def _crown_crease(side):
    pts, nrms = [], []
    for i in range(CROWN_N):
        s = i / (CROWN_N - 1)
        p, n = _crest_frame(CROWN_X_TIP + (CROWN_X_AFT - CROWN_X_TIP) * s, side)
        pts.append(p)
        nrms.append(n)
    return _blade(pts, nrms, CROWN_DEPTH, CROWN_WIDTH, CROWN_PROUD,
                  _crown_scale, CREASE_POWER)


# The blade's down-stroke ends at (1869, 368); the arch leading edge is the
# circle of radius FRONT_ARCH_R about (FRONT_AXLE_X, FRONT_HUB_Z), which at
# z = 308 sits at x = 1738.  The crease spans exactly that: light line in,
# arch edge out, nothing floating at either end.
_CHEEK_WAY = [
    (1869, 368),
    (1848, 352),
    (1820, 338),
    (1790, 327),
    (1762, 317),
    (1740, 309),
]
_CHEEK_N = 26
CHEEK_DEPTH = 20.0
CHEEK_WIDTH = 46.0
CHEEK_PROUD = 7.0


def _cheek_scale(s):
    """Grows out of the blade's tail, which is itself at 0.30 scale."""
    return 0.30 + 0.70 * min(s / 0.55, 1.0) ** 0.8


def _cheek_crease(side):
    pts, nrms = [], []
    for x, z in _resample(_CHEEK_WAY, _CHEEK_N):
        p, n = _surf(x, z, side)
        pts.append(p)
        nrms.append(n)
    return _blade(pts, nrms, CHEEK_DEPTH, CHEEK_WIDTH, CHEEK_PROUD,
                  _cheek_scale, CREASE_POWER)


# The crest is the silhouette in every three-quarter view, so a crease there
# sharpens the outline but leaves the 700 mm-wide top surface inboard of it as
# one unbroken dome -- which is precisely what read as bloat.  This third line
# is the one that cuts across it: it branches off the crown crease at the prow
# and diverges aft, so the fender crown becomes a defined wedge and the hood
# valley becomes a defined panel between the two of them.  It lands on
# (BX_FASCIA_F, BY_HOOD) -- the exact corner where the hood|fender shutline
# starts -- so the line the eye is following simply becomes the panel gap and
# carries on down the car.

HOOD_X_TIP = 2272.0
HOOD_X_AFT = S.BX_FASCIA_F        # 1795 -- where the design curve is aimed
HOOD_X_END = 1801.4               # where the loft stops, so the raked end cap
                                  # lands on the fascia's aft edge and not across
                                  # the shutline itself
HOOD_N = 46
HOOD_DEPTH = 24.0
HOOD_WIDTH = 86.0
HOOD_PROUD = 9.0


def _hood_t(x):
    """Fraction of the way from centreline to crest, as a function of x.

    ``e = s ** 1.35`` has zero slope at the prow, so the branch leaves the
    crown crease tangentially instead of forking off it at an angle.
    """
    s = min(max((HOOD_X_TIP - x) / (HOOD_X_TIP - HOOD_X_AFT), 0.0), 1.0)
    t_aft = S.BY_HOOD / (0.952 * S.HALF_WIDTH(HOOD_X_AFT))
    return 1.0 + (t_aft - 1.0) * s ** 1.35


def _hood_scale(s):
    return 0.52 + 0.48 * min(s / 0.35, 1.0) ** 0.75


def _hood_crease(side):
    pts, nrms = [], []
    for i in range(HOOD_N):
        s = i / (HOOD_N - 1)
        x = HOOD_X_TIP + (HOOD_X_END - HOOD_X_TIP) * s
        p, n = _top_frame(x, _hood_t(x), side)
        pts.append(p)
        nrms.append(n)
    return _blade(pts, nrms, HOOD_DEPTH, HOOD_WIDTH, HOOD_PROUD,
                  _hood_scale, CREASE_POWER)


def _front(side):
    kids = []
    name = "left" if side > 0 else "right"

    kids.append(style(_crown_crease(side), f"crown_crease:{name}", P.BODY))
    kids.append(style(_hood_crease(side), f"hood_crease:{name}", P.BODY))
    kids.append(style(_cheek_crease(side), f"cheek_crease:{name}", P.BODY))

    dense, _ = _front_path()
    pts, nrms = [], []
    for x, z in dense:
        p, n = _surf(x, z, side)
        pts.append(p)
        nrms.append(n)

    trough = _blade(pts, nrms, 28.0, 26.0, -4.0, _front_scale)
    kids.append(style(trough, f"drl_trough:{name}", P.CARBON))

    blade = _blade(pts, nrms, 24.0, 14.0, 3.0, _front_scale)
    kids.append(style(blade, f"drl_blade:{name}", P.LAMP_HOT))

    stations = _lamp_stations()

    # The bezel is a U, not a ring: closing it across the top would put a
    # second hairline right under the blade and the pair would read as a
    # doubled line.  Open at the top, the aperture and the blade are one
    # graphic -- a lit edge with a dark void hanging off it.
    outer = _flank_panel(
        stations, lambda x: _lamp_lo(x) - 13.0, _lamp_hi, 1.0, -22.0, side)
    inner = _flank_panel(
        stations[1:-1], _lamp_lo, lambda x: _lamp_hi(x) + 6.0,
        4.0, -25.0, side)
    try:
        bezel = outer - inner
    except Exception:  # pragma: no cover -- kernel fallback
        bezel = outer
    kids.append(style(bezel, f"lamp_bezel:{name}", P.ALUMINIUM_DARK))

    cavity = _flank_panel(stations, _lamp_lo, _lamp_hi, -13.0, -33.0, side)
    kids.append(style(cavity, f"lamp_cavity:{name}", P.CARBON))

    bar_stations = [x for x in stations if LAMP_X0 + 14 <= x <= LAMP_X1 - 14]
    bar = _flank_panel(
        bar_stations,
        lambda x: _lamp_lo(x) + 3.0,
        lambda x: _lamp_lo(x) + 9.5,
        0.5, -16.0, side, nz=4)
    kids.append(style(bar, f"lamp_bar:{name}", P.LAMP_HOT))

    for x, r in _PROJECTORS:
        _projector(x, side, r, kids)

    return kids


# ---------------------------------------------------------------------------
# REAR -- one full-width blade with hooked ends, comb of guides beneath
# ---------------------------------------------------------------------------

TAIL_X = -2400.0

_REAR_HALF = [
    (0, 730),
    (170, 729),
    (340, 726),
    (490, 721),
    (612, 713),
    (704, 702),
    (776, 685),
    (826, 656),
    (850, 622),
    (858, 588),
]

_REAR_N = 68

TAIL_Y0, TAIL_Y1 = 250.0, 756.0
TAIL_DROP = 35.0        # aperture centreline, below the blade
TAIL_HALF_H = 29.0


@lru_cache(maxsize=2)
def _rear_path():
    full = [(-y, z) for y, z in reversed(_REAR_HALF[1:])] + list(_REAR_HALF)
    return tuple(_resample(full, _REAR_N))


def _tail_z(y):
    a = abs(y)
    tab = _REAR_HALF
    if a >= tab[-1][0]:
        return tab[-1][1]
    for (y0, z0), (y1, z1) in zip(tab, tab[1:]):
        if y0 <= a <= y1:
            return z0 + (a - y0) / (y1 - y0) * (z1 - z0)
    return tab[0][1]


def _rear_scale(s):
    return 0.34 + 0.66 * min(min(s, 1.0 - s) / 0.055, 1.0) ** 0.55


def _tail_profile(side, grow=0.0, lift=0.0, n=30):
    """Almond aperture in the tail plane.

    ``grow`` fattens it downward and sideways; ``lift`` raises only the top
    edge.  Keeping the two separate is what lets the bezel be a U rather than
    a ring, so the aperture opens straight into the underside of the blade.
    """
    span = max(grow, lift)
    y0 = TAIL_Y0 - span * 1.6
    y1 = TAIL_Y1 + span * 1.6
    hi, lo = [], []
    for i in range(n + 1):
        s = i / n
        y = y0 + (y1 - y0) * s
        f = 0.17 + 0.83 * (4.0 * s * (1.0 - s)) ** 0.42
        zc = _tail_z(min(max(y, TAIL_Y0), TAIL_Y1)) - TAIL_DROP
        hi.append((side * y, zc + max(TAIL_HALF_H * f + lift, 3.0)))
        lo.append((side * y, zc - max(TAIL_HALF_H * f + grow, 3.0)))
    wire = (
        Spline(*hi)
        + Line(hi[-1], lo[-1])
        + Spline(*list(reversed(lo)))
        + Line(lo[0], hi[0])
    )
    return Plane.YZ.offset(TAIL_X) * make_face(wire)


def _tail_slab(side, grow, x0, depth, lift=None):
    face = _tail_profile(side, grow, grow if lift is None else lift)
    return Pos(x0 - TAIL_X, 0, 0) * extrude(face, amount=depth, dir=(1, 0, 0))


def _tail_ring(side, g_out, g_in, x0, depth, lift_out=0.0, lift_in=6.0):
    face = (_tail_profile(side, g_out, lift_out)
            - _tail_profile(side, g_in, lift_in))
    return Pos(x0 - TAIL_X, 0, 0) * extrude(face, amount=depth, dir=(1, 0, 0))


def _tail_bar_face(side, n=26):
    """Slim strip hugging the lower edge of the aperture.

    The front lamp closes with a light bar under its jewels; repeating it here
    is what makes the two ends of the car read as one family rather than two
    unrelated graphics.
    """
    y0, y1 = TAIL_Y0 + 32.0, TAIL_Y1 - 44.0
    hi, lo = [], []
    for i in range(n + 1):
        y = y0 + (y1 - y0) * i / n
        sa = (y - TAIL_Y0) / (TAIL_Y1 - TAIL_Y0)
        f = 0.17 + 0.83 * (4.0 * sa * (1.0 - sa)) ** 0.42
        zb = _tail_z(y) - TAIL_DROP - TAIL_HALF_H * f + 4.0
        hi.append((side * y, zb + 7.0))
        lo.append((side * y, zb))
    wire = (
        Spline(*hi)
        + Line(hi[-1], lo[-1])
        + Spline(*list(reversed(lo)))
        + Line(lo[0], hi[0])
    )
    return Plane.YZ.offset(TAIL_X) * make_face(wire)


def _rear():
    kids = []

    dense = _rear_path()
    pts = [Vector(TAIL_X, y, z) for y, z in dense]
    nrms = [Vector(-1, 0, 0)] * len(pts)

    trough = _blade(pts, nrms, 28.0, 26.0, -4.0, _rear_scale)
    kids.append(style(trough, "tail_trough:centre", P.CARBON))

    blade = _blade(pts, nrms, 24.0, 14.0, 3.0, _rear_scale)
    kids.append(style(blade, "tail_blade:centre", P.LAMP_RED_HOT))

    for side in (1, -1):
        name = "left" if side > 0 else "right"

        kids.append(style(_tail_ring(side, 12.0, 0.0, TAIL_X - 1.0, 23.0),
                          f"tail_bezel:{name}", P.CARBON_GLOSS))
        kids.append(style(_tail_ring(side, 0.0, -9.0, TAIL_X + 14.0, 22.0,
                                     lift_out=0.0, lift_in=8.0),
                          f"tail_shroud:{name}", P.CARBON))
        kids.append(style(_tail_slab(side, -9.0, TAIL_X + 36.0, 10.0),
                          f"tail_backplate:{name}", P.ALUMINIUM_DARK))

        n_fin = 17
        fy0, fy1 = TAIL_Y0 + 40.0, TAIL_Y1 - 56.0
        for i in range(n_fin):
            y = fy0 + (fy1 - fy0) * i / (n_fin - 1)
            s = (y - TAIL_Y0) / (TAIL_Y1 - TAIL_Y0)
            f = 0.17 + 0.83 * (4.0 * s * (1.0 - s)) ** 0.42
            h = max(13.0, 2.0 * TAIL_HALF_H * f - 20.0)
            zc = _tail_z(y) - TAIL_DROP + 3.0
            fin = Pos(TAIL_X + 15.0, side * y, zc) * Box(32.0, 4.2, h)
            kids.append(style(fin, f"tail_fin:{name}_{i}", P.LAMP_RED_HOT))

        bar = Pos(-0.5, 0, 0) * extrude(
            _tail_bar_face(side), amount=18.0, dir=(1, 0, 0))
        kids.append(style(bar, f"tail_bar:{name}", P.LAMP_RED_HOT))

    return kids


# ---------------------------------------------------------------------------


def build():
    kids = []
    for side in (1, -1):
        kids.extend(_front(side))
    kids.extend(_rear())
    return group("lighting", kids)
