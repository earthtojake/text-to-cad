"""Engine cover panel, airbox intake, cooling louvres, aerial fin.

Two REMOVABLE PANELS. Both are genuine shells — an outer loft minus an inner
loft — so every free edge shows carbon thickness and the strip-down animation
can lift them off an engine that is really there underneath.

THE SECTION LAW (engine cover)
------------------------------
Every station is one closed outline built from four named features, written as
a front-view sketch in (y, z) from the centreline bottom, out, and over the
top:

    SILL    (y_cr - uc, z_cr - drop)  the panel's free lower edge, TUCKED IN
    CREASE  (y_cr, z_cr)              THE feature line: widest point, KNUCKLE
    RIDGE   (0,    spine_z + h_r)     centreline crest — a V, not a dome

    RIDGE --deck + spine--> CREASE --skirt--> SILL --(false bottom, cut away)

Both named lines are genuine CORNERS, not highlights, and they are built the
only way a lofted spline section can hold a corner: points 2.4-2.6 mm apart
straddling the vertex, with the tangent on each side taken from the analytic
law of the surface that meets there. The spline is then forced to turn through
the whole included angle inside 5 mm, which at render resolution is an edge.

  * at the CREASE the deck arrives falling at 57-67 deg and the skirt leaves
    at 105-121 deg — the outline turns a hard 52-69 deg corner, and because
    the skirt tucks INBOARD (`_undercut`) the crease is unambiguously the
    widest point of the section with daylight under it;
  * at the RIDGE two tensioned deck surfaces meet on the centreline at about
    110 deg. The spine is zero where the airbox owns the centreline, rises as
    the aperture closes, and the aerial fin then grows straight out of its
    crest — so it starts and ends on another feature, never fading out.

Everything between the two corners is ONE function (`surf_z`): a deck of
`1 - (1 - u)^2` — flat under the spine, turning down hard only in the last
third before the crease — with the spine's `h (1 - v)^2` added on top of it.
Adding rather than butting the two laws together is what keeps the valley at
the foot of the spine tangent-continuous; see `_ridge_z`.

THE COKE-BOTTLE WAIST
---------------------
`crease()` is the plan-view story. Ahead of x = -2860 the sidepod panel owns
`spec.SHOULDER_LINE` (its crease sits at y = 500 at the crest, far outboard of
this panel), so the cover carries its own crease just inboard of the sidepod's
inner wall — a second line, parallel, one panel break away. At x = -2860 the
sidepod is gone and the two lines merge: from there aft the cover's crease IS
`spec.shoulder_at(x)` exactly, pinching 319 -> 176 -> 155 mm and terminating
into the rear-wing pylon root run at (-3800, 62, 386). Half width falls by 58%
between the cockpit and the tail; that is the waist.

THE SPINE
---------
One analytic fall, 852 at the roll hoop to 434 over the gearbox, with the rate
growing rearward (0.45t + 0.55t^3). No table, no keyframes, so there is no
bump and no flat spot anywhere along 1750 mm. It clears the plenum crown
(z = 699 at x = -2235..-2570) by 30 mm and the gearbox casing by 23 mm.

WHAT IS CUT INTO IT
-------------------
* the airbox aperture — the airbox's own outer loft, grown by `spec.PANEL_GAP`,
  subtracted from the cover, so the two panels meet at a real joint, and a
  3.2 mm proud exposed-weave flange (`_aperture_flange`) rings the hole so the
  break is a STEP with a lit edge rather than a smooth continuation;
* six gill louvres per flank, chord and pitch on `spec.CHORD_RATIO` /
  `spec.GAP_RATIO`, each with a slot cut through into the cavity behind it;
* the hot-air exit at the gearbox: the cavity runs out of the back, and a
  rolled bead (radius `spec.TIP_ROLL_R`) wraps the aperture edge.
"""

from __future__ import annotations

import math
from functools import lru_cache

from build123d import Line, Plane, Spline, extrude, make_face

from . import lib, spec

# ==========================================================================
# shared section machinery
# ==========================================================================


def _blend(table, x):
    """Smoothstep-blend a keyframe table (x descending) at station x."""
    if x >= table[0][0]:
        return table[0][1:]
    if x <= table[-1][0]:
        return table[-1][1:]
    for i in range(len(table) - 1):
        a, b = table[i], table[i + 1]
        if b[0] <= x <= a[0]:
            t = spec.smoothstep((a[0] - x) / (a[0] - b[0]))
            return tuple(spec.lerp(a[j], b[j], t) for j in range(1, len(a)))
    return table[-1][1:]


def _super_arc(hw, hh, n, a0, a1, count, cz=0.0):
    """Superellipse arc from a0 to a1 degrees, centred on (0, cz).

    a = 0 is the widest point (y = hw, z = cz); a = 90 is the crown.
    Every station samples the SAME angles, which is what keeps the lofted
    sections parameter-compatible and the skin glassy.
    """
    out = []
    for i in range(count):
        a = math.radians(spec.lerp(a0, a1, i / (count - 1)))
        ca, sa = math.cos(a), math.sin(a)
        out.append(
            (
                hw * math.copysign(abs(ca) ** (2.0 / n), ca),
                cz + hh * math.copysign(abs(sa) ** (2.0 / n), sa),
            )
        )
    return out


def _area(pts) -> float:
    n = len(pts)
    return 0.5 * sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )


def _shrink(pts, t):
    """Similarity shrink about the centroid — can never self-intersect."""
    cy = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)
    r = sum(math.hypot(p[0] - cy, p[1] - cz) for p in pts) / len(pts)
    k = max(0.05, 1.0 - t / max(r, 1e-6))
    return [(cy + (p[0] - cy) * k, cz + (p[1] - cz) * k) for p in pts]


def _offset(pts, t):
    """Offset a closed outline inward by t along its own normal.

    Negative t grows it outward. Falls back to a centroid shrink if the normal
    offset collapses the outline, so a thin section never ships a folded wall.
    """
    n = len(pts)
    w = 1.0 if _area(pts) > 0 else -1.0
    out = []
    for i in range(n):
        y, z = pts[i]
        ya, za = pts[(i - 1) % n]
        yb, zb = pts[(i + 1) % n]
        ty, tz = yb - ya, zb - za
        L = math.hypot(ty, tz) or 1.0
        out.append((y - tz / L * w * t, z + ty / L * w * t))
    a0, a1 = _area(pts), _area(out)
    if a1 * a0 <= 0.0 or abs(a1) < 0.12 * abs(a0):
        return _shrink(pts, t)
    return out


def _bounded(solid, outlines, xs, tol, what):
    """Assert a loft stayed inside the envelope of its own sections.

    A smooth loft can bulge far outside the stations it was built from and the
    result is still a "valid" solid — it just is not the shape that was drawn.
    """
    lo, hi = lib.bbox(solid)
    ys = [p[0] for o in outlines for p in o]
    zs = [p[1] for o in outlines for p in o]
    want = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
    for i in range(3):
        if lo[i] < want[0][i] - tol or hi[i] > want[1][i] + tol:
            raise ValueError(
                f"{what} loft escaped its sections on {'xyz'[i]}: "
                f"[{lo[i]:.0f},{hi[i]:.0f}] want "
                f"[{want[0][i]:.0f},{want[1][i]:.0f}]"
            )
    return solid


def _fuse(base, extras):
    out = base
    for e in extras:
        if e is None:
            continue
        try:
            cand = out + e
            if cand is not None and cand.is_valid and cand.volume > 0:
                out = cand
        except Exception:
            continue
    return out


def _disc_face(center, normal, r, samples=20):
    """A circular face centred on `center`, normal to `normal`."""
    plane = lib.plate_plane(center, normal)
    pts = [
        (r * math.cos(2 * math.pi * i / samples), r * math.sin(2 * math.pi * i / samples))
        for i in range(samples)
    ]
    return plane * make_face(Spline(*pts, periodic=True))


def _dzus(center, normal, r=10.5, sink=1.6, proud=3.0):
    """One Dzus quarter-turn fastener head, sunk into the flange it holds."""
    n = lib.Vector(normal).normalized()
    c = lib.Vector(center)
    return lib.loft_solid(
        [
            _disc_face(c - n * sink, n, r),
            _disc_face(c + n * proud, n, r * 0.88),
        ],
        ruled=True,
    )


# ==========================================================================
# 1. ENGINE COVER — the longest surface on the car
# ==========================================================================

COVER_X0 = -1700.0  # panel break against the cockpit / roll-hoop shoulder
COVER_X1 = -3450.0  # hot-air exit aperture over the gearbox
_SPINE_Z0 = 852.0
_SPINE_Z1 = 434.0

_N_STATIONS = 26  # outer skin stations (>= 14 required; 26 keeps it glassy)
_Q = 2.0  # deck fall exponent: flat under the spine, steep at the crease
_N_BOT = 2.35
_ND, _NS, _NB, _NR = 10, 4, 9, 4  # samples: deck, skirt, false bottom, ridge
_BOTTOM_DEPTH = 78.0
_VERTEX_E = 2.6  # how far a corner's tangent-control points sit from it
_APEX_E = 2.4

_JOIN_X = -2860.0  # aft of here the crease IS spec.SHOULDER_LINE


def spine_z(x: float) -> float:
    """Deck crown height at the foot of the ridge — one accelerating fall."""
    t = min(max((COVER_X0 - x) / (COVER_X0 - COVER_X1), 0.0), 1.0)
    return _SPINE_Z0 - (_SPINE_Z0 - _SPINE_Z1) * (0.45 * t + 0.55 * t**3)


#             x       y_cr    z_cr
_CREASE = (
    (-1700.0, 372.0, 620.0),  # sits on the tub deck, outboard of its knuckle
    (-1780.0, 379.0, 601.0),
    (-1860.0, 384.0, 578.0),
    (-1940.0, 387.0, 552.0),
    (-2020.0, 387.0, 520.0),  # tub ends: the line falls away behind it
    (-2100.0, 384.0, 480.0),
    (-2180.0, 379.0, 442.0),
    (-2260.0, 373.0, 419.0),
    (-2400.0, 356.0, 412.0),  # from here it runs just inboard of the sidepod
    (-2560.0, 334.0, 410.0),
    (-2740.0, 320.0, 411.0),  # sidepod trailing edge
    (_JOIN_X,) + tuple(spec.shoulder_at(_JOIN_X)),
)


def crease(x: float):
    """(y, z) of the panel's primary feature line at station x."""
    if x <= _JOIN_X:
        return spec.shoulder_at(x)
    return _blend(_CREASE, x)


def _drop(x: float) -> float:
    """Skirt depth: how far the free lower edge sits below the crease."""
    if x >= -3150.0:
        return 27.0
    return 27.0 + 39.0 * spec.smoothstep((-3150.0 - x) / 300.0)


def _undercut(x: float) -> float:
    """How far the sill tucks INBOARD of the crease.

    This is what turns the crease from a tangent point into a knuckle: with a
    vertical skirt the deck leaves the crease vertically and the skirt runs
    down vertically, so the section is smooth through the "crease" and the
    flank reads as one rolled tube. Tucking the sill in puts a real included
    angle at the vertex and a shadow under it.
    """
    return min(0.80 * _drop(x), 24.0)


def sill_z(x: float) -> float:
    return crease(x)[1] - _drop(x)


#            x       h_r     the centreline ridge height above the deck crown
_RIDGE = (
    (-1860.0, 0.0),  # the airbox still owns the centreline ahead of here
    (-1980.0, 15.0),
    (-2260.0, 30.0),
    (-3120.0, 30.0),
    (-3450.0, 20.0),
)


def _ridge_h(x: float) -> float:
    return max(_blend(_RIDGE, x)[0], 0.0)


def _ridge_w(x: float) -> float:
    """Half-width the spine is faired out over — it narrows with the panel."""
    return 0.18 * crease(x)[0] + 26.0


def _ridge_z(x: float, y: float) -> float:
    """How much the spine lifts the deck at (x, |y|).

    `(1 - v)^2`, NOT a straight tent. A tent is a corner at BOTH ends: sharp on
    the centreline (wanted) and a tangent break in the valley where it lands on
    the deck (not wanted). That valley break was a visible defect — the deck
    sample either side of it sits 39 mm out and the tent's 13 mm in, and an
    interpolating spline asked to turn 24 deg across that spacing ripples, which
    on a near-flat panel shows up as a band of noise down the whole cover. The
    square is zero-valued AND zero-sloped at v = 1, so it lands on the deck with
    no corner at all, while still leaving a genuine 110 deg crest at v = 0.
    """
    w = _ridge_w(x)
    v = min(abs(y), w) / max(w, 1e-6)
    return _ridge_h(x) * (1.0 - v) ** 2


def apex_z(x: float) -> float:
    """Height of the centreline ridge crest — the top of the panel."""
    return spine_z(x) + _ridge_h(x)


def surf_z(x: float, y: float) -> float:
    """Height of the outer skin at (x, |y|) — deck law plus the spine."""
    y_cr, z_cr = crease(x)
    z_cw = spine_z(x)
    ay = min(abs(y), y_cr)
    u = min(max((y_cr - ay) / max(y_cr - _ridge_w(x), 1e-6), 0.0), 1.0)
    return z_cr + (z_cw - z_cr) * (1.0 - (1.0 - u) ** _Q) + _ridge_z(x, ay)


def _deck_slope(x: float) -> float:
    """dz/dy where the deck arrives at the crease (negative: falling outboard)."""
    y_cr, z_cr = crease(x)
    return -(spine_z(x) - z_cr) * _Q / max(y_cr - _ridge_w(x), 1e-6)


def _unit(dy: float, dz: float):
    n = math.hypot(dy, dz) or 1.0
    return dy / n, dz / n


def _sec_pts(x: float, inset: float = 0.0):
    """The closed outline at station x — 60 points, same law every time.

    Point count and ordering are IDENTICAL at every station (the corners are
    always at the same indices) so the loft's sections stay parameter
    compatible and the two creases sweep as continuous edges instead of
    wandering across the skin.

    `inset` walks the WHOLE LAW inward by that many mm (negative grows it), and
    that is deliberately not `_offset()`. A normal-offset of a point list
    cannot survive a corner: the two 2.6 mm tangent-control points either side
    of the crease sit well inside the 7-9 mm the cavity is inset by, so their
    offsets swap over and the inner outline self-intersects — which is exactly
    how a cavity loft fails after a smooth section is given a knuckle. Moving
    the crease along its own mitred bisector, the sill along the skirt normal
    and the crown straight down reproduces the corner at the correct wall
    thickness instead of trying to slide the samples sideways.
    """
    y_cr, z_cr = crease(x)
    z_cw, z_ap = spine_z(x), apex_z(x)
    z_si, drop = sill_z(x), _drop(x)
    uc = _undercut(x)
    y_si = y_cr - uc
    w, h = _ridge_w(x), _ridge_h(x)
    depth = _BOTTOM_DEPTH

    sy, sz = _unit(-0.75 * uc, -drop)  # crease -> sill, down the skirt
    dy, dz = _unit(-1.0, -_deck_slope(x))  # crease -> deck, inboard and up

    if inset:
        t = inset
        by, bz = _unit(sy + dy, sz + dz)  # interior bisector at the crease
        sina = max(abs(sy * bz - sz * by), 0.25)  # sin of the half angle
        y_cr += by * t / sina
        z_cr += bz * t / sina
        y_si += sz * t  # the skirt's own inward normal is (sz, -sy)
        z_si += -sy * t
        z_cw -= t
        # the ridge's steepest slope is 2h/w at the crest, so a normal inset of
        # t drops the crest by t*hypot(w, 2h)/w, not by t
        z_ap -= t * math.hypot(w, 2.0 * h) / max(w, 1e-6)
        depth = max(depth - t, 10.0)
        uc, drop = y_cr - y_si, z_cr - z_si
        if drop < 6.0:
            drop, z_si = 6.0, z_cr - 6.0
        if uc < 2.0:
            uc, y_si = 2.0, y_cr - 2.0
        sy, sz = _unit(-0.75 * uc, -drop)

    # 1. false bottom — cut away by `_sill_cutter`, it only closes the outline
    half = _super_arc(y_si, depth, _N_BOT, -90.0, 0.0, _NB, cz=z_si)[:-1]

    # 2. skirt: sill -> crease, leaning outboard as it rises (the undercut)
    for s in (0.0, 0.30, 0.58, 0.80)[:_NS]:
        half.append((y_si + uc * s**0.75, z_si + drop * s))

    # 3. THE CREASE — a forced corner: below-tangent, vertex, above-tangent
    half.append((y_cr + _VERTEX_E * sy, z_cr + _VERTEX_E * sz))
    half.append((y_cr, z_cr))
    half.append((y_cr + _VERTEX_E * dy, z_cr + _VERTEX_E * dz))

    # 4/5. ONE curve from the crease to the crest — deck law plus the spine.
    # Both are evaluated from the same `zz`, so the valley where the spine
    # lands on the deck is a point on a single smooth function rather than a
    # junction between two differently-sampled laws.
    hh = z_ap - z_cw

    def zz(y: float) -> float:
        u = min(max((y_cr - y) / max(y_cr - w, 1e-6), 0.0), 1.0)
        v = min(max(y, 0.0), w) / max(w, 1e-6)
        return z_cr + (z_cw - z_cr) * (1.0 - (1.0 - u) ** _Q) + hh * (1.0 - v) ** 2

    for k in range(1, _ND + 1):  # crease -> the foot of the spine
        y = y_cr - ((k / _ND) ** 1.30) * (y_cr - w)
        half.append((y, zz(y)))
    for v in (0.72, 0.48, 0.26, 0.10)[:_NR]:  # up the spine flank
        half.append((w * v, zz(w * v)))
    half.append((_APEX_E, zz(_APEX_E)))  # THE SPINE — forced corner on y = 0
    half.append((0.0, z_ap))
    return half + [(-y, z) for (y, z) in reversed(half[1:-1])]


#            x      wall
_WALL = (
    (-1700.0, 9.0),
    (-2400.0, 8.0),
    (-3000.0, 7.0),
    (-3300.0, 8.0),
    (-3450.0, 9.0),
)


def _wall(x: float) -> float:
    return max(_blend(_WALL, x)[0], spec.SKIN_T)


_STATIONS = tuple(
    COVER_X0 + (COVER_X1 - COVER_X0) * k / (_N_STATIONS - 1)
    for k in range(_N_STATIONS)
)
# The cavity runs 45 mm out of each end so the shell is open front and back —
# but it is lofted through the SKIN'S OWN STATIONS plus those two, not through
# its own evenly spaced stack. Once the sections carry corners, a cavity whose
# stations are interleaved with the skin's makes OCC's cut return the uncut
# solid (no error, no warning, a 317-litre "shell"); aligning them and adding
# the two overruns hollows it correctly.
_CAV_STATIONS = (-1655.0,) + _STATIONS + (-3505.0,)


# ---------------------------------------------------------------- panel cut


def _sill_cutter():
    """Everything below the sill line, as one extruded side-view profile.

    The free lower edge follows a curve in side view, so it is cut with a
    profile drawn in the XZ plane rather than a stack of section faces — that
    keeps the edge exactly on `sill_z()` at every station.
    """
    xs = [-1650.0 - 40.0 * k for k in range(47)]
    top = [(x, sill_z(x)) for x in xs]
    x0, x1 = top[0][0], top[-1][0]
    prof = (
        Spline(*top)
        + Line(top[-1], (x1, 90.0))
        + Line((x1, 90.0), (x0, 90.0))
        + Line((x0, 90.0), top[0])
    )
    return extrude(Plane.XZ * make_face(prof), amount=1300, both=True)


# The first station is 1.6 mm INSIDE the skin, not on it. A bead whose root
# section is exactly coincident with the panel it is fused to used to be fine;
# with a crease running through both surfaces the union comes back `is_valid`
# with a poisoned face, and it is the NEXT cut (the sill) that dies. Starting
# the bead under the skin makes it a genuine overlap and the fuse robust.
#          x        grow
_BEAD = (
    (-3400.0, -1.6),
    (-3424.0, 1.4),
    (-3438.0, 3.6),
    (-3448.0, 4.2),
    (-3454.0, 2.0),
    (-3459.0, -11.0),
)


def _exit_bead():
    """The rolled lip round the hot-air exit: radius `spec.TIP_ROLL_R`.

    Built as an outer bulge minus a straight bore rather than filleted — 3D
    fillets after booleans are the one operation that can take OCC down
    uncatchably, so every radius on this part is lofted, never filleted.
    """
    xs = [r[0] for r in _BEAD]
    outer = lib.body_loft(
        [lib.section_face(x, _sec_pts(x, inset=-g)) for x, g in _BEAD]
    )
    xi = [xs[0] + 6.0] + xs[1:] + [-3470.0]
    inner = lib.body_loft(
        [lib.section_face(x, _sec_pts(x, inset=spec.TIP_ROLL_R + 6.0)) for x in xi]
    )
    return outer - inner


# ---------------------------------------------------------------- louvres

_LV_N = 6
_LV_X0 = -2540.0
_LV_ROOT_CHORD = 66.0
_LV_ROOT_GAP = 22.0
_LV_TWIST0 = 6.5

# `lib.section_plane()`'s twist used to YAW the section instead of pitching it,
# so this bank was silently flat-and-swept and the incidence numbers were
# meaningless. Now that twist is a true pitch about the span axis, a slat's
# trailing edge really does lift `chord * sin(twist)` off its leading edge:
# at the old 12 -> 21.5 deg the gills stood 16-20 mm proud of a 5 mm-thick
# slat and read as a row of fins. 6.5 -> 13.5 deg puts them 6-9 mm proud on a
# 45 deg shoulder, which is a gill, and the rise still grows down the bank.


def _louvre_plan():
    """Rhythmic gill bank: chord, gap and incidence all progress smoothly."""
    chords = spec.cascade_chords(_LV_ROOT_CHORD, _LV_N, 0.93)
    gaps = spec.cascade_gaps(_LV_ROOT_GAP, _LV_N, spec.GAP_RATIO)
    plan, x_le, twist, d = [], _LV_X0, _LV_TWIST0, 1.00
    for i in range(_LV_N):
        plan.append({"x": x_le, "chord": chords[i], "twist": twist})
        if i < _LV_N - 1:
            x_le -= chords[i] + gaps[i]
            twist += d
            d += 0.20
    return plan


_LV_U0, _LV_U1 = 0.36, 0.66  # where on the deck the bank sits, in deck-law u


def _lv_span(x: float):
    """Inboard / outboard end of a gill, stated in the DECK LAW's own u.

    A fraction of `y_cr` is the wrong measure now: the flank below u = 0.3 is
    60-plus degrees, so a bank pinned at 0.56-0.90 of the half width climbed
    190 mm of z across its own span and read as six vertical fins. u = 0.36 to
    0.66 is the shoulder — the part of the section that is turning over — so a
    pitched slat's trailing edge actually lifts OFF the skin instead of sliding
    along it, and the bank stays a bank.
    """
    y_cr = crease(x)[0]
    span = y_cr - _ridge_w(x)
    return y_cr - _LV_U1 * span, y_cr - _LV_U0 * span


def _slab_face(x: float, y0: float, y1: float, up: float, down: float):
    """A deck-following slab section, closed with a ROUNDED NOSE at each end.

    `lib.section_face` interpolates a periodic spline through the points. Asked
    to U-turn 180 degrees between the last top sample and the first bottom one
    — 47 mm apart, with nothing in between — it overshoots hard, and on the
    steep new flank that overshoot loops the outline back through itself. The
    face still builds; the cutter it is lofted into then silently kills the
    boolean it is used in, several operations downstream. One point per end,
    half way down the slab and a nose-radius outboard, gives the spline
    somewhere to turn and makes the slot ends round instead of a square gash.
    """
    n = 8
    ys = [spec.lerp(y0, y1, k / n) for k in range(n + 1)]
    nose = 0.22 * (up + down)
    mid = 0.5 * (up - down)
    top = [(y, surf_z(x, y) + up) for y in ys]
    bot = [(y, surf_z(x, y) - down) for y in reversed(ys)]
    end_hi = (y1 + nose, surf_z(x, y1) + mid)
    end_lo = (y0 - nose, surf_z(x, y0) + mid)
    return lib.section_face(x, top + [end_hi] + bot + [end_lo])


@lru_cache(maxsize=1)
def _louvres():
    """(slats, cutters) for BOTH flanks — raised gills over open slots."""
    slats, cutters = [], []
    for p in _louvre_plan():
        x_le, chord, twist = p["x"], p["chord"], p["twist"]
        y0, y1 = _lv_span(x_le)
        ym = 0.5 * (y0 + y1)
        st = []
        for y, k in ((y0, 0.0), (ym, 0.5), (y1, 1.0)):
            st.append(
                {
                    "le": (x_le, y, surf_z(x_le, y) - 5.0),
                    "chord": chord * (1.0 - 0.12 * k),
                    "twist": twist,
                    "thickness": 0.075,
                    "camber": 0.050,
                    "te": spec.TE_THICKNESS,
                }
            )
        slat = lib.wing_element(st)
        cut = lib.body_loft(
            [
                _slab_face(x_le - 0.52 * chord, y0 + 9.0, y1 - 9.0, 9.0, 38.0),
                _slab_face(x_le - 1.22 * chord, y0 + 9.0, y1 - 9.0, 9.0, 38.0),
            ],
            ruled=True,
        )
        slats += [slat, lib.mirror_y(slat)]
        cutters += [cut, lib.mirror_y(cut)]
    return slats, cutters


# ---------------------------------------------------------------- aerial fin

_FIN_X0, _FIN_X1 = -2700.0, -3444.0
_FIN_H = 122.0
_FIN_T = 26.0
_FIN_N = 17


def _fin_u(x: float) -> float:
    return min(max((_FIN_X0 - x) / (_FIN_X0 - _FIN_X1), 0.0), 1.0)


def _fin_h(x: float) -> float:
    u = _fin_u(x)
    h = 16.0 + (_FIN_H - 16.0) * spec.smoothstep(min(u / 0.52, 1.0))
    return h * (1.0 - 0.16 * spec.smoothstep((u - 0.82) / 0.18))


def _fin_t(x: float) -> float:
    u = _fin_u(x)
    return 3.2 + (_FIN_T - 3.2) * math.sin(math.pi * u**0.5) ** 1.15


def _fin_pts(x: float):
    """Closed section of the fin at station x: a blade lens ON THE RIDGE.

    Seated on `apex_z` rather than the deck crown, so the fin grows straight
    out of the spine crest instead of being swallowed 26 mm into it.
    """
    zb = apex_z(x)
    hw = 0.5 * _fin_t(x)
    half = _super_arc(hw, 26.0, 6.0, -90.0, 0.0, 5, cz=zb)[:-1]
    half += _super_arc(hw, _fin_h(x), 2.55, 0.0, 90.0, 11, cz=zb)
    return half + [(-y, z) for (y, z) in reversed(half[1:-1])]


def _aerial_fin():
    xs = [spec.lerp(_FIN_X0, _FIN_X1, k / (_FIN_N - 1)) for k in range(_FIN_N)]
    outs = [_fin_pts(x) for x in xs]
    return _bounded(
        lib.body_loft([lib.section_face(x, o) for x, o in zip(xs, outs)]),
        outs,
        xs,
        14.0,
        "aerial fin",
    )


# ---------------------------------------------------------------- furniture


def _exit_liner():
    """Matte inner duct seen through the hot-air exit — depth, not a hole."""
    xo = (-3150.0, -3240.0, -3330.0, -3410.0, -3452.0)
    xi = (-3130.0, -3240.0, -3330.0, -3410.0, -3470.0)
    outer = lib.body_loft(
        [lib.section_face(x, _sec_pts(x, inset=_wall(x) + 9.0)) for x in xo]
    )
    inner = lib.body_loft(
        [lib.section_face(x, _sec_pts(x, inset=_wall(x) + 14.5)) for x in xi]
    )
    return (outer - inner) - _sill_cutter()


def _sill_normal(x: float):
    """Outward normal of the skirt at the sill.

    The skirt is no longer vertical — it leans in under the crease — so the
    normal has to lean with it or every Dzus head on the band sits skew.
    """
    d = 40.0
    dy = (crease(x - d)[0] - crease(x + d)[0]) / (2.0 * d)
    v = lib.Vector(-dy, _drop(x), -0.75 * _undercut(x))
    return v.normalized()


def _sill_pt(x: float):
    """(y, z) of the panel's free lower edge — inboard of the crease."""
    return crease(x)[0] - _undercut(x), sill_z(x)


_FLANGE_X0, _FLANGE_X1 = -1780.0, -3380.0


def _flange_rail():
    """The shut line against the sidepod panels, built as a real STEP.

    The cover's own free edge is a `_wall()`-thick carbon lip at the sill. This
    band is the mating flange BEHIND it: set `spec.PANEL_GAP` inboard and a
    little lower, so from outside you read skin -> crease -> undercut skirt ->
    9 mm of exposed carbon edge -> a 3 mm shadow gap -> exposed weave. That is
    a panel break, not a fading highlight.
    """
    n = 15
    pts, chords = [], []
    for k in range(n):
        x = spec.lerp(_FLANGE_X0, _FLANGE_X1, k / (n - 1))
        y_si, z_si = _sill_pt(x)
        chord = spec.lerp(17.0, 11.0, k / (n - 1))
        # `blade_face` seats its section on the QUARTER chord and the chord
        # runs up +Z here, so the band spans z - 0.25c .. z + 0.75c. Hanging it
        # off 0.75c below the sill lands its top edge exactly on the sill line
        # instead of poking 7 mm up through the cover's own skirt.
        pts.append(
            (x, y_si - spec.PANEL_GAP - 0.20 * chord, z_si - 0.75 * chord)
        )
        chords.append(chord)
    left = lib.blade_path(pts, chords, thickness_ratio=0.40)
    return left, lib.mirror_y(left)


def _dzus_row():
    """Rhythmic quarter-turn fasteners: sill flange + airbox aperture flange."""
    heads = []
    n = 9
    for k in range(n):
        x = spec.lerp(-1850.0, -3320.0, spec.smoothstep(k / (n - 1)) * 0.5 + k / (n - 1) * 0.5)
        y_si, z_si = _sill_pt(x)
        nrm = _sill_normal(x)
        c = (x, y_si + 0.46 * _undercut(x), z_si + 0.42 * _drop(x))
        h = _dzus(c, nrm, r=8.0, sink=1.4, proud=2.4)
        heads += [h, lib.mirror_y(h)]
    for k in range(4):
        x = spec.lerp(-1738.0, -1880.0, k / 3.0)
        y = _airbox_half_w(x) + 22.0
        z = surf_z(x, y)
        nz = surf_z(x, y + 12.0) - surf_z(x, y - 12.0)
        nrm = lib.Vector(0.0, -nz / 24.0, 1.0).normalized()
        h = _dzus((x, y, z), nrm, r=9.0)
        heads += [h, lib.mirror_y(h)]
    return _fuse(heads[0], heads[1:])


# --------------------------------------------------- airbox aperture flange

_AP_STATIONS = (COVER_X0, -1745.0, -1800.0, -1860.0, -1930.0, -2020.0, -2120.0)
_AP_PROUD = 3.2  # how far the flange stands off the skin
_AP_WIDTH = 14.0  # how far outboard of the panel gap it reaches


@lru_cache(maxsize=1)
def _aperture_flange():
    """A raised carbon flange ringing the airbox aperture.

    A hole cut in a shell is a hole; a JOINT is a hole with a landing round it.
    This is the cover's own skin lofted 3.2 mm proud, kept only where a collar
    round the airbox reaches the outer surface — so the band follows the
    aperture exactly, dies out on its own where the airbox sinks below the
    deck, and puts a lit step and a `spec.PANEL_GAP` shadow on the joint.
    """
    skin = lib.body_loft([lib.section_face(x, _sec_pts(x)) for x in _AP_STATIONS])
    proud = lib.body_loft(
        [lib.section_face(x, _sec_pts(x, inset=-_AP_PROUD)) for x in _AP_STATIONS]
    )
    collar = lib.body_loft(
        [
            lib.section_face(x, _ab_pts(x, spec.PANEL_GAP + _AP_WIDTH))
            for x in _AB_STATIONS
        ]
    )
    band = lib.repair(proud & collar)
    for tool in (skin, _airbox_envelope()):
        if not lib.is_valid_shape(band):
            return None  # `lib.group` drops it; a missing trim strip is not
        band = lib.cut(band, tool)  # worth taking the whole panel down with it
    return band if lib.is_valid_shape(band) else None


# ---------------------------------------------------------------- assembly


@lru_cache(maxsize=1)
def _cover_shell():
    outs = [_sec_pts(x) for x in _STATIONS]
    outer = _bounded(
        lib.body_loft([lib.section_face(x, o) for x, o in zip(_STATIONS, outs)]),
        outs,
        _STATIONS,
        26.0,
        "engine cover skin",
    )
    cav = [_sec_pts(x, inset=_wall(x)) for x in _CAV_STATIONS]
    cavity = lib.body_loft(
        [lib.section_face(x, o) for x, o in zip(_CAV_STATIONS, cav)]
    )
    # ORDER MATTERS. Every SUBTRACTION runs first and the one fuse runs last,
    # because a cut through a creased loft routinely leaves one out-of-
    # tolerance trim face and the NEXT boolean against that body is the one
    # that returns a null shape — the traceback then lands nowhere near the
    # operation that actually broke it. `lib.cut` heals between the big steps,
    # and the bead is fused at the end so that if the union ever does fail the
    # panel still ships without its lip instead of taking the build down.
    sill = _sill_cutter()
    shell = lib.cut(outer, cavity)
    shell = lib.cut(shell, sill)
    shell = lib.cut(shell, _airbox_envelope())
    # all twelve slots in ONE cut: twelve sequential booleans give OCC twelve
    # chances to leave a bad face behind, and only the last one reports it
    shell = lib.repair(shell - list(_louvres()[1]))
    fused = lib.fuse_all(shell, [_exit_bead() - sill])
    return fused if lib.is_valid_shape(fused) else shell


def build_engine_cover():
    slats = _louvres()[0]
    rail_l, rail_r = _flange_rail()
    kids = [
        lib.styled(_cover_shell(), "cover_panel", spec.CARBON_GLOSS),
        lib.styled(_aerial_fin(), "aerial_fin", spec.CARBON_GLOSS),
        lib.styled(_exit_liner(), "exit_duct_liner", spec.CARBON_MATTE),
        lib.styled(_aperture_flange(), "airbox_aperture_flange", spec.CARBON_WEAVE),
        lib.styled(rail_l, "cover_flange:left", spec.CARBON_WEAVE),
        lib.styled(rail_r, "cover_flange:right", spec.CARBON_WEAVE),
        lib.styled(_dzus_row(), "cover_dzus", spec.STEEL),
    ]
    for i, s in enumerate(slats):
        side = "left" if i % 2 == 0 else "right"
        kids.append(
            lib.styled(s, f"cover_louvre:{side}:{i // 2 + 1}", spec.CARBON_MATTE)
        )
    return lib.group("engine_cover", kids)


# ==========================================================================
# 2. AIRBOX — the intake above the driver's head
#
# `spec.AIRBOX_MOUTH_X` is the forwardmost point of the ROLLED LIP, not a
# knife edge: the outer skin curls through `spec.TIP_ROLL_R` from the mouth
# plane at x = -1629 to the rim at x = -1620, and the throat behind it flares
# out again into a bell, so the aperture reads as a thick rolled mouth with a
# real duct behind it rather than a hole punched in a surface.
#
# The duct sweeps back and down, narrowing, and hands its exit to the power
# unit's compressor trunk, whose published hardpoint is (-2044, 0, 700) with
# r = 43. The exit ring at x = -2060 is 150 x 112 mm about z = 699, so the
# trunk plugs into it with ~10 mm clearance the whole way round.
# ==========================================================================

AIRBOX_X0 = spec.AIRBOX_MOUTH_X  # -1620, the lip rim
_MOUTH_X = AIRBOX_X0 - spec.TIP_ROLL_R  # -1629, the mouth plane
AIRBOX_X1 = -2060.0  # duct exit into the plenum trunk

#           x       hw    z_top   z_bot   tri   n_top  n_bot
_AIRBOX = (
    (_MOUTH_X, 122.0, 916.0, 784.0, 0.52, 2.45, 2.55),
    (-1700.0, 118.0, 896.0, 762.0, 0.46, 2.45, 2.60),
    (-1800.0, 110.0, 860.0, 722.0, 0.36, 2.42, 2.62),
    (-1900.0, 99.0, 820.0, 688.0, 0.26, 2.40, 2.60),
    (-2000.0, 89.0, 786.0, 654.0, 0.15, 2.38, 2.55),
    (AIRBOX_X1, 84.0, 766.0, 632.0, 0.08, 2.35, 2.50),
)

_AB_STATIONS = (
    _MOUTH_X, -1660.0, -1700.0, -1745.0, -1800.0, -1850.0,
    -1900.0, -1950.0, -2000.0, -2032.0, AIRBOX_X1,
)

# Bore inset from the outer skin — i.e. the local wall thickness.
#
# THE MOUTH IS A HARD EDGE, NOT A ROLL. The lip used to curl through the full
# `spec.TIP_ROLL_R` (9 mm) with an 18 mm-thick wall behind it, which is a soft
# opening: the outer surface just wraps round into the duct with no line on it
# anywhere. Now the outer skin runs almost flat to the rim plane (see
# `_MOUTH_LIP`, 3 mm of curl) and the bore sits 7.5 mm inside it, so the rim
# is a 4.5 mm annular FACE with a crisp corner top and bottom — a punched
# intake with machined edges. 4.5 mm is `spec.SKIN_T` plus the accent ring's
# seat, so the edge still reads as carbon and not as a knife.
#              x      inset
_AB_WALL = (
    (-1612.0, 7.5),
    (-1621.0, 7.5),
    (-1626.0, 8.4),
    (_MOUTH_X, 9.2),
    (-1650.0, 10.5),
    (-1680.0, 10.0),
    (-1720.0, 9.5),
    (-1790.0, 9.0),
    (-1860.0, 8.7),
    (-1930.0, 8.5),
    (-2000.0, 8.2),
    (-2075.0, 8.0),
)


def _ab_wall(x: float) -> float:
    return _blend(_AB_WALL, x)[0]


def _airbox_half_w(x: float) -> float:
    return _blend(_AIRBOX, x)[0]


def _ab_pts(x: float, grow: float = 0.0):
    """Closed outer outline of the duct at station x.

    A superellipse whose upper half is narrowed by `tri`, which turns the
    ellipse into the rounded triangle the mouth needs and relaxes back into an
    oval by the time the duct reaches the plenum.
    """
    hw, z_top, z_bot, tri, n_top, n_bot = _blend(_AIRBOX, x)
    cz = 0.5 * (z_top + z_bot)
    hh = 0.5 * (z_top - z_bot)
    half = _super_arc(hw, hh, n_bot, -90.0, 0.0, 8, cz=cz)[:-1]
    half += _super_arc(hw, hh, n_top, 0.0, 90.0, 14, cz=cz)
    half = [(y * (1.0 - tri * max((z - cz) / hh, 0.0) ** 1.25), z) for y, z in half]
    loop = half + [(-y, z) for (y, z) in reversed(half[1:-1])]
    return loop if grow == 0.0 else _offset(loop, -grow)


def _ab_face(x: float, inset: float = 0.0):
    return lib.section_face(x, _offset(_ab_pts(x), inset))


# ---------------------------------------------------------------- side inlets
#
# Two kidney scoops flanking the main mouth: same rolled-lip family, one
# quarter the size, dying back into the airbox flank they grew out of.

#            x      cy      cz     hw    hh
_LOBE = (
    (-1634.0, 132.0, 868.0, 30.0, 21.0),
    (-1668.0, 126.0, 858.0, 30.0, 21.0),
    (-1700.0, 116.0, 846.0, 28.0, 20.0),
    (-1746.0, 96.0, 828.0, 24.0, 17.0),
)


def _lobe_pts(x: float, grow: float = 0.0):
    cy, cz, hw, hh = _blend(_LOBE, x)
    half = _super_arc(hw, hh, 2.3, -90.0, 90.0, 15)
    loop = half + [(-y, z) for (y, z) in reversed(half[1:-1])]
    loop = [(y + cy, z + cz) for y, z in loop]
    return loop if grow == 0.0 else _offset(loop, -grow)


# Same hard-edged treatment as the main mouth, one quarter the size.
_LOBE_LIP = ((-1626.0, -2.4), (-1627.6, -1.0), (-1630.0, -0.25), (-1634.0, 0.0))
_LOBE_X = (-1634.0, -1660.0, -1690.0, -1720.0, -1746.0)


def _lobe_solid():
    xs = [r[0] for r in _LOBE_LIP] + list(_LOBE_X[1:])
    grows = [r[1] for r in _LOBE_LIP] + [0.0] * (len(_LOBE_X) - 1)
    return lib.body_loft(
        [lib.section_face(x, _lobe_pts(x, g)) for x, g in zip(xs, grows)]
    )


def _lobe_bore():
    """The scoop's throat — it runs inboard and dies into the main duct."""
    xs = (-1618.0, -1634.0, -1668.0, -1700.0, -1746.0, -1772.0)
    ins = (5.6, 5.6, 5.8, 6.0, 6.2, 6.5)
    faces = []
    for x, t in zip(xs, ins):
        pts = _offset(_lobe_pts(max(x, -1746.0)), t)
        if x < -1746.0:
            pts = [(y - 26.0, z - 14.0) for y, z in pts]
        faces.append(lib.section_face(x, pts))
    return lib.body_loft(faces)


# ---------------------------------------------------------------- T-cam pod

#           x      hw    h
_POD = (
    (-1660.0, 20.0, 24.0),
    (-1674.0, 24.0, 30.0),
    (-1706.0, 26.0, 34.0),
    (-1744.0, 22.0, 29.0),
    (-1780.0, 15.0, 21.0),
    (-1806.0, 5.0, 8.0),
)


def _crown_z(x: float) -> float:
    return _blend(_AIRBOX, x)[1]


def _pod_pts(x: float):
    hw, h = _blend(_POD, x)
    zb = _crown_z(x) - 12.0
    half = _super_arc(hw, 14.0, 5.0, -90.0, 0.0, 5, cz=zb)[:-1]
    half += _super_arc(hw, h, 2.5, 0.0, 90.0, 11, cz=zb)
    return half + [(-y, z) for (y, z) in reversed(half[1:-1])]


def _tcam():
    """Dark lens + machined bezel on the pod's front face."""
    zc = _crown_z(-1660.0) - 12.0 + 10.0
    axis = lib.Vector(1, 0, 0)
    lens = lib.loft_solid(
        [
            _disc_face((-1662.0, 0.0, zc), axis, 10.0),
            _disc_face((-1653.5, 0.0, zc), axis, 9.0),
        ],
        ruled=True,
    )
    ring_o = lib.loft_solid(
        [
            _disc_face((-1663.0, 0.0, zc), axis, 14.0),
            _disc_face((-1655.0, 0.0, zc), axis, 13.2),
        ],
        ruled=True,
    )
    ring_i = lib.loft_solid(
        [
            _disc_face((-1665.0, 0.0, zc), axis, 10.2),
            _disc_face((-1652.0, 0.0, zc), axis, 10.2),
        ],
        ruled=True,
    )
    return lens, ring_o - ring_i


# ---------------------------------------------------------------- assembly

_MOUTH_LIP = (
    (AIRBOX_X0, -3.0),  # -1620: the rim plane, 3 mm inside the mouth outline
    (-1622.0, -1.30),
    (-1625.0, -0.35),
    (_MOUTH_X, 0.0),  # -1629: the mouth plane, full outline
    (-1638.0, 0.0),
)


def _mouth_lip():
    return lib.body_loft(
        [lib.section_face(x, _ab_pts(x, g)) for x, g in _MOUTH_LIP]
    )


def _ab_throat():
    xs = (
        -1612.0, -1621.0, _MOUTH_X, -1650.0, -1680.0, -1720.0,
        -1790.0, -1860.0, -1930.0, -2000.0, -2075.0,
    )
    return lib.body_loft([_ab_face(x, _ab_wall(x)) for x in xs])


def _pod_solid():
    return lib.body_loft([lib.section_face(r[0], _pod_pts(r[0])) for r in _POD])


def _duct_liner():
    """Matte inner duct — what you actually see through the mouth."""
    xo = (-1636.0, -1690.0, -1760.0, -1850.0, -1940.0, -2030.0)
    xi = (-1626.0, -1690.0, -1760.0, -1850.0, -1940.0, -2070.0)
    outer = lib.body_loft([_ab_face(x, _ab_wall(x) + 1.6) for x in xo])
    inner = lib.body_loft([_ab_face(x, _ab_wall(x) + 5.6) for x in xi])
    return outer - inner


def _mouth_stripe():
    """THE accent: one 2.6 mm vermillion ring seated ON the rim face.

    The rim face runs from 3.0 (outer lip edge) to 7.5 (bore) inside the mouth
    outline, so the ring sits at 4.0 -> 6.6 with a hairline of carbon either
    side of it and stands 1.5 mm proud of the rim.
    """
    o = _offset(_ab_pts(_MOUTH_X), 4.0)
    i = _offset(_ab_pts(_MOUTH_X), 6.6)
    ring_o = lib.body_loft(
        [lib.section_face(-1622.5, o), lib.section_face(-1618.5, o)], ruled=True
    )
    ring_i = lib.body_loft(
        [lib.section_face(-1624.0, i), lib.section_face(-1616.0, i)], ruled=True
    )
    return ring_o - ring_i


def _ab_collar():
    """Exposed-weave band where the airbox passes through the cover panel."""
    outer = lib.body_loft(
        [lib.section_face(x, _ab_pts(x, 1.5)) for x in (-1686.0, -1716.0)],
        ruled=True,
    )
    inner = lib.body_loft(
        [_ab_face(x, 7.0) for x in (-1680.0, -1722.0)], ruled=True
    )
    return outer - inner


@lru_cache(maxsize=1)
def _airbox_envelope():
    """The airbox grown by `spec.PANEL_GAP` — the cover's aperture cutter."""
    body = lib.body_loft(
        [lib.section_face(x, _ab_pts(x, spec.PANEL_GAP)) for x in _AB_STATIONS]
    )
    lobe = lib.body_loft(
        [lib.section_face(x, _lobe_pts(x, spec.PANEL_GAP)) for x in _LOBE_X]
    )
    return _fuse(body, [lobe, lib.mirror_y(lobe)])


@lru_cache(maxsize=1)
def _airbox_shell():
    outs = [_ab_pts(x) for x in _AB_STATIONS]
    body = _bounded(
        lib.body_loft(
            [lib.section_face(x, o) for x, o in zip(_AB_STATIONS, outs)]
        ),
        outs,
        _AB_STATIONS,
        20.0,
        "airbox duct",
    )
    lobe = _lobe_solid()
    shell = _fuse(body, [_mouth_lip(), lobe, lib.mirror_y(lobe), _pod_solid()])
    shell = shell - _ab_throat()
    bore = _lobe_bore()
    shell = shell - bore
    shell = shell - lib.mirror_y(bore)
    return shell


def build_airbox():
    lens, bezel = _tcam()
    return lib.group(
        "airbox",
        [
            lib.styled(_airbox_shell(), "airbox_duct", spec.CARBON_GLOSS),
            lib.styled(_duct_liner(), "airbox_duct_liner", spec.CARBON_MATTE),
            lib.styled(_ab_collar(), "airbox_flange", spec.CARBON_WEAVE),
            lib.styled(_mouth_stripe(), "airbox_lip_stripe", spec.ACCENT),
            lib.styled(lens, "tcam_lens", spec.GLASS),
            lib.styled(bezel, "tcam_bezel", spec.ANODIZED),
        ],
    )
