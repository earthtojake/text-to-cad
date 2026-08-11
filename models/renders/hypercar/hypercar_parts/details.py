"""Details -- the jewellery pass.

This module owns everything that is read at arm's length rather than at
thumbnail size: door mirrors, badging, the fuel filler, the louvred outlets and
the visible fasteners.  Two rules govern all of it.

**Everything is placed ON the master surface, never near it.**  Each piece asks
``surfaces`` for the real body point and the real outward normal and then works
in that local frame, so a 0.4 mm proud backing plate is 0.4 mm proud everywhere
along its length however the panel rolls underneath.

**Every feature line terminates into something.**  The louvres are the clearest
case: their leading edge is drawn *parallel to the wheel-arch cut*, 34 mm off
it, so the gill reads as a consequence of the arch rather than a sticker near
it, and every blade dies into a machined rail at both ends instead of fading
out.  Front and rear gills are the same shape scaled, which ties the two ends
of the car together.

Construction notes
------------------
* Flank work lofts along X through sections in YZ planes; work that follows a
  constant height (the louvre blades' own outline) lofts along Z through
  sections in XY planes.  Both use true *normal* offsets of the master surface,
  not in-plane offsets, so nothing sinks into the paint on a swept section.
* The mirror head is one loft plus two prism cuts -- a raked facet for the
  glass and a pocket in it.  No 3D fillets anywhere.
* The bonnet extractor blades fill the apertures ``body`` already cuts in the
  hood; their coordinates are derived from the same numbers.
"""

from __future__ import annotations

import math
from functools import lru_cache

from build123d import (
    Align,
    Box,
    Cylinder,
    Line,
    Location,
    Plane,
    Polyline,
    Pos,
    RectangleRounded,
    Spline,
    Vector,
    extrude,
    loft,
    make_face,
)

from cadgen import compound_from_instances

from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style
from hypercar_parts import palette as P


# ---------------------------------------------------------------------------
# master-surface queries
# ---------------------------------------------------------------------------

_OUTLINE_SAMPLES = 18


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


def _top_z(x, y):
    """Height of the TOP surface at station ``x``, half-width ``y``."""
    pts = _outline(round(x * 4.0))
    a = abs(y)
    best = None
    for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
        if y0 == y1 or (y0 - a) * (y1 - a) > 0.0:
            continue
        z = z0 + (a - y0) / (y1 - y0) * (z1 - z0)
        if best is None or z > best:
            best = z
    if best is None:
        raise RuntimeError(f"no top surface at x={x:.1f} y={y:.1f}")
    return best


_D = 4.0


def _slopes(x, z):
    dydx = (_flank_y(x + _D, z) - _flank_y(x - _D, z)) / (2.0 * _D)
    dydz = (_flank_y(x, z + _D) - _flank_y(x, z - _D)) / (2.0 * _D)
    return dydx, dydz


def _surf(x, z, side=1):
    """3D point + outward unit normal on the FLANK."""
    dydx, dydz = _slopes(x, z)
    y = _flank_y(x, z)
    n = Vector(-dydx, 1.0, -dydz).normalized()
    if side < 0:
        return Vector(x, -y, z), Vector(n.X, -n.Y, n.Z)
    return Vector(x, y, z), n


def _top_surf(x, y):
    """3D point + outward unit normal on the TOP surface."""
    dzdx = (_top_z(x + _D, y) - _top_z(x - _D, y)) / (2.0 * _D)
    dzdy = (_top_z(x, y + _D) - _top_z(x, y - _D)) / (2.0 * _D)
    return (
        Vector(x, y, _top_z(x, y)),
        Vector(-dzdx, -dzdy, 1.0).normalized(),
    )


def _off_yz(x, z, off, side=1):
    """(y, z) at a true normal offset ``off``, expressed in the station plane.

    Offsetting inside the section plane only moves along the 2D section normal
    ``m``; scaling by 1/(m.n) puts the result at distance ``off`` from the real
    surface, which is what "1 mm proud" has to mean on a flank whose sections
    sweep in X as hard as this one does.
    """
    dydx, dydz = _slopes(x, z)
    y = _flank_y(x, z)
    s2 = math.hypot(1.0, dydz)
    d = off * math.sqrt(1.0 + dydx * dydx + dydz * dydz) / s2
    return (side * (y + d / s2), z - d * dydz / s2)


def _off_xy(x, z, off, side=1):
    """(x, y) at a true normal offset ``off``, expressed in the Z=z plane."""
    dydx, dydz = _slopes(x, z)
    y = _flank_y(x, z)
    s1 = math.hypot(1.0, dydx)
    d = off * math.sqrt(1.0 + dydx * dydx + dydz * dydz) / s1
    return (x - d * dydx / s1, side * (y + d / s1))


# ---------------------------------------------------------------------------
# small shared primitives
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _slat(half_w, half_h, power=3.0, n=36):
    """Closed superellipse face: a machined section with softened corners.

    One periodic spline edge rather than the eight of ``RectangleRounded`` --
    ThruSections is far better behaved lofting single-edge wires.
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


def _quad_face(pts_yz, x):
    """Closed 4-point face in the station plane at ``x`` (points are (y, z))."""
    return Plane.YZ.offset(x) * make_face(Polyline(*pts_yz, pts_yz[0]))


# ---------------------------------------------------------------------------
# DOOR MIRRORS -- a slim aerofoil head on a sculptural stalk
# ---------------------------------------------------------------------------
#
# The head is a horizontal wing: long in chord, wide in span, thin in section,
# so it is nearly invisible in side view and reads as a blade from the front
# three-quarter.  Its trailing face is raked inboard and carries the glass, and
# the stalk is a second, smaller aerofoil that grows out of the door skin --
# one gesture, two elements, no brackets.

MIRROR_X = 560.0
MIRROR_Y = 966.0
MIRROR_Z = 808.0
MIRROR_CHORD = 210.0

# (s along chord: 0 = leading edge, 1 = trailing) -> (half span Y, half thick Z)
#
MIRROR_HALF_SPAN = 55.0
MIRROR_HALF_THICK = 25.5

# The head is the FRONT HALF of a NACA thickness distribution: a truly
# elliptical leading edge, maximum section at 60 % of the pod's length, and a
# trailing face still at 94 % of maximum -- a Kammback aerofoil, not a
# teardrop.  It is written as a formula rather than a table on purpose.  Two
# earlier versions failed here: a linearly-interpolated table is only C0, so
# every knot became a crease the loft reproduced faithfully; and lofting the
# knots directly left the section spacing so uneven that the surface rang
# between the tight clusters.  A smooth law sampled on smoothly-graded stations
# has neither failure mode.
_POD_STATIONS = 16
_POD_U0 = 0.0035
_NACA_PEAK = 0.09963          # value of the distribution at its maximum


def _naca(s):
    return (0.2969 * math.sqrt(s) - 0.1260 * s - 0.3516 * s * s
            + 0.2843 * s ** 3 - 0.1015 * s ** 4)


def _pod_section(u):
    """(half span, half thickness) at fraction ``u`` of the pod's length."""
    r = _naca(0.50 * u) / _NACA_PEAK
    return MIRROR_HALF_SPAN * r, MIRROR_HALF_THICK * r ** 0.80


def _pod_axis(side):
    """Chord direction of the head: toed out a little, nose up a little."""
    return Vector(1.0, side * 0.10, 0.045).normalized()


def _glass_frame(side):
    """Plane of the mirror glass: raked aft-inboard and tipped down."""
    n = Vector(-1.0, side * -0.40, -0.13).normalized()
    a = _pod_axis(side)
    centre = Vector(MIRROR_X, side * MIRROR_Y, MIRROR_Z)
    origin = centre - a * (0.5 * MIRROR_CHORD - 27.0)
    up = Vector(0, 0, 1)
    xd = (up.cross(n)).normalized()
    return Plane(origin=origin, x_dir=xd, z_dir=n)


def _mirror_head(side):
    a = _pod_axis(side)
    centre = Vector(MIRROR_X, side * MIRROR_Y, MIRROR_Z)
    nose = centre + a * (0.5 * MIRROR_CHORD)
    yd = Vector(0, 1, 0)
    xd = (yd - a * yd.dot(a)).normalized()

    secs = []
    for i in range(_POD_STATIONS):
        t = (i / (_POD_STATIONS - 1.0)) ** 1.25
        u = _POD_U0 + (1.0 - _POD_U0) * t
        hw, hh = _pod_section(u)
        pl = Plane(origin=nose - a * (u * MIRROR_CHORD), x_dir=xd, z_dir=a)
        secs.append((pl * _slat(round(hw, 3), round(hh, 3), 2.5)).faces()[0])
    return loft(secs)


def _mirror(side):
    name = "left" if side > 0 else "right"
    kids = []

    pod = _mirror_head(side)
    gp = _glass_frame(side)

    # rake the trailing face off, then sink a pocket into it
    facet = gp * Box(520, 520, 520, align=(Align.CENTER, Align.CENTER, Align.MIN))
    pocket = gp * Pos(0, 0, -13.0) * extrude(
        RectangleRounded(92.0, 40.0, 12.0), amount=14.0)
    housing = (pod - facet) - pocket
    kids.append(style(housing, f"mirror_housing:{name}", P.BODY))

    bezel_face = (Pos(0, 0, 0) * RectangleRounded(92.0, 40.0, 12.0)
                  - Pos(0, 0, 0) * RectangleRounded(82.0, 31.0, 8.4))
    bezel = gp * Pos(0, 0, -4.6) * extrude(bezel_face, amount=4.6)
    kids.append(style(bezel, f"mirror_bezel:{name}", P.BRONZE))

    glass = gp * Pos(0, 0, -9.0) * extrude(
        RectangleRounded(81.0, 30.0, 8.0), amount=4.2)
    kids.append(style(glass, f"mirror_glass:{name}", P.ALUMINIUM))

    # ---- stalk: a second aerofoil growing out of the door skin -------------
    #
    # Wide in chord and thin in section, so from the front three-quarter it is
    # a blade standing off the door, and from the side it nearly disappears --
    # the pod appears to be cantilevered on nothing.
    root_p, root_n = _surf(466.0, 712.0, side)
    w1 = root_p + root_n * 30.0 + Vector(6.0, 0, 20.0)
    w2 = Vector(516.0, side * (abs(root_p.Y) + 76.0), 768.0)
    tip = Vector(MIRROR_X - 30.0, side * (MIRROR_Y - 44.0), MIRROR_Z - 7.0)
    path = Spline(root_p - root_n * 24.0, w1, w2, tip)

    n_st = 15
    secs = []
    for i in range(n_st + 1):
        t = i / n_st
        p = path @ t
        d = Vector(path % t).normalized()
        xd = Vector(1, 0, 0)
        xd = (xd - d * xd.dot(d)).normalized()
        chord = 86.0 - 28.0 * t ** 1.35
        thick = 15.5 - 4.5 * t ** 1.2
        pl = Plane(origin=p, x_dir=xd, z_dir=d)
        secs.append((pl * _slat(round(chord / 2.0, 3),
                                round(thick / 2.0, 3), 2.9)).faces()[0])
    kids.append(style(loft(secs), f"mirror_stalk:{name}", P.CARBON))

    # a machined pad terminates the stalk INTO the door instead of letting it
    # merge with the paint at an undefined edge
    pad_pl = Plane(origin=root_p + root_n * 0.5, x_dir=Vector(0, 0, 1).cross(
        root_n).normalized() * -1.0, z_dir=root_n)
    pad = pad_pl * extrude(_slat(52.0, 19.0, 3.0), amount=-4.5)
    kids.append(style(pad, f"mirror_base:{name}", P.CARBON))

    return kids


# ---------------------------------------------------------------------------
# LOUVRED OUTLETS -- gills drawn parallel to the wheel-arch cut
# ---------------------------------------------------------------------------


def _arch_aft(axle_x, hub_z, radius, z):
    """X of the arch opening's TRAILING edge at height ``z``."""
    return axle_x - math.sqrt(max(radius * radius - (z - hub_z) ** 2, 1.0))


class _GillSpec:
    def __init__(self, tag, z0, z1, gap, width, blades, axle_x, hub_z, radius):
        self.tag = tag
        self.z0, self.z1 = z0, z1
        self.gap = gap
        self.width = width
        self.blades = blades
        self.axle_x, self.hub_z, self.radius = axle_x, hub_z, radius

    def near(self, z):
        return _arch_aft(self.axle_x, self.hub_z, self.radius, z) - self.gap

    def taper(self, z):
        s = (z - self.z0) / (self.z1 - self.z0)
        s = min(max(s, 0.0), 1.0)
        return 0.46 + 0.54 * (4.0 * s * (1.0 - s)) ** 0.36

    def far(self, z):
        return self.near(z) - self.width * self.taper(z)


FRONT_GILL = _GillSpec("front_gill", 552.0, 706.0, 34.0, 158.0, 9,
                       S.FRONT_AXLE_X, S.FRONT_HUB_Z, S.FRONT_ARCH_R)
REAR_GILL = _GillSpec("rear_gill", 574.0, 762.0, 36.0, 176.0, 10,
                      S.REAR_AXLE_X, S.REAR_HUB_Z, S.REAR_ARCH_R)

_GILL_RAIL = 9.0


def _strip_face(z, x_far, x_near, off_a, off_b, side, n=6):
    """Face on the plane Z=z: flank strip between two normal offsets."""
    outer, inner = [], []
    for i in range(n + 1):
        x = x_far + (x_near - x_far) * i / n
        outer.append(_off_xy(x, z, off_a, side))
        inner.append(_off_xy(x, z, off_b, side))
    wire = (
        Spline(*outer)
        + Line(outer[-1], inner[-1])
        + Spline(*list(reversed(inner)))
        + Line(inner[0], outer[0])
    )
    return Plane.XY.offset(z) * make_face(wire)


def _gill_slab(spec, z0, z1, inset, off_a, off_b, side, nz=11):
    faces = []
    for i in range(nz + 1):
        z = z0 + (z1 - z0) * i / nz
        faces.append(_strip_face(z, spec.far(z) + inset, spec.near(z) - inset,
                                 off_a, off_b, side))
    return loft(faces)


_BLADE_CHORD = 10.6
_BLADE_THICK = 2.9
_BLADE_ANGLE = math.radians(42.0)


def _gill_blade(spec, z, side, n=5):
    """One louvre: a thin machined lamina, outer edge dropped."""
    ca, sa = math.cos(_BLADE_ANGLE), math.sin(_BLADE_ANGLE)
    hl, ht = _BLADE_CHORD / 2.0, _BLADE_THICK / 2.0
    # (normal offset, dz) corners of the tilted rectangle
    corners = [
        (+hl * ca + ht * sa, -hl * sa + ht * ca),
        (+hl * ca - ht * sa, -hl * sa - ht * ca),
        (-hl * ca - ht * sa, +hl * sa - ht * ca),
        (-hl * ca + ht * sa, +hl * sa + ht * ca),
    ]
    x0 = spec.far(z) + _GILL_RAIL + 1.2
    x1 = spec.near(z) - _GILL_RAIL - 1.2
    faces = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        pts = [_off_yz(x, z + dz, 0.6 + dn, side) for dn, dz in corners]
        faces.append(_quad_face(pts, x))
    return loft(faces)


def _gill(spec, side):
    name = "left" if side > 0 else "right"
    kids = []

    outer = _gill_slab(spec, spec.z0, spec.z1, 0.0, 5.4, -2.5, side)
    inner = _gill_slab(spec, spec.z0 + _GILL_RAIL, spec.z1 - _GILL_RAIL,
                       _GILL_RAIL, 7.0, -9.0, side)
    kids.append(style(outer - inner, f"{spec.tag}_frame:{name}",
                      P.ALUMINIUM_DARK))

    back = _gill_slab(spec, spec.z0 + _GILL_RAIL + 0.4, spec.z1 - _GILL_RAIL - 0.4,
                      _GILL_RAIL + 0.4, 0.2, -7.0, side, nz=7)
    kids.append(style(back, f"{spec.tag}_backing:{name}", P.CARBON))

    z_lo = spec.z0 + _GILL_RAIL + 8.0
    z_hi = spec.z1 - _GILL_RAIL - 8.0
    for i in range(spec.blades):
        z = z_lo + (z_hi - z_lo) * i / (spec.blades - 1)
        kids.append(style(_gill_blade(spec, z, side),
                          f"{spec.tag}_blade:{name}_{i}", P.ALUMINIUM))
    return kids


# ---------------------------------------------------------------------------
# BONNET EXTRACTORS -- blades filling the apertures `body` cuts in the hood
# ---------------------------------------------------------------------------

EXT_X = 1560.0
EXT_Y = 330.0
EXT_HX = 210.0
EXT_HY = 95.0
EXT_R = 54.0

EXT_BLADES = 8
EXT_SPAN = 372.0
EXT_CHORD = 46.0
EXT_THICK = 4.0
EXT_TILT = math.radians(34.0)
EXT_DROP = 17.0


def _ext_half_y(dx):
    """Half-width of the rounded-rect aperture at offset ``dx`` from centre."""
    a = abs(dx)
    if a <= EXT_HX - EXT_R:
        return EXT_HY
    d = a - (EXT_HX - EXT_R)
    return (EXT_HY - EXT_R) + math.sqrt(max(EXT_R * EXT_R - d * d, 0.0))


def _ext_half_x(dy):
    a = abs(dy)
    if a <= EXT_HY - EXT_R:
        return EXT_HX
    d = a - (EXT_HY - EXT_R)
    return (EXT_HX - EXT_R) + math.sqrt(max(EXT_R * EXT_R - d * d, 0.0))


def _ext_blade(dx, side, n=8):
    """One hood louvre: a slat that follows the crown of the hood across Y."""
    ca, sa = math.cos(EXT_TILT), math.sin(EXT_TILT)
    hl, ht = EXT_CHORD / 2.0, EXT_THICK / 2.0
    corners = [
        (+hl * ca - ht * sa, +hl * sa + ht * ca),
        (+hl * ca + ht * sa, +hl * sa - ht * ca),
        (-hl * ca + ht * sa, -hl * sa - ht * ca),
        (-hl * ca - ht * sa, -hl * sa + ht * ca),
    ]
    x = EXT_X + dx
    hy = _ext_half_y(dx) - 7.0
    faces = []
    for i in range(n + 1):
        y = side * (EXT_Y - hy + 2.0 * hy * i / n)
        zc = _top_z(x, y) - EXT_DROP
        pts = [(x + du, zc + dv) for du, dv in corners]
        face = Plane.XZ.offset(-y) * make_face(Polyline(*pts, pts[0]))
        faces.append(face)
    return loft(faces)


def _ext_plenum(side, n=9):
    """Dark floor under the aperture so the extractor reads deep, not hollow."""
    faces = []
    for i in range(n + 1):
        dy = -(EXT_HY - 10.0) + 2.0 * (EXT_HY - 10.0) * i / n
        y = side * (EXT_Y + dy)
        hx = _ext_half_x(dy) - 10.0
        zc = _top_z(EXT_X, y) - 74.0
        pts = [
            (EXT_X - hx, zc + 8.0), (EXT_X + hx, zc + 8.0),
            (EXT_X + hx, zc - 8.0), (EXT_X - hx, zc - 8.0),
        ]
        faces.append(Plane.XZ.offset(-y) * make_face(Polyline(*pts, pts[0])))
    return loft(faces)


def _extractor(side):
    name = "left" if side > 0 else "right"
    kids = [style(_ext_plenum(side), f"extractor_plenum:{name}", P.CARBON)]
    for i in range(EXT_BLADES):
        dx = -EXT_SPAN / 2.0 + EXT_SPAN * i / (EXT_BLADES - 1)
        kids.append(style(_ext_blade(dx, side),
                          f"extractor_blade:{name}_{i}", P.ALUMINIUM))
    return kids


# ---------------------------------------------------------------------------
# BADGES -- one abstract mark, used twice
# ---------------------------------------------------------------------------


def _chevron(a, b, g):
    """A tapered delta mark: sharp apex at +x, arms swept back."""
    pts = [
        (a, 0.0),
        (-a, b),
        (-a, b - g),
        (a - 1.85 * g, 0.0),
        (-a, -(b - g)),
        (-a, -b),
    ]
    return make_face(Polyline(*pts, pts[0]))


def _nose_badge():
    """Delta mark + underscore, milled straight into the prow.

    No dark plinth: on a nose this dark a filled pad reads as a smudge behind
    the mark.  The mark's own base is sunk 4 mm so the bronze meets the paint
    everywhere across the crown of the nose instead of lifting at its corners.
    """
    p, n = _top_surf(2228.0, 0.0)
    xd = Vector(1, 0, 0)
    xd = (xd - n * xd.dot(n)).normalized()
    pl = Plane(origin=p - n * 4.0, x_dir=xd, z_dir=n)

    mark = pl * extrude(_chevron(33.0, 23.0, 9.0), amount=6.8)
    bar = pl * Pos(-30.0, 0.0, 0.0) * extrude(
        RectangleRounded(4.2, 104.0, 2.0), amount=6.2)
    return [
        style(mark, "badge_mark:nose", P.BRONZE),
        style(bar, "badge_underscore:nose", P.BRONZE),
    ]


def _tail_badge():
    """The same mark on the tail, standing on a machined body-coloured pad.

    The tail is a true blunt cap at ``TAIL_X``, so the badge sits on a vertical
    face: local +x is UP, local +y is +Y.  The pad is body colour, not black --
    it reads as a raised milled panel rather than a stuck-on plate -- and it is
    deep enough to give the emblem a body of its own.
    """
    pl = Plane(origin=(S.TAIL_X + 2.0, 0.0, 790.0),
               x_dir=(0, 0, 1), z_dir=(-1, 0, 0))
    pad = pl * extrude(RectangleRounded(74.0, 206.0, 30.0), amount=4.0)
    mark = pl * Pos(16.0, 0.0, 3.6) * extrude(
        _chevron(27.0, 19.0, 9.0), amount=2.6)
    bar = pl * Pos(-19.0, 0.0, 3.6) * extrude(
        RectangleRounded(4.2, 150.0, 2.0), amount=2.2)
    return [
        style(pad, "badge_pad:tail", P.BODY),
        style(mark, "badge_mark:tail", P.BRONZE),
        style(bar, "badge_underscore:tail", P.BRONZE),
    ]


# ---------------------------------------------------------------------------
# FUEL FILLER -- a machined flush cap on the left rear haunch
# ---------------------------------------------------------------------------

FILLER_X = -1050.0
FILLER_Z = 780.0


def _fuel_filler():
    """An aviation-style flush filler: flange, sunk dish, flip latch, pip.

    A plain disc reads as a coin stuck on the haunch.  The three steps -- a
    proud satin flange, a dish set 1.2 mm below it, and a latch bar standing
    proud of the dish -- are what make it read as machined at any distance.
    """
    p, n = _surf(FILLER_X, FILLER_Z, 1)
    xd = Vector(1, 0, 0)
    xd = (xd - n * xd.dot(n)).normalized()
    pl = Plane(origin=p, x_dir=xd, z_dir=n)

    def disc(r, z0, h):
        return pl * Pos(0, 0, z0) * Cylinder(
            r, h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    flange = disc(55.0, -6.0, 7.7) - disc(45.5, -7.0, 10.0)
    dish = disc(45.5, -6.0, 6.5)
    latch = pl * Pos(0, 17.0, 0.4) * extrude(
        RectangleRounded(64.0, 12.5, 5.6), amount=3.0)
    pip = disc(9.5, 0.4, 2.0)
    return [
        style(flange, "fuel_filler_flange:left", P.BRONZE),
        style(dish, "fuel_filler_dish:left", P.BRONZE_DARK),
        style(latch, "fuel_filler_latch:left", P.BRONZE),
        style(pip, "fuel_filler_pip:left", P.CARBON),
    ]


# ---------------------------------------------------------------------------
# QUARTER-TURN FASTENERS -- bronze, and used exactly six times
# ---------------------------------------------------------------------------

FASTENERS = [
    (1748.0, 470.0), (1748.0, -470.0),
    (-1058.0, 452.0), (-1058.0, -452.0),
    (-1758.0, 452.0), (-1758.0, -452.0),
]


def _fastener_proto():
    flange = Pos(0, 0, -1.4) * Cylinder(
        11.2, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    head = Pos(0, 0, 1.3) * Cylinder(
        8.2, 1.5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    slot = Pos(0, 0, 2.4) * Box(13.6, 2.6, 1.2)
    return group("quarter_turn", [
        style(flange, "fastener_flange", P.BRONZE),
        style(head, "fastener_head", P.BRONZE_DARK),
        style(slot, "fastener_slot", P.CARBON),
    ])


def _fasteners():
    proto = _fastener_proto()
    inst = []
    for i, (x, y) in enumerate(FASTENERS):
        p, n = _top_surf(x, y)
        xd = Vector(1, 0, 0)
        xd = (xd - n * xd.dot(n)).normalized()
        pl = Plane(origin=p, x_dir=xd, z_dir=n)
        nm = "left" if y > 0 else "right"
        inst.append((proto, pl.location, f"quarter_turn:{nm}_{i // 2}"))
    return compound_from_instances("quarter_turns", inst)


# ---------------------------------------------------------------------------


def build():
    kids = []
    for side in (1, -1):
        kids.extend(_mirror(side))
        kids.extend(_gill(FRONT_GILL, side))
        kids.extend(_gill(REAR_GILL, side))
        kids.extend(_extractor(side))
    kids.extend(_nose_badge())
    kids.extend(_tail_badge())
    kids.extend(_fuel_filler())
    kids.append(_fasteners())
    return group("details", kids)
