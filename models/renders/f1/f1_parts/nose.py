"""Nose crash structure: chisel blade, tip cap + pitot, pylon junction, pods.

THE SECTION LAW
---------------
The nose is one lofted carbon volume whose section is a CHISEL, not a cone.
Every station is written outboard as a front-view sketch in (y, z) and read
from the centreline keel, out under the belly, up the flank and over the deck
back to the centreline spine.  Four named features:

    KEEL     centreline bottom `zb`, a sharp V `kr` deep      the blade edge
    SCOOP    concave belly, z'' < 0 from the keel to ~0.6 hw  the undercut
    CREASE   `spec.shoulder_at(x)` -> (hw, zc)                THE feature line
    DECK     convex crown leaning inboard off the crease

The belly arrives at the crease travelling almost straight UP and the deck
leaves it at ~50 deg, so the two surfaces meet at a real angle and the primary
feature line reads as a corner rather than a highlight.  Between the keel and
that flank the surface is genuinely CONCAVE — the slope falls away from the
keel and only turns back up outboard of the wing pylons — which is what makes
the nose read as sculpted rather than extruded.

Toward the tip the plan view collapses far faster than the elevation.  The
section stops being wider than tall at x = 1362 and inverts hard from there:
44 x 70 at x = 1399, 19 x 42 at x = 1414, and the nose ends at x = 1420 on an
8 x 26 raked chisel edge.  That inversion — markedly narrower in y than tall
in z — is the whole point of the forward third.

INTERFACES — do not move these
------------------------------
  * x = 703 panel break: half width 194.6, z 157.4 .. 300.0, crease z 266;
  * x = 1250 pylon pad: flat over |y| = 38 .. 90, pad underside z = 200;
  * nothing forward of `spec.NOSE_TIP_X` but the pitot, nothing outboard of
    |y| = 260, nothing below z = 150;
  * the keel clears the front wing: the topmost flap's centreline trailing
    edge peaks at z = 182.5 at x = 1072, and `zb` holds ~199 across it.

Everything forward of the bulkhead is a bolt-on: the rear of the module is a
proud flange, a `spec.PANEL_GAP` parting line at x = 703, and a rhythmic ring
of Dzus fittings. The tip cap is a second parting line with a machined collar
recessed in the gap.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Pos

from . import lib, spec

# ==========================================================================
# STATIONS — everything below is derived from spec datums
# ==========================================================================

TIP_X = spec.NOSE_TIP_X  # 1420 — forwardmost bodywork
BULK_X = spec.BULKHEAD_FRONT_X  # 700 — front bulkhead face
BREAK_X = BULK_X + spec.PANEL_GAP  # 703 — rearmost nose bodywork

TIP_Z_CREASE = 246.0  # where the shoulder crease sits on the chisel face
SHOULDER_LOCK_X = 1180.0  # spec.SHOULDER_LINE's forward-most point

CAP_BREAK_X = 1352.0  # tip-cap parting line
CONE_NOSE_X = CAP_BREAK_X - spec.PANEL_GAP  # 1349

# front-wing pylon junction
PYLON_X = 1250.0
PYLON_Y = 64.0
PYLON_Z = 200.0  # pylon tops
PYLON_DEPTH = 16.0  # local trough amplitude in the belly
PYLON_SIGMA_F = 96.0  # trough fade forward of PYLON_X
PYLON_SIGMA_A = 175.0  # ... and aft, so it reads as a channel not a dimple
PYLON_WIDTH = 44.0  # trough width in y

# camera pods
CAM_NOSE_X = 1006.0
CAM_TAIL_X = 878.0
CAM_Y = 210.0
CAM_Z = 400.0
CAM_ROOT = (950.0, 118.0, 272.0)

N_FASTENERS = 20
N_LOWER = 23  # section samples, centreline keel -> crease
N_UPPER = 15  # section samples, crease -> centreline spine


# ==========================================================================
# SECTION LAWS
#
#   x      half width   keel bottom   spine top   keel depth
# The plan (hw) collapses to a 9 mm half width at the tip while the elevation
# still carries 55 mm of section — that is the chisel. `zb` rises forward to
# clear the front wing's topmost flap (182.5 at x = 1072) and lands exactly on
# the 157.4 handed to the tub at the panel break.
# ==========================================================================

#: PLAN. Written analytically, not keyed: a keyframed half width put a visible
#: corner in the plan outline wherever the taper rate changed, and the taper
#: rate has to change a lot here — the pad forces 204 mm of width at x = 1250
#: while the tip is a 14 mm blade. This rational S is C-infinity, so the flare
#: off the chisel and the long parallel run into the bulkhead are one curve.
W_TIP = 4.0
W_BULK = 194.6
W_A = 1.0  # rise off the tip
W_B = 1.0  # approach to the bulkhead
W_K = 0.293665  # pins hw(1250) = 102: the pad reaches |y| = 90


def _half_width(x: float) -> float:
    s = (TIP_X - x) / (TIP_X - BREAK_X)
    if s <= 0.0:
        return W_TIP
    if s >= 1.0:
        return W_BULK
    h = s**W_A / (s**W_A + W_K * (1.0 - s) ** W_B)
    return W_TIP + (W_BULK - W_TIP) * h


#: ELEVATION. `zb` runs almost LEVEL from the tip back to x ~ 1090 and only
#: then dives to the panel break, so the forward third is a constant-depth
#: blade rather than a cone; it holds ~200 across x = 1072 where the front
#: wing's topmost flap peaks at z = 182.5.
_SECTIONS = (
    #   x       zb      zt      kr
    (1420.0, 232.0, 258.0, 3.0),  # the chisel edge: 8 wide, 26 tall, raked
    (1414.0, 222.0, 264.5, 4.5),
    (1407.0, 212.5, 270.0, 6.0),
    (1399.0, 204.5, 274.5, 7.5),
    (1390.0, 199.6, 278.4, 8.8),
    (1381.0, 197.9, 281.0, 9.6),
    (1366.0, 197.9, 283.5, 10.4),
    (1344.0, 198.1, 285.2, 10.8),
    (1320.0, 198.3, 286.6, 11.2),
    (1294.0, 198.5, 287.6, 11.5),
    (1272.0, 198.8, 288.5, 11.8),
    (PYLON_X, 199.0, 289.3, 12.0),
    (1220.0, 199.4, 290.3, 12.3),
    (1180.0, 199.8, 291.5, 12.5),
    (1140.0, 200.2, 292.5, 13.0),
    (1090.0, 200.5, 293.7, 14.5),
    (1040.0, 196.0, 294.8, 17.5),
    (980.0, 189.5, 295.9, 20.5),
    (920.0, 182.0, 296.8, 23.0),
    (850.0, 173.0, 297.9, 25.5),
    (780.0, 165.0, 299.1, 28.0),
    (703.0, 157.4, 300.0, 30.0),
)

_TANGENTS: dict = {}


def _tangents(table):
    """Fritsch-Carlson slopes for every column of a keyframe table.

    Smoothstep between keyframes forces the slope to ZERO at each one, so a
    densely keyed law undulates between them and the loft carries that
    undulation into the skin as a chevron ripple. A monotone cubic keeps the
    law genuinely smooth and never overshoots a keyframe.
    """
    key = id(table)
    if key in _TANGENTS:
        return _TANGENTS[key]
    xs = [r[0] for r in table]
    cols = []
    for j in range(1, len(table[0])):
        v = [r[j] for r in table]
        d = [(v[i + 1] - v[i]) / (xs[i + 1] - xs[i]) for i in range(len(v) - 1)]
        mm = [d[0]] + [(d[i - 1] + d[i]) / 2.0 for i in range(1, len(d))] + [d[-1]]
        for i, di in enumerate(d):
            if abs(di) < 1e-12:
                mm[i] = mm[i + 1] = 0.0
                continue
            a, b = mm[i] / di, mm[i + 1] / di
            s = a * a + b * b
            if s > 9.0:
                k = 3.0 / math.sqrt(s)
                mm[i], mm[i + 1] = k * a * di, k * b * di
        cols.append(mm)
    _TANGENTS[key] = cols
    return cols


def _blend(table, x: float):
    """Monotone-cubic sample of a keyframe table (x descending) at station x."""
    if x >= table[0][0]:
        return table[0][1:]
    if x <= table[-1][0]:
        return table[-1][1:]
    cols = _tangents(table)
    for i in range(len(table) - 1):
        a, b = table[i], table[i + 1]
        if b[0] <= x <= a[0]:
            h = b[0] - a[0]
            t = (x - a[0]) / h
            t2, t3 = t * t, t * t * t
            h00 = 2 * t3 - 3 * t2 + 1
            h10 = t3 - 2 * t2 + t
            h01 = -2 * t3 + 3 * t2
            h11 = t3 - t2
            out = []
            for j in range(1, len(a)):
                m0, m1 = cols[j - 1][i], cols[j - 1][i + 1]
                out.append(h00 * a[j] + h10 * h * m0 + h01 * b[j] + h11 * h * m1)
            return out
    return table[-1][1:]


def _section(x: float):
    """(half_width, z_bottom, z_top, z_crease, keel_depth) at station x."""
    zb, zt, kr = _blend(_SECTIONS, x)
    hw = _half_width(x)
    _, zc = spec.shoulder_at(x)
    if x > SHOULDER_LOCK_X:
        u = spec.smoothstep((x - SHOULDER_LOCK_X) / (TIP_X - SHOULDER_LOCK_X))
        zc = zc + (TIP_Z_CREASE - zc) * u
    kr = min(kr, 0.42 * (zc - zb))  # the keel never eats the whole belly
    return hw, zb, zt, zc, kr


def _keel_half_w(hw: float) -> float:
    """Half width of the keel V — mostly absolute, so it stays a strake."""
    return 0.13 * hw + 6.0


#: deck squareness: hardest through the body, softening into the blade tip so
#: the chisel finishes on a rolled ridge rather than a flat-topped plank.
_DECK_EXP = ((1420.0, 2.55), (1352.0, 2.95), (1250.0, 3.35), (1090.0, 3.45),
             (900.0, 3.30), (703.0, 3.05))


def _deck_exp(x: float) -> float:
    return _blend(_DECK_EXP, x)[0]


def _pylon_dip(x: float, y: float, v: float) -> float:
    """Local scoop that seats the front-wing pylon pad in the belly.

    Faded to zero at BOTH the keel apex and the crease (`v` is y / half width),
    so it deepens the concave shoulder without softening either feature line.
    """
    s = PYLON_SIGMA_F if x >= PYLON_X else PYLON_SIGMA_A
    a = PYLON_DEPTH * math.exp(-(((x - PYLON_X) / s) ** 2))
    if a < 0.02:
        return 0.0
    a *= math.exp(-(((y - PYLON_Y) / PYLON_WIDTH) ** 2))
    return a * spec.smoothstep(v / 0.16) * spec.smoothstep((1.0 - v) / 0.26)


def _catmull(ctrl, per_seg: int = 26):
    """Centripetal Catmull-Rom through (y, z) control points — the section shape.

    The shape is sampled densely here and re-sampled with graded spacing below,
    so the interpolating spline `half_section_face` builds never has to swallow
    a sudden jump in point density. That is what keeps the lofted skin free of
    the specular ripple a clustered crease otherwise produces.
    """
    pts = [p for i, p in enumerate(ctrl) if i == 0 or math.dist(p, ctrl[i - 1]) > 1e-7]
    if len(pts) < 3:
        return list(pts)
    ext = [
        (2 * pts[0][0] - pts[1][0], 2 * pts[0][1] - pts[1][1]),
        *pts,
        (2 * pts[-1][0] - pts[-2][0], 2 * pts[-1][1] - pts[-2][1]),
    ]
    out = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        t0 = 0.0
        t1 = t0 + math.dist(p0, p1) ** 0.5
        t2 = t1 + math.dist(p1, p2) ** 0.5
        t3 = t2 + math.dist(p2, p3) ** 0.5
        for k in range(per_seg):
            t = t1 + (t2 - t1) * k / per_seg
            a1 = [(t1 - t) / (t1 - t0) * p0[j] + (t - t0) / (t1 - t0) * p1[j] for j in range(2)]
            a2 = [(t2 - t) / (t2 - t1) * p1[j] + (t - t1) / (t2 - t1) * p2[j] for j in range(2)]
            a3 = [(t3 - t) / (t3 - t2) * p2[j] + (t - t2) / (t3 - t2) * p3[j] for j in range(2)]
            b1 = [(t2 - t) / (t2 - t0) * a1[j] + (t - t0) / (t2 - t0) * a2[j] for j in range(2)]
            b2 = [(t3 - t) / (t3 - t1) * a2[j] + (t - t1) / (t3 - t1) * a3[j] for j in range(2)]
            out.append(
                tuple(
                    (t2 - t) / (t2 - t1) * b1[j] + (t - t1) / (t2 - t1) * b2[j]
                    for j in range(2)
                )
            )
    out.append(tuple(pts[-1]))
    return out


_FRAC_CACHE: dict = {}


def _grade_fracs(
    n: int,
    tighten: float = 0.11,
    ease: float = 1.7,
    tighten0: float = 1.0,
    ease0: float = 1.8,
):
    """Arc-length fractions for `n` samples, spacing tightening toward the ends.

    `tighten` clusters samples at the END of the run (the crease) and
    `tighten0` at its START (the keel apex). Both corners are tight-radius
    features, so both need the point density — a keel sampled at the same
    spacing as the flank comes out of the loft as a rounded belly.

    The fractions are the SAME at every station, so every lofted section has an
    identical point count and distribution. Mixed section resolutions are what
    make OCC re-approximate a loft and put waves in the skin.
    """
    key = (n, tighten, ease, tighten0, ease0)
    if key in _FRAC_CACHE:
        return _FRAC_CACHE[key]
    m = 720
    lr = math.log(tighten)
    lr0 = math.log(tighten0)
    cum = [0.0]
    for i in range(1, m + 1):
        u = i / m
        w = math.exp(-lr * u**ease) * math.exp(-lr0 * (1.0 - u) ** ease0)
        cum.append(cum[-1] + w)
    total = cum[-1]
    out, j = [], 0
    for i in range(n):
        target = total * i / (n - 1)
        while j < m and cum[j + 1] < target:
            j += 1
        span = cum[j + 1] - cum[j] if j < m else 1.0
        u = (j + (target - cum[j]) / max(span, 1e-12)) / m
        out.append(min(max(u, 0.0), 1.0))
    _FRAC_CACHE[key] = out
    return out


def _sample_fracs(dense, fracs):
    seg = [math.dist(dense[i], dense[i + 1]) for i in range(len(dense) - 1)]
    total = sum(seg)
    if total <= 0:
        return [tuple(dense[0])] * len(fracs)
    out = []
    i, acc = 0, 0.0
    for f in fracs:
        s = f * total
        while i < len(seg) - 1 and acc + seg[i] < s:
            acc += seg[i]
            i += 1
        u = (s - acc) / max(seg[i], 1e-9)
        u = min(max(u, 0.0), 1.0)
        a, b = dense[i], dense[i + 1]
        out.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
    return out


# --- the keel V: y as a fraction of the keel half width, z of `kr` ---------
_KEEL = ((0.00, 0.000), (0.10, 0.300), (0.26, 0.580), (0.50, 0.800),
         (0.76, 0.945), (1.00, 1.000))

# --- the belly: y from the keel shoulder to the crease, z of `hl` ----------
# The slope FALLS from 1.33 at the keel shoulder to 0.60 around u = 0.5 — that
# decreasing slope IS the concavity — and only then turns back up. It arrives
# at the crease leaning inboard, so the flank genuinely tucks UNDER the feature
# line instead of running straight down past it.
_BELLY = ((0.000, 0.000), (0.090, 0.120), (0.190, 0.222), (0.300, 0.308),
          (0.420, 0.386), (0.540, 0.458), (0.660, 0.532), (0.780, 0.618),
          (0.865, 0.700), (0.930, 0.790), (0.975, 0.890), (1.000, 1.000))

N_DECK = 16  # deck control points, clustered onto the crease


def _lower_ctrl(x: float, dip: bool = True):
    """Keel -> concave scoop -> undercut -> CREASE, as (y, z) control points."""
    hw, zb, zt, zc, kr = _section(x)
    kw = min(_keel_half_w(hw), 0.42 * hw)
    hl = max(zc - (zb + kr), 1.0)
    ctrl = [(f * kw, zb + g * kr) for f, g in _KEEL]
    ctrl += [(kw + u * (hw - kw), zb + kr + g * hl) for u, g in _BELLY[1:]]
    if dip:
        ctrl = [(y, z - _pylon_dip(x, y, y / hw)) for (y, z) in ctrl]
    return ctrl


def _upper_ctrl(x: float):
    """CREASE -> deck -> spine: a SQUARED superellipse quadrant.

    A deck written as a fixed fraction table is a shallow cone off the crease,
    and with the crease sitting low in the section (spec pins it to z = 232 at
    x = 1180, only 30 % up) that cone made the whole nose read as a lens with a
    rim. A superellipse quadrant leaves the crease travelling straight UP, so
    the flank above the feature line is vertical and the crown is flat — a
    chiselled box section — and the exponent is the one dial that trades
    squareness for roundness as the nose narrows into the blade.
    """
    hw, _, zt, zc, _ = _section(x)
    m = _deck_exp(x)
    hu = max(zt - zc, 1.0)
    pts = []
    for i in range(N_DECK):
        a = 0.5 * math.pi * (i / (N_DECK - 1)) ** 1.35
        pts.append(
            (hw * math.cos(a) ** (2.0 / m), zc + hu * math.sin(a) ** (2.0 / m))
        )
    pts[-1] = (0.0, zc + hu)
    return pts


def _half_pts(x: float, dip: bool = True):
    """Left-side section outline, centreline keel -> crease -> centreline spine.

    Sampling tightens toward the crease AND toward the keel apex so both corners
    read as real, tight-radius feature lines rather than soft blends.
    """
    lower = _sample_fracs(
        _catmull(_lower_ctrl(x, dip)), _grade_fracs(N_LOWER, 0.11, 1.7, 0.20, 1.9)
    )
    # sample the deck spine -> crease so the tightening lands on the crease,
    # then flip it back into section order
    upper = _sample_fracs(
        list(reversed(_catmull(_upper_ctrl(x)))), _grade_fracs(N_UPPER, 0.16, 1.7)
    )
    return lower + list(reversed(upper))[1:]


def _offset_pts(pts, x: float, d: float, d_low: float | None = None):
    """Grow (d>0) or shrink (d<0) a section outline normal-ish to itself.

    `d_low` throttles the growth below the crease so a proud flange does not
    push the keel down into the front wing's airspace.
    """
    hw, zb, zt, zc, _ = _section(x)
    hl = max(zc - zb, 1.0)
    hu = max(zt - zc, 1.0)
    dl = d if d_low is None else d_low
    sy = (hw + d) / hw
    sl = (hl + dl) / hl
    su = (hu + d) / hu
    return [(y * sy, zc + (z - zc) * (su if z >= zc else sl)) for (y, z) in pts]


def _flank_z(x: float, s: float) -> float:
    """Deck height at y = s * hw — the superellipse solved for z."""
    _, _, zt, zc, _ = _section(x)
    m = _deck_exp(x)
    s = min(max(s, 0.0), 1.0)
    return zc + (zt - zc) * max(1.0 - s**m, 0.0) ** (1.0 / m)


def _circle_pts(cz: float, r: float, n: int = 22):
    return [
        (r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


# ==========================================================================
# BODIES
# ==========================================================================

_CONE_X = (CONE_NOSE_X, 1340.0, 1330.0, 1318.0, 1305.0, 1291.0, 1276.0,
           1259.0, 1240.0, 1219.0, 1195.0, 1168.0, 1138.0, 1104.0, 1066.0,
           1024.0, 978.0, 928.0, 874.0, 818.0, 762.0, 706.0)

_CAP_X = (1420.0, 1416.0, 1411.0, 1405.0, 1398.0, 1390.0, 1381.0, 1371.0,
          1361.0, CAP_BREAK_X)


def _nose_cone():
    faces = [lib.half_section_face(x, _half_pts(x)) for x in _CONE_X]
    return lib.styled(lib.body_loft(faces), "nose_cone", spec.CARBON_GLOSS)


def _tip_cap():
    faces = [lib.half_section_face(x, _half_pts(x)) for x in _CAP_X]
    return lib.styled(lib.body_loft(faces), "nose_tip_cap", spec.CARBON_GLOSS)


def _tip_collar():
    """Machined ring recessed in the tip-cap parting line."""
    faces = [
        lib.half_section_face(x, _offset_pts(_half_pts(x), x, -2.2))
        for x in (1357.0, 1345.0)
    ]
    return lib.styled(lib.body_loft(faces, ruled=True), "tip_collar", spec.ANODIZED)


def _pitot():
    _, zb, zt, zc, _ = _section(TIP_X)
    cz = zc + 0.25 * (zt - zc)  # just above the crease, on the chisel's axis
    probe = lib.body_loft(
        [
            lib.section_face(x, _circle_pts(cz, r))
            for x, r in (
                (1400.0, 5.0), (1420.0, 4.6), (1442.0, 4.0), (1468.0, 3.4),
                (1492.0, 2.8), (1504.0, 2.4), (1509.0, 1.6),
            )
        ]
    )
    boss = lib.body_loft(
        [
            lib.section_face(x, _circle_pts(cz, r))
            for x, r in ((1410.0, 6.6), (1420.0, 5.8), (1430.0, 5.0))
        ]
    )
    return [
        lib.styled(boss, "pitot_boss", spec.ANODIZED),
        lib.styled(probe, "pitot_probe", spec.ALLOY),
    ]


def _accent_stripe():
    """The single ACCENT body: a thin stripe down the nose's top centreline."""
    xs = (CONE_NOSE_X, 1300.0, 1235.0, 1160.0, 1075.0, 985.0, 900.0, 820.0, 745.0)
    faces = []
    for x in xs:
        _, _, zt, _, _ = _section(x)
        t = (CONE_NOSE_X - x) / (CONE_NOSE_X - 745.0)
        hw = 4.6 + 4.0 * t
        faces.append(
            lib.section_face(
                x, lib.superellipse_pts(hw, 1.7, n_top=3.4, n_bot=3.4,
                                        cz=zt + 0.5, samples=22)
            )
        )
    return lib.styled(lib.body_loft(faces), "nose_stripe", spec.ACCENT)


def _bulkhead_flange():
    """Proud parting-line flange at the front bulkhead, exposed weave."""
    stations = ((744.0, 0.4), (736.0, 4.2), (712.0, 4.2), (BREAK_X, 3.4))
    faces = [
        lib.half_section_face(
            x, _offset_pts(_half_pts(x, dip=False), x, d, d_low=0.30 * d)
        )
        for x, d in stations
    ]
    return lib.styled(
        lib.body_loft(faces, ruled=True), "bulkhead_flange", spec.CARBON_WEAVE
    )


def _flange_fasteners():
    x = 720.0
    pts = _offset_pts(_half_pts(x, dip=False), x, 4.2, d_low=1.26)
    full = pts + [(-y, z) for (y, z) in reversed(pts[1:-1])]
    _, _, _, zc, _ = _section(x)

    dense = []
    for i in range(len(full)):
        a, b = full[i], full[(i + 1) % len(full)]
        for k in range(10):
            u = k / 10.0
            dense.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))

    n = len(dense)
    seg = [math.dist(dense[i], dense[(i + 1) % n]) for i in range(n)]
    total = sum(seg)
    cum, acc = [], 0.0
    for s in seg:
        cum.append(acc)
        acc += s

    out = []
    for k in range(N_FASTENERS):
        target = (k + 0.5) * total / N_FASTENERS
        i = max(j for j in range(n) if cum[j] <= target)
        y, z = dense[i]
        py, pz = dense[(i - 1) % n]
        ny, nz = dense[(i + 1) % n]
        ty, tz = ny - py, nz - pz
        L = math.hypot(ty, tz) or 1.0
        oy, oz = tz / L, -ty / L
        if oy * y + oz * (z - zc) < 0:
            oy, oz = -oy, -oz
        plane = lib.plate_plane((x, y, z), (0.0, oy, oz))
        head = plane * Cylinder(3.6, 7.0)
        boss = plane * Pos(0, 0, 2.6) * Cylinder(1.8, 3.4)
        out.append(lib.styled(head + boss, f"flange_fastener_{k:02d}", spec.STEEL))
    return out


# (x, half-width, half-height, rise of the pad underside above PYLON_Z)
_PAD_STATIONS = ((1316.0, 11.0, 6.0, 10.5), (1284.0, 22.0, 8.0, 2.6),
                 (PYLON_X, 26.0, 9.0, 0.0), (1218.0, 22.0, 8.0, 2.6),
                 (1192.0, 11.0, 5.0, 8.0))


def _pylon_pad():
    """Laminated mounting pad in the underside trough, where a pylon lands."""
    faces = [
        lib.section_face(
            x,
            lib.superellipse_pts(hw, hh, n_top=2.6, n_bot=2.9,
                                 cy=PYLON_Y, cz=PYLON_Z + rise + hh, samples=26),
        )
        for x, hw, hh, rise in _PAD_STATIONS
    ]
    return lib.body_loft(faces)


def _pylon_bolts():
    out = []
    for i, (x, rise) in enumerate(((1284.0, 2.6), (PYLON_X, 0.0), (1218.0, 2.6))):
        r = 5.2 - 0.8 * abs(i - 1)
        out.append(Pos((x, PYLON_Y, PYLON_Z + rise + 1.6)) * Cylinder(r, 5.4))
    return out


def _camera_pod():
    stations = ((CAM_NOSE_X, 22.0, 20.0), (992.0, 26.0, 24.0),
                (972.0, 27.0, 25.0), (946.0, 24.0, 22.0),
                (912.0, 16.0, 14.0), (CAM_TAIL_X, 5.5, 4.5))
    faces = [
        lib.section_face(
            x,
            lib.superellipse_pts(hw, hh, n_top=2.6, n_bot=2.3,
                                 cy=CAM_Y, cz=CAM_Z, samples=26),
        )
        for x, hw, hh in stations
    ]
    return lib.body_loft(faces)


def _camera_stalk():
    return lib.blade_member(
        CAM_ROOT, (950.0, CAM_Y - 4.0, CAM_Z - 6.0),
        68.0, 42.0, thickness_ratio=0.15,
    )


def _camera_optics():
    bezel_plane = lib.plate_plane((1005.0, CAM_Y, CAM_Z), (1.0, 0.0, 0.0))
    lens_plane = lib.plate_plane((1009.0, CAM_Y, CAM_Z), (1.0, 0.0, 0.0))
    return (
        bezel_plane * Cylinder(19.0, 14.0),
        lens_plane * Cylinder(13.5, 12.0),
    )


_VANE_S = (0.44, 0.59, 0.73, 0.87, 0.995)
_VANE_DZ = (9.0, 9.0, 8.0, 6.0, -6.0)  # tip dives into the flank crease


def _vane_station(le_x: float, chord: float, twist: float, sweep: float, i: int):
    s, dz = _VANE_S[i], _VANE_DZ[i]
    f = (s - _VANE_S[0]) / (_VANE_S[-1] - _VANE_S[0])
    x = le_x - sweep * f
    hw, _, _, _, _ = _section(x)
    return {
        "le": (x, s * hw, _flank_z(x, s) + dz),
        "chord": chord * (1.0 - 0.55 * f),
        "twist": twist + 5.0 * f,
        "thickness": 0.085,
        "camber": 0.040,
    }


def _nose_vane(le_x: float, chord: float, twist: float, sweep: float):
    """A stood-off slat: free inboard end on a strut, tip dying into the crease."""
    stations = [
        _vane_station(le_x, chord, twist, sweep, i) for i in range(len(_VANE_S))
    ]
    vane = lib.wing_element(stations)
    root = stations[0]
    rx = root["le"][0] - 0.42 * root["chord"]
    ry, rz = root["le"][1], root["le"][2]
    strut = lib.blade_member(
        (rx, ry, rz + 2.0), (rx, ry * 0.985, rz - 17.0),
        0.34 * root["chord"], 0.28 * root["chord"], thickness_ratio=0.30,
    )
    return vane, strut


# ==========================================================================
# PUBLIC BUILDER
# ==========================================================================


def build_nose():
    bodies = [
        _nose_cone(),
        _tip_cap(),
        _tip_collar(),
        _accent_stripe(),
        _bulkhead_flange(),
    ]
    bodies += _pitot()
    bodies += _flange_fasteners()

    bodies += lib.pair(_pylon_pad(), "pylon_pad", spec.CARBON)
    for i, b in enumerate(_pylon_bolts()):
        bodies += lib.pair(b, f"pylon_bolt_{i}", spec.STEEL)

    bodies += lib.pair(_camera_pod(), "camera_pod", spec.CARBON_GLOSS)
    bodies += lib.pair(_camera_stalk(), "camera_stalk", spec.CARBON)
    bezel, lens = _camera_optics()
    bodies += lib.pair(bezel, "camera_bezel", spec.ANODIZED)
    bodies += lib.pair(lens, "camera_lens", spec.GLASS)

    chords = spec.cascade_chords(64.0, 2)
    for i, (le_x, twist, sweep) in enumerate(
        ((1156.0, 7.0, 46.0), (1064.0, 12.0, 40.0))
    ):
        vane, strut = _nose_vane(le_x, chords[i], twist, sweep)
        bodies += lib.pair(vane, f"nose_vane_{i}", spec.CARBON)
        bodies += lib.pair(strut, f"nose_vane_strut_{i}", spec.CARBON)

    return lib.group("nose", bodies)
