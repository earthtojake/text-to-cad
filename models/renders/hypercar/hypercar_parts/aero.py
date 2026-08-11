"""Aero: front splitter, rear diffuser, swan-neck rear wing.

All exposed carbon.  These three elements are what make the car read as a
hypercar rather than a fast GT, so each is built as a real aerodynamic device
rather than a decorative applique:

``splitter``  a blade that wraps the nose.  Its inboard edge is not modelled --
              the blank is *subtracted by the master body*, so the blade meets
              the fascia exactly on the fascia's own surface and the split line
              is a true intersection curve rather than a guessed offset.  The
              turning vanes and dive planes are trimmed the same way, which is
              what makes them look grown out of the nose instead of glued on.

``diffuser``  a moulding under the tail.  ``body.py`` deliberately leaves the
              underbody aft of the rocker empty (``underfloor_prism`` claims it
              and no panel owns it), so the diffuser IS the car's lower tail
              surface here: a ramped ceiling climbing 200 -> 406, seven fins
              (five strakes plus the two side fences) hanging to one common
              lower line, and a floor tray feeding the throat.

``rear wing`` a single element with a real inverted aerofoil section (cambered,
              cosine-sampled, blunt trailing edge plus a Gurney lip), carried on
              swan-neck uprights that arc up in front of the leading edge and
              hook down onto the *upper* surface, leaving the working underside
              of the wing completely clean.
"""

from __future__ import annotations

import math

from build123d import (
    Line,
    Plane,
    Polyline,
    Pos,
    Rot,
    Spline,
    extrude,
    loft,
    make_face,
    mirror,
)

from hypercar_parts import palette as P
from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

_CACHE = {}


def _body():
    b = _CACHE.get("body")
    if b is None:
        b = _CACHE["body"] = S.body_master()
    return b


def _nose_body():
    """Master body clipped to the nose -- a small cutter is a fast cutter."""
    b = _CACHE.get("nose")
    if b is None:
        b = _CACHE["nose"] = _body() & S.slab(
            1600.0, 2420.0, -1300.0, 1300.0, -120.0, 780.0
        )
    return b


def _tail_body():
    b = _CACHE.get("tail")
    if b is None:
        b = _CACHE["tail"] = _body() & S.slab(
            -2420.0, -1400.0, -1300.0, 1300.0, -120.0, 1120.0
        )
    return b


def _cat(ts, vs, t):
    """Catmull-Rom on a uniform parameter -- smooth, and does not overshoot."""
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    i = min(int(t), len(ts) - 2)
    f = t - i
    p0 = vs[i - 1] if i > 0 else vs[i]
    p1, p2 = vs[i], vs[i + 1]
    p3 = vs[i + 2] if i + 2 < len(vs) else vs[i + 1]
    m1, m2 = 0.5 * (p2 - p0), 0.5 * (p3 - p1)
    f2, f3 = f * f, f * f * f
    return (
        (2 * f3 - 3 * f2 + 1) * p1
        + (f3 - 2 * f2 + f) * m1
        + (-2 * f3 + 3 * f2) * p2
        + (f3 - f2) * m2
    )


def _resample(ctrl, n):
    ts = list(range(len(ctrl)))
    us = [p[0] for p in ctrl]
    vs = [p[1] for p in ctrl]
    out = []
    for i in range(n):
        t = i * (len(ctrl) - 1) / (n - 1)
        out.append((_cat(ts, us, t), _cat(ts, vs, t)))
    return out


def _closed_face(pts, plane):
    """A face from a smooth closed outline: one spline plus a closing line."""
    wire = Spline(*pts) + Line(pts[-1], pts[0])
    return plane * make_face(wire)


def _plan_offset(pts, d):
    """Offset a CCW outline outward by ``d`` mm (negative shrinks it)."""
    n = len(pts)
    out = []
    for i, (x, y) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dy) or 1.0
        out.append((x + dy / m * d, y - dx / m * d))
    return out


def _xz_band(xs, flo, fhi, half_y=1500.0):
    """Solid between two smooth Z curves of X, unbounded in Y."""
    lo = [(x, flo(x)) for x in xs]
    hi = [(x, fhi(x)) for x in reversed(xs)]
    wire = (
        Spline(*lo)
        + Line(lo[-1], hi[0])
        + Spline(*hi)
        + Line(hi[-1], lo[0])
    )
    face = Plane.XZ * make_face(wire)
    return extrude(face, amount=-half_y) + extrude(face, amount=half_y)


def _plan_face(xs, fy, z, grow=0.0):
    lo = [(x, -fy(x) - grow) for x in xs]
    hi = [(x, fy(x) + grow) for x in reversed(xs)]
    wire = (
        Spline(*lo)
        + Line(lo[-1], hi[0])
        + Spline(*hi)
        + Line(hi[-1], lo[0])
    )
    return Plane.XY.offset(z) * make_face(wire)


def _plan_prism(xs, fy, z0=-300.0, z1=900.0):
    """Vertical prism whose plan half-width is a smooth function of X."""
    return extrude(_plan_face(xs, fy, z0), amount=z1 - z0)


def _plan_loft(xs, fy, layers):
    """Prism whose half-width also varies with Z: layers = [(z, grow), ...]."""
    return loft([_plan_face(xs, fy, z, g) for z, g in layers], ruled=True)


def _span(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _naca(s, t, m=0.0, p=0.4):
    """Thickness/camber ordinates of a 4-digit section at station ``s``."""
    yt = 5.0 * t * (
        0.2969 * math.sqrt(s)
        - 0.1260 * s
        - 0.3516 * s * s
        + 0.2843 * s ** 3
        - 0.1036 * s ** 4
    )
    if m <= 0.0:
        return 0.0, yt, 0.0
    if s < p:
        yc = m / (p * p) * (2 * p * s - s * s)
        dy = 2 * m / (p * p) * (p - s)
    else:
        q = (1.0 - p) ** 2
        yc = m / q * ((1.0 - 2.0 * p) + 2 * p * s - s * s)
        dy = 2 * m / q * (p - s)
    return yc, yt, dy


# ---------------------------------------------------------------------------
# 1.  front splitter
# ---------------------------------------------------------------------------
#
# Plan outline of the blade: it clears the fascia by ~80 mm at the nose and
# settles onto SILL_Y + 35 down the sides, so the lip runs back under the
# fender as a thin carbon line instead of stopping in mid air.

_SPLIT_HALF = [
    (1688.0, 806.0), (1760.0, 792.0), (1840.0, 742.0), (1920.0, 688.0),
    (2000.0, 606.0), (2080.0, 520.0), (2150.0, 452.0), (2220.0, 360.0),
    (2270.0, 272.0), (2306.0, 216.0), (2340.0, 162.0), (2368.0, 90.0),
    (2384.0, 0.0),
]

# The blade's own top and bottom.  Both are deliberately run *into* the body:
# where the fascia is lower than SP_ZTOP the boolean trims the blade to the
# fascia, so the two meet on a real surface intersection.  SP_ZBOT is kicked up
# hard at x ~ 1960 so the under-nose tray closes with a crisp transverse edge
# rather than dying out in a tangent sliver.
SP_ZBOT = S.C1("sp_zbot", [
    (1670, 150), (1780, 146), (1880, 146), (1935, 140), (1990, 100),
    (2080, 94), (2200, 92), (2320, 92), (2392, 92),
])
SP_ZTOP = S.C1("sp_ztop", [
    (1670, 176), (1780, 180), (1880, 182), (1990, 178), (2100, 174),
    (2200, 176), (2300, 179), (2345, 170), (2392, 140),
])


SP_Y = S.C1("sp_y", list(_SPLIT_HALF))


def _splitter_outline():
    neg = [(x, -y) for (x, y) in _SPLIT_HALF]
    pos = [(x, y) for (x, y) in reversed(_SPLIT_HALF)]
    return neg + pos[1:]


def _splitter_blade():
    xs = _span(1670.0, 2392.0, 30)
    band = _xz_band(xs, SP_ZBOT, SP_ZTOP)
    out = _splitter_outline()
    # four plan slices: a small under-chamfer, a near-vertical edge band, then
    # a long chamfer off the top so the blade reads as a knife, not a plank
    prism = loft([
        _closed_face(_plan_offset(out, -22.0), Plane.XY.offset(66.0)),
        _closed_face(_plan_offset(out, 0.0), Plane.XY.offset(116.0)),
        _closed_face(_plan_offset(out, 2.0), Plane.XY.offset(158.0)),
        _closed_face(_plan_offset(out, -44.0), Plane.XY.offset(238.0)),
    ], ruled=True)
    return (band & prism) - _nose_body()


# Turning vanes ride ON the blade's plan curve rather than on a constant Y --
# the nose sheds 350 mm of half-width across their length, so a streamwise fin
# would hang off the edge at its front.  Their tops are run far into the fascia
# and trimmed by it, which is what makes the top edge a true surface
# intersection curve instead of a guessed profile.
_VANE_FWD_TOP = S.C1("vane_fwd_top", [
    (1994, 168), (2030, 340), (2078, 372), (2126, 344), (2158, 172),
])
_VANE_AFT_TOP = S.C1("vane_aft_top", [
    (1798, 168), (1832, 316), (1874, 344), (1920, 318), (1954, 170),
])


def _turning_vane(x0, x1, top, inset, thick):
    xs = _span(x0, x1, 15)
    band = _xz_band(xs, lambda x: 128.0, top)
    lo = [(x, SP_Y(x) - inset - thick) for x in xs]
    hi = [(x, SP_Y(x) - inset) for x in reversed(xs)]
    wire = Spline(*lo) + Line(lo[-1], hi[0]) + Spline(*hi) + Line(hi[-1], lo[0])
    prism = extrude(Plane.XY.offset(60.0) * make_face(wire), amount=420.0)
    return (band & prism) - _nose_body()


_DIVE_LOWER = [
    (2002.0, 400.0), (1984.0, 652.0), (1952.0, 812.0), (1898.0, 890.0),
    (1838.0, 876.0), (1814.0, 776.0), (1798.0, 590.0), (1792.0, 400.0),
]
_DIVE_UPPER = [
    (1980.0, 400.0), (1962.0, 644.0), (1934.0, 800.0), (1888.0, 878.0),
    (1836.0, 864.0), (1814.0, 766.0), (1802.0, 588.0), (1796.0, 400.0),
]
# the fence that ties the two canards together at their tips: without it the
# blades read as two loose slats instead of one machined assembly
_DIVE_FENCE = [
    (1938.0, 268.0), (1930.0, 384.0), (1892.0, 412.0), (1842.0, 402.0),
    (1826.0, 330.0), (1832.0, 266.0),
]
DIVE_Y0 = 400.0


def _dive_plane(plan, z0, cant, thick):
    wire = Spline(*plan) + Line(plan[-1], plan[0])
    blade = extrude(Plane.XY * make_face(wire), amount=thick)
    return (
        Pos(0, DIVE_Y0, z0)
        * Rot(cant, 0, 0)
        * Pos(0, -DIVE_Y0, -thick / 2.0)
        * blade
    ) - _nose_body()


def _dive_fence(y, thick):
    wire = Spline(*_DIVE_FENCE) + Line(_DIVE_FENCE[-1], _DIVE_FENCE[0])
    face = Plane.XZ.offset(-y) * make_face(wire)
    return extrude(face, amount=thick / 2.0) + extrude(face, amount=-thick / 2.0)


def _splitter():
    kids = [style(_splitter_blade(), "front_splitter", P.CARBON)]

    for x0, x1, top, tag in (
        (1994.0, 2158.0, _VANE_FWD_TOP, "fwd"),
        (1798.0, 1954.0, _VANE_AFT_TOP, "aft"),
    ):
        kids.append(
            style(_turning_vane(x0, x1, top, 9.0, 15.0),
                  f"turning_vane:left_{tag}", P.CARBON_GLOSS)
        )
        kids.append(
            style(mirror(_turning_vane(x0, x1, top, 9.0, 15.0), Plane.XZ),
                  f"turning_vane:right_{tag}", P.CARBON_GLOSS)
        )

    for plan, tag, z0, cant, t in (
        (_DIVE_LOWER, "lower", 248.0, 10.0, 17.0),
        (_DIVE_UPPER, "upper", 334.0, 7.0, 15.0),
    ):
        kids.append(
            style(_dive_plane(plan, z0, cant, t),
                  f"dive_plane:left_{tag}", P.CARBON_GLOSS)
        )
        kids.append(
            style(mirror(_dive_plane(plan, z0, cant, t), Plane.XZ),
                  f"dive_plane:right_{tag}", P.CARBON_GLOSS)
        )

    kids.append(style(_dive_fence(866.0, 14.0), "canard_fence:left", P.CARBON))
    kids.append(
        style(mirror(_dive_fence(866.0, 14.0), Plane.XZ),
              "canard_fence:right", P.CARBON)
    )
    return kids


# ---------------------------------------------------------------------------
# 2.  rear diffuser
# ---------------------------------------------------------------------------

DF_X0, DF_X1 = -2400.0, -1880.0

DF_CEIL = S.C1("df_ceil", [
    (-1880, 202), (-1980, 238), (-2080, 282), (-2180, 326),
    (-2280, 366), (-2400, 406),
])
DF_BOT = S.C1("df_bot", [(-1880, 176), (-2100, 186), (-2400, 204)])
# The plan flares rearward: the tunnels expand, and the shoulders grow out to
# meet the rear fascia so the moulding reads as the car's lower tail surface
# rather than a box screwed under it.
DF_OUT = S.C1("df_out", [
    (-1880, 734), (-2000, 744), (-2100, 758), (-2200, 772),
    (-2300, 784), (-2400, 792),
])

STRAKE_T = 12.0          # half thickness
# (spanwise position, how far this fin's lower edge sits above the fence line)
# -- the lift grows inboard so the seven fins describe a shallow arch across the
# exit instead of a flat comb of identical teeth.
STRAKE_Y = ((0.0, 24.0), (238.0, 13.0), (-238.0, 13.0), (478.0, 0.0), (-478.0, 0.0))
STRAKE_RAKE = 84.0       # how far the strakes' lower edge climbs to the throat


def _df_roof(x):
    return DF_CEIL(x) + 36.0


def _strake_bot(x):
    t = (x - DF_X0) / (DF_X1 - DF_X0)
    return DF_BOT(x) + STRAKE_RAKE * max(0.0, min(t, 1.0)) ** 1.25


def _diffuser():
    xs = _span(DF_X0, DF_X1, 26)
    xs_cut = _span(DF_X0 - 14.0, DF_X1 + 26.0, 26)

    # the shoulders tuck in above the fence line, so the exit is a trapezoid
    # tapering into the rear fascia rather than a square-cornered box
    env = _xz_band(xs, DF_BOT, _df_roof) & _plan_loft(
        xs, DF_OUT, ((-200.0, 0.0), (330.0, 0.0), (470.0, -62.0))
    )
    cavity = (
        _xz_band(xs_cut, lambda x: -200.0, DF_CEIL)
        & _plan_prism(xs_cut, lambda x: DF_OUT(x) - 58.0, -260.0, 700.0)
    )

    kids = [style(env - cavity, "rear_diffuser", P.CARBON)]

    # the strakes stop short of the fences' lower line and rake up hard toward
    # the throat, so the exit reads as a deep arch framed by the two fences
    inner = env & cavity
    voids = {}
    for i, (sy, lift) in enumerate(STRAKE_Y):
        void = voids.get(lift)
        if void is None:
            void = voids[lift] = inner & _xz_band(
                xs_cut, lambda x, l=lift: _strake_bot(x) + l, lambda x: 900.0
            )
        fin = void & S.slab(
            DF_X0 - 20.0, DF_X1 + 40.0, sy - STRAKE_T, sy + STRAKE_T, -300.0, 800.0
        )
        if fin.solids():
            tag = "c" if sy == 0.0 else (
                f"left_{i // 2 + 1}" if sy > 0 else f"right_{i // 2}"
            )
            kids.append(style(fin, f"diffuser_strake:{tag}", P.CARBON_GLOSS))
    return kids


TRAY_BOT = S.C1("tray_bot", [
    (-1900, 176), (-1800, 178), (-1710, 184), (-1650, 208), (-1600, 232),
])
TRAY_Y = S.C1("tray_y", [
    (-1900, 738), (-1800, 726), (-1710, 690), (-1650, 636), (-1600, 600),
])


def _rear_tray():
    """Flat floor feeding the diffuser throat.

    Its ceiling is run above the body and trimmed by it, so the tray's upper
    face IS the car's underside and the tray simply fades out forward, where
    the floor drops below the tray's own plane.
    """
    xs = _span(-1900.0, -1600.0, 16)
    band = _xz_band(xs, TRAY_BOT, lambda x: S.SILL_Z(x) + 20.0)
    tray = (band & _plan_prism(xs, TRAY_Y, -200.0, 500.0)) - _tail_body()
    return tray if tray.solids() else None


# ---------------------------------------------------------------------------
# 3.  rear wing
# ---------------------------------------------------------------------------

WING_SPAN = 812.0
WING_T = 0.150
WING_M = 0.063
WING_P = 0.42
_S_END = 0.955


def _wing_geom(y):
    """Swept leading edge, near-straight trailing edge, mild tip washout."""
    f = min(abs(y) / WING_SPAN, 1.0)
    chord = 408.0 - 108.0 * f ** 1.5
    xle = -1996.0 - 104.0 * f ** 1.7
    zle = 1028.0 + 26.0 * f ** 1.4
    alpha = math.radians(12.5 - 1.8 * f)
    return chord, xle, zle, alpha


def _wing_profile(y, n=38):
    """Inverted cambered section in global (x, z) at spanwise station ``y``."""
    chord, xle, zle, a = _wing_geom(y)
    ca, sa = math.cos(a), math.sin(a)
    up, lo = [], []
    for i in range(n + 1):
        s = _S_END * 0.5 * (1.0 - math.cos(math.pi * i / n))
        yc, yt, dy = _naca(s, WING_T, WING_M, WING_P)
        th = math.atan(dy)
        # inverted: the suction side is underneath, so the standard lower
        # surface becomes this wing's upper surface
        cu, hu = (s + yt * math.sin(th)) * chord, (yt * math.cos(th) - yc) * chord
        cl, hl = (s - yt * math.sin(th)) * chord, -(yc + yt * math.cos(th)) * chord
        up.append((xle - cu * ca + hu * sa, zle + cu * sa + hu * ca))
        lo.append((xle - cl * ca + hl * sa, zle + cl * sa + hl * ca))
    return up, lo


def _wing_face(y):
    up, lo = _wing_profile(y)
    pts = list(reversed(up)) + lo[1:]
    wire = Spline(*pts) + Line(pts[-1], pts[0])
    return Plane.XZ.offset(-y) * make_face(wire)


_WING_STATIONS = [
    -812.0, -776.0, -718.0, -630.0, -500.0, -340.0, -170.0, 0.0,
    170.0, 340.0, 500.0, 630.0, 718.0, 776.0, 812.0,
]


def _wing_element():
    return loft([_wing_face(y) for y in _WING_STATIONS])


def _gurney_face(y, height=22.0, width=9.0, sink=6.0):
    up, _ = _wing_profile(y)
    _, _, _, a = _wing_geom(y)
    ca, sa = math.cos(a), math.sin(a)
    dx, dz = -ca, sa            # leading edge -> trailing edge
    nx, nz = sa, ca             # section "up"
    te = up[-1]
    fw = (te[0] - dx * width, te[1] - dz * width)
    pts = [
        (fw[0] - nx * sink, fw[1] - nz * sink),
        (te[0] - nx * sink, te[1] - nz * sink),
        (te[0] + nx * height, te[1] + nz * height),
        (fw[0] + nx * height, fw[1] + nz * height),
    ]
    return Plane.XZ.offset(-y) * make_face(Polyline(*pts, pts[0]))


def _gurney():
    return loft([_gurney_face(y) for y in _WING_STATIONS], ruled=True)


# Built from three edges, not one closed spline: a single spline rounds every
# corner into a leaf.  Two splines meeting at a shared nose point give a knife
# leading edge, and the straight trailing edge between them gives two sharp
# rear points -- the span terminates on deliberate corners.
_EP_TOP = [
    (-2086.0, 1042.0), (-2104.0, 1082.0), (-2150.0, 1104.0),
    (-2240.0, 1122.0), (-2330.0, 1130.0), (-2400.0, 1128.0),
]
_EP_BOT = [
    (-2394.0, 1092.0), (-2330.0, 1068.0), (-2240.0, 1036.0),
    (-2160.0, 1016.0), (-2110.0, 1018.0), (-2086.0, 1042.0),
]


def _endplate(wing):
    wire = Spline(*_EP_TOP) + Line(_EP_TOP[-1], _EP_BOT[0]) + Spline(*_EP_BOT)
    face = Plane.XZ.offset(-816.0) * make_face(wire)
    plate = extrude(face, amount=6.0) + extrude(face, amount=-6.0)
    return plate - wing


# The swan neck is a blade, not a tube: a curved strap in the XZ plane, crowned
# across its thickness.  It rises AHEAD of the leading edge, arcs over the top
# and plunges down onto the upper surface, so the wing's working underside is
# left completely uninterrupted -- which is the whole point of a swan neck.
_PYLON_PATH = [
    (-1890.0, 792.0), (-1894.0, 872.0), (-1900.0, 944.0), (-1914.0, 1006.0),
    (-1940.0, 1052.0), (-1978.0, 1082.0), (-2026.0, 1094.0),
    (-2072.0, 1086.0), (-2108.0, 1068.0), (-2134.0, 1044.0),
]
_PYLON_W = [(0.00, 108.0), (0.10, 66.0), (0.30, 48.0), (0.62, 40.0),
            (0.86, 32.0), (1.00, 26.0)]
PYLON_Y = 352.0
_PYLON_LAYERS = ((0.0, 0.0), (11.0, 3.5), (18.0, 12.0))


def _pylon_half_width(u):
    for (u0, w0), (u1, w1) in zip(_PYLON_W, _PYLON_W[1:]):
        if u <= u1:
            t = (u - u0) / (u1 - u0)
            return w0 + t * (w1 - w0)
    return _PYLON_W[-1][1]


def _pylon_face(y, shrink):
    path = _resample(_PYLON_PATH, 26)
    n = len(path)
    outer, inner = [], []
    for i, p in enumerate(path):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        dx, dz = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dz) or 1.0
        nx, nz = -dz / m, dx / m
        w = max(_pylon_half_width(i / (n - 1)) - shrink, 5.0)
        outer.append((p[0] + nx * w, p[1] + nz * w))
        inner.append((p[0] - nx * w, p[1] - nz * w))
    inner.reverse()
    wire = (
        Spline(*outer)
        + Line(outer[-1], inner[0])
        + Spline(*inner)
        + Line(inner[-1], outer[0])
    )
    return Plane.XZ.offset(-y) * make_face(wire)


def _pylon(side, wing):
    y0 = side * PYLON_Y
    faces = [
        _pylon_face(y0 - dy, sh) for dy, sh in reversed(_PYLON_LAYERS)
    ] + [
        _pylon_face(y0 + dy, sh) for dy, sh in _PYLON_LAYERS[1:]
    ]
    strut = loft(faces, ruled=True)
    return (strut - _tail_body()) - wing


def _rear_wing():
    wing = _wing_element()
    kids = [style(wing, "rear_wing_element", P.CARBON_GLOSS)]
    kids.append(style(_gurney(), "wing_gurney", P.CARBON))
    kids.append(style(_endplate(wing), "wing_endplate:left", P.CARBON))
    kids.append(
        style(mirror(_endplate(wing), Plane.XZ), "wing_endplate:right", P.CARBON)
    )
    for side, nm in ((1, "left"), (-1, "right")):
        kids.append(style(_pylon(side, wing), f"swan_neck:{nm}", P.CARBON_GLOSS))
    return kids


# ---------------------------------------------------------------------------


def build():
    kids = []
    kids.extend(_splitter())
    kids.extend(_diffuser())
    tray = _rear_tray()
    if tray is not None:
        kids.append(style(tray, "rear_floor_tray", P.CARBON))
    kids.extend(_rear_wing())
    return group("aero", kids)
