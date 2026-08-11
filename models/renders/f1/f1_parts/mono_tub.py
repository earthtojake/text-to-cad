"""Survival cell: the sculpted carbon tub, its cockpit trough, roll structure.

THE SECTION LAW
---------------
Every station is one closed outline, written outboard as a front-view sketch
in (y, z) and read from the centreline keel up and over to the centreline
spine.  Five named features, blended from the keyframe table below:

    KEEL   centreline bottom, `zb`            the tub's own floor
    CHINE  bottom corner, radius `rc`         where the belly turns vertical
    CREASE `spec.shoulder_at(x)` -> (hw, zc)  THE feature line
    SHOULDER top corner, radius `rs`          the deck's outer knuckle
    SPINE  centreline top, `zt` + `crown`

THE CREASE IS A CORNER, NOT A BLEND
-----------------------------------
An earlier tub rolled through the crease at a 143 deg included angle — a soft
knuckle that lit as one continuous highlight, so the body read as a
shrink-wrapped pod. The section is now built as TWO CUBICS THAT MEET AT AN
ANGLE, and the outline carries two points 2 * `CREASE_D` apart straddling the
corner so the interpolating spline has to turn inside a 9 mm knuckle instead of
rounding over the neighbouring 60 mm:

    below   the flank leaves the chine VERTICAL and flares outboard, arriving
            at the crease leaning 20 deg (nose) to 57 deg (cockpit) off
            vertical. Its second derivative is outward, so the flank is
            SCOOPED: the crease overhangs a belly that tucks in by up to 112 mm
            and the whole lower surface faces down-and-out, into shadow.
    above   the deck leaves the crease nearly HORIZONTAL (68-89 deg off
            vertical), turns up within ~60 mm and runs to the knuckle as a
            taut, near-vertical cockpit side.

Included angle at the crease is 45-70 deg the whole length of the tub, so one
hard line catches the key light from the bulkhead to the engine face while the
flank under it stays dark. That contrast is the shoulder line; without it the
same volume is a blob.

Every outline is generated ANALYTICALLY with a fixed point count per feature,
never by arc-length re-sampling a polyline. Re-sampling moved each point along
the outline as a piecewise-linear function of x, and those kinks in the loft's
control net came back as a chevron ripple with exactly the station pitch.

The tub is one loft from the nose panel break (x = 700, where the section is
handed over from `nose.py` — half width 194.6, z 157..300, crease at z 266)
to the engine mounting face at `spec.SURVIVAL_CELL_REAR_X`.  Below z = 157 at
the bulkhead the tub fairs its OWN keel: the nose sits on top of a tub that
continues below it.

The cockpit is cut, not modelled hollow: one lofted cavity whose floor rises
at both ends, so the opening's plan outline is where that floor breaches the
deck.  The rolled rim is a genuine swept bead (2 * TIP_ROLL_R tall, rolled at
TIP_ROLL_R) running around the front and both sides and dying into the
headrest shoulders — a feature line that terminates into another body.
"""

from __future__ import annotations

import math

from . import lib, spec

# ==========================================================================
# STATIONS
# ==========================================================================

X_FRONT = spec.BULKHEAD_FRONT_X  # 700 — nose panel break
X_REAR = spec.SURVIVAL_CELL_REAR_X  # -1980 — engine mounting face

#  Station count is a TESSELLATION decision as much as a shape one. The skin is
#  one B-spline face with no interior boundary, so the mesher's rows fall on the
#  surface's own v-knots — one per station. At 22 stations the rows are 128 mm
#  apart and each quad twists enough that its two triangles disagree, which
#  renders as a sawtooth chevron running the whole length of the shoulder. The
#  surface itself was never rippled (its crease line is monotone to <1 mm
#  between stations); only the mesh was. Do not drop this back below ~28: the
#  cost is boolean time against a bigger skin face, and the payoff is a shoulder
#  that stays a line instead of a zigzag.
N_STATIONS = 42

#  `lwf` is the CHINE half-width as a fraction of the crease half-width, i.e.
#  how hard the belly tucks in under the shoulder. It runs 0.90 at the bulkhead
#  (a small section that still has to meet the nose) down to 0.72 alongside the
#  driver, which is 112 mm of undercut in 141 mm of flank height.
#  `th` is the DECK KNUCKLE half-width as a fraction of the crease. It has to
#  stay high enough that the rolled cockpit rim (`cw` + _RIM_W/2) still lands on
#  the flat deck rather than hanging over the knuckle round; the deck's
#  fall-away is set by the crease TANGENT (DECK_KY), not by this number.
#  x,     hw,   zb,   kr,  rc,  lwf,   zt,   th,    rs,  crown
_KEYS = (
    (700.0, 194.6, 110.0, 28.0, 28.0, 0.900, 300.0, 0.860, 26.0, 0.0),
    (620.0, 205.0, 110.0, 26.0, 29.0, 0.888, 330.0, 0.868, 30.0, 2.0),
    (480.0, 220.0, 107.0, 20.0, 30.0, 0.868, 404.0, 0.878, 36.0, 3.0),
    (380.0, 236.0, 105.0, 16.0, 30.0, 0.850, 456.0, 0.884, 42.0, 4.0),
    (300.0, 251.0, 104.0, 14.0, 30.0, 0.833, 500.0, 0.886, 46.0, 5.0),
    (150.0, 282.0, 104.0, 13.0, 32.0, 0.805, 552.0, 0.882, 46.0, 6.0),
    (0.0, 305.0, 105.0, 13.0, 34.0, 0.784, 588.0, 0.876, 50.0, 6.0),
    (-180.0, 325.0, 106.0, 13.0, 38.0, 0.770, 612.0, 0.870, 54.0, 6.0),
    (-330.0, 340.0, 109.0, 14.0, 42.0, 0.760, 630.0, 0.865, 58.0, 6.0),
    (-530.0, 358.0, 115.0, 14.0, 46.0, 0.748, 652.0, 0.860, 60.0, 5.0),
    (-700.0, 376.0, 123.0, 14.0, 48.0, 0.738, 670.0, 0.856, 60.0, 4.0),
    (-900.0, 390.0, 133.0, 14.0, 50.0, 0.729, 686.0, 0.852, 58.0, 3.0),
    (-1100.0, 397.0, 145.0, 13.0, 52.0, 0.722, 693.0, 0.849, 56.0, 2.0),
    (-1300.0, 400.0, 157.0, 13.0, 54.0, 0.720, 697.0, 0.847, 54.0, 2.0),
    (-1420.0, 400.0, 165.0, 13.0, 54.0, 0.722, 697.0, 0.847, 54.0, 2.0),
    (-1560.0, 400.0, 175.0, 13.0, 56.0, 0.732, 672.0, 0.851, 58.0, 3.0),
    (-1700.0, 396.0, 185.0, 13.0, 56.0, 0.750, 622.0, 0.856, 62.0, 4.0),
    (-1850.0, 386.0, 195.0, 13.0, 54.0, 0.782, 588.0, 0.862, 62.0, 4.0),
    (-1980.0, 374.0, 203.0, 13.0, 52.0, 0.820, 570.0, 0.868, 60.0, 4.0),
)


_TANGENTS: dict = {}


def _tangents(table):
    """Fritsch-Carlson slopes for every column of a keyframe table.

    Smoothstep between keyframes forces the slope to ZERO at each one, so a
    densely keyed law undulates between them and the loft carries that
    undulation into the skin as a chevron ripple. A monotone cubic keeps the
    law genuinely smooth and still never overshoots a keyframe.
    """
    key = id(table)
    if key in _TANGENTS:
        return _TANGENTS[key]
    xs = [r[0] for r in table]
    cols = []
    for j in range(1, len(table[0])):
        v = [r[j] for r in table]
        d = [
            (v[i + 1] - v[i]) / (xs[i + 1] - xs[i]) for i in range(len(v) - 1)
        ]
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
                m = cols[j - 1]
                out.append(
                    h00 * a[j] + h10 * h * m[i] + h01 * b[j] + h11 * h * m[i + 1]
                )
            return tuple(out)
    return table[-1][1:]


def _sec(x: float):
    """(hw, zb, kr, rc, lw, zt, th, rs, crown, zc) at station x."""
    hw, zb, kr, rc, lwf, zt, th, rs, crown = _blend(_KEYS, x)
    hw_line, zc = spec.shoulder_at(x)
    hw = min(hw, spec.CHASSIS_MAX_HALF_W)
    return hw, zb, kr, rc, hw * lwf, zt, th, rs, crown, zc


def tub_top(x: float) -> float:
    """Deck height on the centreline — the halo and the rim bead ride on it."""
    return _sec(x)[5]


# ==========================================================================
# OUTLINE SAMPLING
#
# Fixed point count per feature, generated straight from the blended section
# law. Sample k of every station is therefore a SMOOTH function of x, which is
# the whole point: the loft's control net has no kinks in it, so the skin has
# no ripple in it. (Arc-length re-sampling of a dense polyline — what this used
# to do — is only C0 in x, because a sample crossing a polyline vertex breaks
# the derivative. That showed up as a chevron wave at the station pitch.)
# ==========================================================================

N_KEEL = 5  # centreline keel -> chine arc
N_CHINE = 5  # chine arc, -90 deg -> vertical
N_FLANK = 6  # scooped flank, chine -> crease
N_DECK = 7  # deck, crease -> knuckle arc
N_KNUCK = 5  # knuckle arc, vertical -> flat
N_SPINE = 5  # flat deck -> centreline spine

CREASE_D = 4.5  # the two crease points sit this far either side of the corner

FLANK_H = 0.45  # chine-end handle: how long the flank stays vertical
FLANK_KY, FLANK_KZ = 0.58, 0.30  # crease-end handle -> the flank's lean-out
DECK_KY, DECK_KZ = 0.85, 0.04  # crease-end handle -> the deck's fall-away
DECK_H = 0.55  # knuckle-end handle: how long the cockpit side stays vertical


def _arc(cy, cz, r, a0, a1, n):
    return [
        (
            cy + r * math.cos(math.radians(spec.lerp(a0, a1, i / n))),
            cz + r * math.sin(math.radians(spec.lerp(a0, a1, i / n))),
        )
        for i in range(n + 1)
    ]


def _bez(p0, c1, c2, p3, t: float):
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p3[1],
    )


def _unit(vy: float, vz: float):
    m = math.hypot(vy, vz) or 1.0
    return vy / m, vz / m


def _outline(x: float):
    """(below-crease points, above-crease points, flank dir, deck dir).

    Split at the corner so the two cubics can state their own crease tangents.
    """
    hw, zb, kr, rc, lw, zt, th, rs, crown, zc = _sec(x)
    bw = max(lw - rc, 14.0)
    lw = bw + rc  # keep the chine arc and the flank start consistent
    z0 = zb + kr + rc  # chine top — the flank leaves here vertical
    yk, zk = hw * th, zt - rs
    dyf, dzf = hw - lw, zc - z0  # flank box
    dyd, dzd = hw - yk, zk - zc  # deck box

    # THE CORNER. Both crease points sit ON their own cubic, `CREASE_D` from the
    # corner, and each cubic is sampled only up to / away from that point.
    #
    # They used to be offset along the corner's TANGENT LINES instead, which is
    # the same thing only while the offset is tiny. At CREASE_D = 4.5 each one
    # landed INBOARD of its own neighbouring on-curve sample, so the outline
    # doubled back on itself at the crease — a cusp. `make_face` accepts the
    # self-intersecting periodic spline and reports a valid, positive-area face,
    # so nothing local complains; the loft then dies with a bare
    # "BRep_API: command not done" on whichever station pair is worst.
    uy, uz = _unit(dyf * FLANK_KY, dzf * FLANK_KZ)
    vy, vz = _unit(-dyd * DECK_KY, dzd * DECK_KZ)
    f0, f3 = (lw, z0), (hw, zc)
    f1 = (lw, z0 + dzf * FLANK_H)
    f2 = (hw - dyf * FLANK_KY, zc - dzf * FLANK_KZ)
    d0, d3 = (hw, zc), (yk, zk)
    d1 = (hw - dyd * DECK_KY, zc + dzd * DECK_KZ)
    d2 = (yk, zk - dzd * DECK_H)
    # |dP/dt| at the corner, so CREASE_D converts to a parameter offset
    sf = 3.0 * math.hypot(f3[0] - f2[0], f3[1] - f2[1])
    sd = 3.0 * math.hypot(d1[0] - d0[0], d1[1] - d0[1])
    tf = max(0.55, 1.0 - CREASE_D / max(sf, 1e-6))
    td = min(0.45, CREASE_D / max(sd, 1e-6))

    # keel — a shallow vee, horizontal on the centreline so the mirror is smooth
    pts = [(0.0, zb)]
    for i in range(1, N_KEEL + 1):
        t = i / N_KEEL
        pts.append((bw * t**0.92, zb + kr * t**1.75))
    # chine
    pts += _arc(bw, z0, rc, -90.0, 0.0, N_CHINE)[1:]
    # flank — vertical off the chine, flaring out to overhang the belly
    for i in range(1, N_FLANK + 1):
        pts.append(_bez(f0, f1, f2, f3, tf * (1.0 - (1.0 - i / N_FLANK) ** 1.8)))

    # deck — falls away off the crease, then stands up as the cockpit side
    up = []
    for j in range(N_DECK + 1):
        up.append(_bez(d0, d1, d2, d3, td + (1.0 - td) * (j / N_DECK) ** 1.7))
    # knuckle
    up += _arc(yk - rs, zk, rs, 0.0, 90.0, N_KNUCK)[1:]
    # spine — flat off the knuckle, flat again on the centreline
    ytop = yk - rs
    for i in range(1, N_SPINE + 1):
        u = i / N_SPINE
        up.append((ytop * (1.0 - u), zt + crown * (1.0 - (1.0 - u) ** 2) ** 1.2))
    return pts, up, (uy, uz), (vy, vz)


def _half_pts(x: float):
    """One station's left-side outline, corner included: keel -> spine."""
    lo, up, _, _ = _outline(x)
    return lo + up


def _check_outline(x: float, pts):
    """Fail HERE, not four operations later, if the outline doubles back.

    The outline has to be a fan: y climbs to the crease and falls away after it,
    z never descends. Break either and the periodic spline through the points
    loops — and a looped section is silent. `make_face` returns a valid,
    positive-area face; only the loft notices, and all it says is
    "BRep_API: command not done" against a station pair rather than a point.
    """
    ys = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    k = ys.index(max(ys))
    bad = next(
        (i for i in range(1, k + 1) if ys[i] < ys[i - 1] - 1e-7),
        next((i for i in range(k + 1, len(ys)) if ys[i] > ys[i - 1] + 1e-7), None),
    )
    if bad is None:
        bad = next((i for i in range(1, len(zs)) if zs[i] < zs[i - 1] - 1e-7), None)
        if bad is None:
            return
        raise ValueError(
            f"tub station x={x:.1f} descends at point {bad}: "
            f"{pts[bad - 1]} -> {pts[bad]}"
        )
    raise ValueError(
        f"tub station x={x:.1f} doubles back at point {bad} (crease at {k}): "
        f"{pts[bad - 1]} -> {pts[bad]}"
    )


# ==========================================================================
# WHY THE CORNER IS 9 MM WIDE AND NOT 3
#
# The crease is carried on ONE periodic spline per station (`half_section_face`)
# and the shape of that corner is right at any width: measured across two
# station intervals the crease line is smooth to 0.12 mm in y. What is NOT free
# is the MESH. The skin is a single 2.7 m B-spline face and the artifact
# pipeline tessellates it at 0.6 rad angular tolerance, so a 1.4 mm corner gets
# about three facets, they disagree from row to row, and the shoulder renders as
# a sawtooth. Widening the corner to `CREASE_D` = 4.5 (a 9 mm knuckle, still a
# quarter of a percent of the section) gives the mesher room while reading as a
# crisp double-edged highlight rather than a rounded-off blend.
#
# Two alternatives were built and measured, and both are worse:
#   * splitting the station into four edges so the crease is a real B-REP edge
#     works and cuts cleanly, but each strip then carries far fewer knots and
#     the whole skin drops to ~1.5 k triangles — every surface goes faceted to
#     fix one line;
#   * `Spline(tangents=...)` to state the corner tangents exactly: build123d
#     normalises tangent magnitude, and the stated tangent blew the left deck
#     out to 1094 mm against its own mirror's 670 mm. That lopsided solid still
#     passed `is_valid_shape` AND the cockpit cut against it silently returned
#     the tub unmodified — the exact silent failure this module warns about.
# ==========================================================================


# ==========================================================================
# COCKPIT OPENING
#
# `cw` is the opening's plan half-width and `zf` its floor. The opening's
# outline is where that floor breaches the deck, so the front lip is a real
# 120 mm plan round rather than a wedge — which is what lets a 2*TIP_ROLL_R
# bead wrap it without pinching.
# ==========================================================================

#  x,       cw,    zf
_OPEN = (
    (-500.0, 8.0, 644.0),
    (-506.0, 37.5, 618.0),
    (-515.0, 58.0, 596.0),
    (-530.0, 79.4, 560.0),
    (-550.0, 97.5, 518.0),
    (-575.0, 111.2, 476.0),
    (-600.0, 118.3, 432.0),
    (-620.0, 120.0, 400.0),
    (-700.0, 172.0, 348.0),
    (-800.0, 210.0, 316.0),
    (-900.0, 232.0, 304.0),
    (-1060.0, 243.0, 300.0),
    (-1200.0, 242.0, 306.0),
    (-1300.0, 230.0, 326.0),
    (-1370.0, 205.0, 372.0),
    (-1420.0, 160.0, 448.0),
    (-1452.0, 96.0, 546.0),
    (-1472.0, 20.0, 630.0),
    (-1484.0, 6.0, 700.0),
)

_CAV_TOP = 760.0  # just clear of the deck: a tall thin cavity meshes badly


def _open_at(x: float):
    return _blend(_OPEN, x)


#  A cutting tool must never taper to a sliver. Sampled straight from _OPEN,
#  the cavity ends 8 mm and 6 mm wide, which put seven near-coincident points
#  into a periodic spline and made the end sections near-degenerate. The loft
#  still succeeded and still reported valid, but the cut against the tub then
#  produced exactly one bad face — and every later fuse onto that body raised
#  "Null TopoDS_Shape object" from a call nowhere near the real cause.
#
#  So the tool is retired gracefully instead: below _CAV_MIN_W the section is
#  widened to a well-conditioned size and its floor is lifted clear above the
#  local tub top, so those stations remove nothing. The visible opening is
#  unchanged — the trough is defined by where the floor drops below tub_top,
#  and that happens well inboard of both ends.
#  Two independent conditioning rules, and they must not be confused:
#   - WIDTH is always floored, so no station is a sliver. This is purely about
#     spline conditioning and never changes how deep the trough cuts.
#   - The FLOOR is only lifted when it GRAZES the tub top. A cavity floor that
#     sits within a few mm of the skin makes a near-tangent intersection, which
#     is the actual bad-face generator. Pushed clear, those stations remove
#     nothing and the cavity's end caps fall outside the skin entirely.
#     Depth is otherwise untouched, so the visible opening is unchanged.
_CAV_MIN_W = 70.0
_CAV_GRAZE = 20.0  # a floor within this of the tub top is a tangency risk
_CAV_CLEAR = 22.0  # so lift it this far clear instead


def _cavity_at(x: float):
    cw, zf = _open_at(x)
    top = tub_top(x)
    if zf > top - _CAV_GRAZE:
        zf = top + _CAV_CLEAR
    return max(cw, _CAV_MIN_W), zf


def _cavity_pts(x: float):
    cw, zf = _cavity_at(x)
    rr = min(70.0, 0.55 * cw)
    bw = cw - rr
    pts = [(bw * i / 6.0, zf) for i in range(7)]
    pts += _arc(bw, zf + rr, rr, -90.0, 0.0, 6)[1:]
    z0 = zf + rr
    pts += [(cw, z0 + (_CAV_TOP - z0) * i / 5.0) for i in range(1, 6)]
    pts += [(cw * (1.0 - i / 4.0), _CAV_TOP) for i in range(1, 5)]
    return pts


def _cavity():
    """Cockpit trough cutter, sampled with COSINE CLUSTERING toward the ends.

    Evenly spaced stations put the whole floor-retirement transition inside a
    single loft interval, and the resulting spline overshot enough that the cut
    against the tub failed outright — it returned the tub unchanged, still
    reporting a single solid, with one bad face. Clustering the stations at the
    ends resolves the transition over several intervals and the cut is clean.
    Keep the loft SMOOTH: a ruled cavity also cuts validly but leaves faceting
    down the trough walls, which shows on the cockpit's inner surface.
    """
    n = 25
    xs = [
        spec.lerp(_OPEN[0][0], _OPEN[-1][0], 0.5 * (1.0 - math.cos(math.pi * k / (n - 1))))
        for k in range(n)
    ]
    return lib.body_loft([lib.half_section_face(x, _cavity_pts(x)) for x in xs])


# ==========================================================================
# ROLLED RIM — the single detail the cockpit lives or dies on
# ==========================================================================

_RIM_W = 2.0 * spec.TIP_ROLL_R + 2.0 * spec.SKIN_T  # 26 — bead across the lip
_RIM_H = 2.0 * spec.TIP_ROLL_R + 2.0  # bead depth, rolled at TIP_ROLL_R
_RIM_TAIL_X = -1370.0  # the bead dies into the headrest shoulder here


def _rim_path():
    """Lip centreline: rear-left, forward, around the front round, rear-right."""
    xs = [
        -1370.0, -1330.0, -1285.0, -1235.0, -1180.0, -1120.0, -1060.0,
        -1000.0, -940.0, -880.0, -820.0, -760.0, -700.0, -655.0, -620.0,
        -598.0, -575.0, -550.0, -530.0, -515.0, -506.0,
    ]
    left = []
    for i, x in enumerate(xs):
        cw, _ = _open_at(x)
        # taper the buried tail so it tucks under the headrest shoulder
        k = 1.0 if i > 1 else (0.62, 0.86)[i]
        left.append((x, cw, tub_top(x) - spec.TIP_ROLL_R, k))
    tip = (-500.0, 0.0, tub_top(-500.0) - spec.TIP_ROLL_R, 1.0)
    right = [(x, -y, z, k) for (x, y, z, k) in reversed(left)]
    return left + [tip] + right


def _rim_bead():
    path = _rim_path()
    n = len(path)
    secs = []
    for i, (x, y, z, k) in enumerate(path):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        secs.append(
            {
                "plane": lib.plate_plane((x, y, z), d, up=(0, 0, 1)),
                "pts": lib.rounded_plate_pts(
                    _RIM_W * k, _RIM_H * k, spec.TIP_ROLL_R * k
                ),
            }
        )
    return lib.swept_plate(secs)


# ==========================================================================
# TUB
# ==========================================================================


def _tub_solid():
    xs = [
        X_FRONT + (X_REAR - X_FRONT) * k / (N_STATIONS - 1)
        for k in range(N_STATIONS)
    ]
    faces = []
    for x in xs:
        pts = _half_pts(x)
        _check_outline(x, pts)
        faces.append(lib.half_section_face(x, pts))
    skin = lib.body_loft(faces)
    lo, hi = lib.obox(skin)
    if hi[1] > spec.CHASSIS_MAX_HALF_W + 6.0 or lo[2] < 100.0 or hi[2] > 712.0:
        raise ValueError(f"tub loft escaped its sections: {lo} {hi}")
    tub = lib.cut(skin, _cavity())
    if not lib.is_valid_shape(tub):
        raise ValueError("tub cavity cut produced an invalid solid")
    return tub


# ==========================================================================
# ROLL STRUCTURE — a stressed blade arch, never a tube
# ==========================================================================

_HOOP = (
    (-1694.0, 346.0, 440.0, 210.0),
    (-1697.0, 342.0, 520.0, 206.0),
    (-1701.0, 334.0, 605.0, 200.0),
    (-1706.0, 320.0, 690.0, 192.0),
    (-1712.0, 298.0, 765.0, 184.0),
    (-1719.0, 266.0, 828.0, 176.0),
    (-1726.0, 222.0, 876.0, 170.0),
    (-1731.0, 168.0, 906.0, 165.0),
    (-1735.0, 106.0, 920.0, 162.0),
    (-1737.0, 44.0, 925.0, 160.0),
)


def _roll_hoop():
    left = list(_HOOP)
    pts = [(x, y, z) for (x, y, z, _) in left]
    ch = [c for (_, _, _, c) in left]
    apex = (_HOOP[-1][0] - 1.0, 0.0, spec.ROLL_HOOP_TOP_Z - 23.5)
    pts = pts + [apex] + [(x, -y, z) for (x, y, z) in reversed(pts)]
    ch = ch + [_HOOP[-1][3]] + list(reversed(ch))
    return lib.blade_path(pts, ch, thickness_ratio=0.29)


def _hoop_stay():
    return lib.blade_member(
        (-1748.0, 126.0, 898.0),
        (-1924.0, 214.0, 524.0),
        102.0,
        84.0,
        thickness_ratio=0.26,
    )


# ==========================================================================
# HEADREST SHOULDERS — the surround behind the driver, carrying the rim away
# ==========================================================================

#  Every station has to sit PROUD of the deck (`cz + hh` above `tub_top`) for
#  the length that matters. A shoulder buried inside the tub is not just
#  invisible — fusing it is a no-op boolean, and a no-op boolean rebuilds the
#  tub's 2.7 m skin face into one that tessellates 14x coarser (see
#  `_fuse_proud`). The narrow deck this tub now carries is what lets them read.
#  x,      cy,    hw,   cz,    hh
_SHOULDER = (
    (-1330.0, 248.0, 72.0, 672.0, 52.0),
    (-1400.0, 244.0, 82.0, 674.0, 56.0),
    (-1480.0, 238.0, 88.0, 670.0, 56.0),
    (-1570.0, 230.0, 92.0, 648.0, 54.0),
    (-1670.0, 220.0, 90.0, 612.0, 50.0),
    (-1780.0, 210.0, 84.0, 578.0, 43.0),
    (-1890.0, 200.0, 74.0, 552.0, 34.0),
    (-1975.0, 190.0, 64.0, 538.0, 26.0),
)


def _headrest_shoulder():
    faces = [
        lib.section_face(
            x, lib.superellipse_pts(hw, hh, n_top=3.0, n_bot=2.4, cy=cy, cz=cz)
        )
        for (x, cy, hw, cz, hh) in _SHOULDER
    ]
    return lib.body_loft(faces)


# ==========================================================================
# FRONT SUSPENSION BLISTER — the hump the rockers, rack and dampers live under
# ==========================================================================

#  x,     hw,    crest
_BLISTER = (
    (580.0, 52.0, 330.0),
    (520.0, 74.0, 400.0),
    (450.0, 96.0, 480.0),
    (390.0, 110.0, 548.0),
    (320.0, 122.0, 588.0),
    (250.0, 130.0, 606.0),
    (170.0, 132.0, 608.0),
    (80.0, 126.0, 598.0),
    (-10.0, 116.0, 584.0),
    (-90.0, 104.0, 570.0),
    (-170.0, 92.0, 558.0),
)


def _blister():
    faces = []
    for (x, hw, crest) in _BLISTER:
        bot = tub_top(x) - 62.0
        faces.append(
            lib.section_face(
                x,
                lib.superellipse_pts(
                    hw, (crest - bot) / 2.0, n_top=2.9, n_bot=2.3,
                    cz=(crest + bot) / 2.0,
                ),
            )
        )
    return lib.body_loft(faces)


# ==========================================================================
# PICKUP FAIRINGS — every inboard suspension joint grows out of the flank
# ==========================================================================


def _surface_y(x: float, z: float) -> float:
    """Outboard skin half-width at (x, z) — where a fairing has to break out.

    Read straight off the station outline, so it tracks the tuck: a hardpoint
    that used to sit outside a fat deck can end up INSIDE a narrow one.
    """
    pts = _half_pts(x)
    best = 0.0
    for i in range(len(pts) - 1):
        (y0, z0), (y1, z1) = pts[i], pts[i + 1]
        if (z0 - z) * (z1 - z) <= 0.0 and abs(z1 - z0) > 1e-9:
            best = max(best, y0 + (y1 - y0) * (z - z0) / (z1 - z0))
    return best


def _boss(pt, reach: float, chord_in: float, chord_out: float, tr: float = 0.36):
    """A pickup fairing, rooted inside the tub and always breaking the skin.

    `F_UPPER_IN_AFT` sits 20 mm INSIDE the tucked flank, so a fairing that
    stopped 7 mm outboard of its own hardpoint was swallowed whole: the joint
    had no fairing to grow from and the fuse was a no-op. Every fairing is now
    driven out to clear the local skin.
    """
    x, y, z = pt
    out = max(y + 7.0, _surface_y(x, z) + 14.0)
    return lib.blade_member(
        (x, y - reach, z), (x, out, z), chord_in, chord_out, thickness_ratio=tr
    )


#  point,            reach, chord_in, chord_out, tr
_BOSSES = (
    ("wb_lower_fwd", spec.F_LOWER_IN_FWD, 118.0, 158.0, 96.0, 0.28),
    ("wb_lower_aft", spec.F_LOWER_IN_AFT, 108.0, 158.0, 94.0, 0.28),
    ("wb_upper_fwd", spec.F_UPPER_IN_FWD, 96.0, 136.0, 82.0, 0.38),
    ("wb_upper_aft", spec.F_UPPER_IN_AFT, 96.0, 136.0, 82.0, 0.38),
)


def _n_faces(shape) -> int:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    n, ex = 0, TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while ex.More():
        n += 1
        ex.Next()
    return n


def _fuse_proud(shell, others):
    """One multi-argument fuse, and a guard that every body broke the surface.

    A NO-OP FUSE IS NOT FREE. Fusing a body that lies entirely inside the shell
    returns the same volume through the same faces — but OCC rebuilds the tub's
    2.7 m skin face on the way, and the REBUILT FACE TESSELLATES 14x COARSER:
    39 400 triangles became 336, which is what put broad flat panels down the
    deck and a sawtooth along the shoulder. Every later boolean inherits the
    coarse face, so one buried body ruins the whole part. Measured, not
    guessed — the identical fuse of a PROTRUDING body leaves the mesh alone.

    That is why `_SHOULDER` sits proud of the deck and `_boss` drives every
    fairing out past the local skin. The face-count check below is the tripwire:
    if a future edit sinks one of them, the build stops instead of quietly
    shipping a faceted tub. Fusing all of them in ONE call rather than in
    sequence also halves the boolean cost (286 s -> 121 s).
    """
    tools = [g for g in others if g is not None and g.wrapped is not None]
    before = _n_faces(shell)
    fused = shell.fuse(*tools)
    if fused is None or fused.wrapped is None:
        raise ValueError("survival-cell fuse returned a null shape")
    if _n_faces(fused) < before + len(tools):
        raise ValueError(
            "a survival-cell body is buried inside the tub: a no-op fuse "
            "rebuilds the skin face and collapses its tessellation"
        )
    return fused


def build_tub_bodies():
    """Every survival-cell body, already labelled and coloured.

    The tub, its blister, the rolled rim, the headrest shoulders and every
    pickup fairing are FUSED into one solid. Left as separate overlapping
    bodies they interpenetrate, and two interpenetrating meshes give a ragged
    z-fighting seam at render resolution instead of a real edge.
    """
    shell = _tub_solid()
    grown = [_blister(), _rim_bead(), _headrest_shoulder()]
    grown.append(lib.mirror_y(grown[-1]))
    for name, pt, reach, ci, co, tr in _BOSSES:
        b = _boss(pt, reach, ci, co, tr)
        grown += [b, lib.mirror_y(b)]
    rack = _boss(spec.F_RACK_END, 150.0, 210.0, 116.0, 0.34)
    grown += [rack, lib.mirror_y(rack)]
    shell = _fuse_proud(shell, grown).clean()

    hoop = _roll_hoop()
    stay = _hoop_stay()
    hoop = hoop + stay + lib.mirror_y(stay)
    return [
        lib.styled(shell, "survival_cell", spec.CARBON_GLOSS),
        lib.styled(hoop.clean(), "roll_structure", spec.CARBON),
    ]

