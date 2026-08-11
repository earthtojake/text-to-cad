"""Sidepod bodywork panels, inlets, undercut, cooling louvres; radiators.

THE SECTION LAW
---------------
Every sidepod station is one closed outline built from five named points and
four cubic arcs between them. Written outboard-to-inboard as a front-view
sketch, in (y, z):

    IWT  inner wall top      the panel's inboard edge, against the tub
    CR   THE CREASE          `spec.shoulder_at(x)` — the car's feature line
    WD   widest point        the flank's maximum half-width
    LP   undercut lip        the sharp lower edge of the flank  (LOWEST point)
    IWB  inner wall bottom    inboard end of the scooped belly

    IWT --gutter--> CR --deck--> WD --flank--> LP --undercut--> IWB --wall--> IWT

CR is a real hard knuckle because the deck leaves it crowned while the gutter
falls away inboard, and it is sampled straight off `spec.shoulder_at()` so the
line is continuous with the monocoque forward and the engine cover aft. Its
HEIGHT also sets the height of the widest point: WD is pinned a few mm under
CR, which is what puts the pod's maximum half-width up at z = 380-400 instead
of halfway down the flank.

THE UNDERCUT is the whole point of the part. Read WD -> LP as a wing section
lying on its side: convex crowned shoulder above the crease, a ~115 deg fold at
WD, then a strongly CONCAVE sweep that leaves the crease running almost
horizontally INBOARD — a genuine overhang — before turning down to the lip.
`_BOW` sets how far that sweep is sucked in past the WD->LP chord (up to 42 mm)
and `_flank_ctrl()` builds the two Bezier handles off the chord normal so the
tuck deepens and shallows with the plan shape instead of being keyframed twice.

The numbers that make it read: between x = -1050 and x = -2400 the lip is
tucked 150-220 mm INBOARD of the widest point and climbs 206 -> 330 mm while
the crease stays out at y = 728-750 and up at z = 357-395. Under a floor that
runs out to y = 900 that overhang is a 200 mm deep slot of daylight, which is
exactly what you are looking at from a low front three-quarter.

The panel is a genuine SHELL: the outer loft minus a cavity loft inset along
the section normal. So the inlet is a real letterbox opening with a carbon lip
all the way round, the duct throat runs inward and rearward, the rear exit is
open, and the louvre slots cut through into the same volume the radiators sit
in. Nothing is faked with a painted-on hole.
"""

from __future__ import annotations

import math
from functools import lru_cache

from build123d import Pos, Box

from . import lib, spec

# ==========================================================================
# SECTION LAW — keyframed stations, smoothstep-blended
# ==========================================================================

_X_NOSE = -820.0  # panel front face: the inlet mouth plane
_X_TAIL = -2740.0  # panel trailing edge, rolled inboard at the gearbox

# The lip column is the one that carries the design. Old table ran the lip
# 28-32 mm inboard of the widest point — a flank that fell straight to the
# floor and an undercut nobody could see. It now runs 150-220 mm inboard
# through the whole mid-pod, deepest at x = -1700.
#
# x,       y_in,  y_wide, z_wide, y_lip, z_lip, z_ib,  crown
_KEYS = (
    (-820.0, 404.0, 598.0, 330.0, 542.0, 228.0, 288.0, 44.0),
    (-1020.0, 406.0, 676.0, 340.0, 556.0, 212.0, 292.0, 54.0),
    (-1300.0, 408.0, 728.0, 357.0, 562.0, 206.0, 300.0, 62.0),
    (-1620.0, 410.0, 748.0, 381.0, 536.0, 212.0, 322.0, 68.0),
    (-1780.0, 412.0, 750.0, 388.0, 528.0, 224.0, 334.0, 68.0),
    (-2000.0, 412.0, 728.0, 390.0, 530.0, 252.0, 342.0, 64.0),
    (-2250.0, 402.0, 646.0, 393.0, 468.0, 296.0, 366.0, 54.0),
    (-2450.0, 372.0, 552.0, 395.0, 424.0, 330.0, 372.0, 42.0),
    (-2620.0, 346.0, 468.0, 396.0, 390.0, 350.0, 376.0, 32.0),
    (-2740.0, 334.0, 426.0, 396.0, 380.0, 360.0, 378.0, 26.0),
)

# Station stack the outer skin is lofted through. The count is load-bearing:
# OCC's smooth ThruSections overshoots its own sections when they are sparse
# (13 stations put the skin 175 mm outside its own outline) and goes unstable
# when they are dense (33 stations blew the solid up to y = 1432). 25 evenly
# spaced stations reproduce the section envelope to ~3 mm. `_bounded()` guards
# the result so a bad loft is a build error, never a shipped panel.
_N_STATIONS = 25
_STATIONS = tuple(
    _X_NOSE + (_X_TAIL - _X_NOSE) * k / (_N_STATIONS - 1) for k in range(_N_STATIONS)
)

_GUTTER_MAX = 28.0  # deepest the gutter ever falls below the crease


def _key(x: float):
    """Blend the keyframe table at station x."""
    ks = _KEYS
    if x >= ks[0][0]:
        return ks[0][1:]
    if x <= ks[-1][0]:
        return ks[-1][1:]
    for i in range(len(ks) - 1):
        x0, x1 = ks[i][0], ks[i + 1][0]
        if x1 <= x <= x0:
            t = spec.smoothstep((x0 - x) / (x0 - x1))
            return tuple(
                spec.lerp(a, b, t) for a, b in zip(ks[i][1:], ks[i + 1][1:])
            )
    return ks[-1][1:]


@lru_cache(maxsize=512)
def _sec(x: float):
    """The five named section points (plus crown) at station x."""
    y_in, y_wide, z_wide, y_lip, z_lip, z_ib, crown = _key(x)
    y_cr, z_cr = spec.shoulder_at(x)
    gutter = min(_GUTTER_MAX, 0.42 * max(y_cr - y_in, 0.0))
    return {
        "IWT": (y_in, z_cr - gutter),
        "CR": (y_cr, z_cr),
        "WD": (y_wide, z_wide),
        "LP": (y_lip, z_lip),
        "IWB": (y_in + 4.0, z_ib),
        "crown": crown,
    }


def _cbez(p0, p1, o1, o2, n: int, include_end: bool = False):
    """Cubic Bezier from p0 to p1; o1/o2 offset the two control points."""
    c1 = (p0[0] + (p1[0] - p0[0]) / 3.0 + o1[0], p0[1] + (p1[1] - p0[1]) / 3.0 + o1[1])
    c2 = (
        p0[0] + 2.0 * (p1[0] - p0[0]) / 3.0 + o2[0],
        p0[1] + 2.0 * (p1[1] - p0[1]) / 3.0 + o2[1],
    )
    out = []
    last = n if include_end else n - 1
    for k in range(last + 1):
        t = k / n
        u = 1.0 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p1[0],
                u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p1[1],
            )
        )
    return out



# How hard the flank is sucked in past the straight WD -> LP chord, as a
# fraction of the tuck. The two handles are pulled along the chord's inboard-up
# normal at 1.0x and 1.6x of it: the first makes the surface leave the crease
# almost horizontally (the overhang), the second holds the concavity all the
# way down to the lip instead of letting it relax into a straight bevel.
_BOW_FRAC = 0.24
_BOW_MAX = 42.0
_BOW_MIN = 5.0


def _flank_ctrl(wd, lp):
    """Handle offsets for the concave undercut sweep WD -> LP."""
    dy, dz = lp[0] - wd[0], lp[1] - wd[1]
    L = math.hypot(dy, dz) or 1.0
    # unit normal of the chord pointing INBOARD and UP — into the body
    ny, nz = dz / L, -dy / L
    bow = min(max(_BOW_FRAC * abs(dy), _BOW_MIN), _BOW_MAX)
    return (ny * bow, nz * bow), (ny * 1.6 * bow, nz * 1.6 * bow)


def _deck_ctrl(x: float):
    """Control data for the top deck arc CR -> WD (crowned, y monotone)."""
    s = _sec(x)
    c = s["crown"]
    return s["CR"], s["WD"], (0.0, 0.62 * c), (0.0, 0.80 * c)


def _deck_z(x: float, y: float) -> float:
    """Height of the top deck at (x, y). y is linear in the Bezier parameter."""
    p0, p1, o1, o2 = _deck_ctrl(x)
    span = p1[0] - p0[0]
    t = 0.0 if abs(span) < 1e-9 else (y - p0[0]) / span
    t = min(max(t, 0.0), 1.0)
    c1z = p0[1] + (p1[1] - p0[1]) / 3.0 + o1[1]
    c2z = p0[1] + 2.0 * (p1[1] - p0[1]) / 3.0 + o2[1]
    u = 1.0 - t
    return u**3 * p0[1] + 3 * u * u * t * c1z + 3 * u * t * t * c2z + t**3 * p1[1]


# Dense per-segment sampling, then ONE uniform arc-length resample per station.
#
# This matters more than it looks. `Spline(..., periodic=True)` parameterises by
# chord length, and a loft matches its sections by parameter — so if the point
# density varies from station to station (and the segment lengths here change by
# 5x front to tail) the loft shrink-wraps over its own sections and the skin
# comes out crumpled. Resampling every station to the SAME uniform arc-length
# distribution, anchored on the inner wall top, makes the sections compatible and
# the surface comes out glassy.
_D_GUT, _D_DECK, _D_FLANK, _D_CUT, _D_WALL = 16, 40, 44, 34, 12
_N_SEC = 88  # points per lofted section, after resampling (~8 mm spacing)
# 88, not 64: the section now folds ~115 deg at the crease, and a periodic
# spline rounds a corner over roughly one point spacing. At 64 the crease came
# out as a 16 mm roll that read as a soft shoulder; at 88 it is a ~9 mm knuckle,
# which is a believable carbon edge radius and catches a hard highlight.


def _raw_outline(x: float):
    """Densely sampled (y, z) outline of the outer skin at station x — left."""
    s = _sec(x)
    iwt, cr, wd, lp, iwb = s["IWT"], s["CR"], s["WD"], s["LP"], s["IWB"]
    c = s["crown"]
    pts = []
    # gutter — a shallow trough so the crease reads as a knuckle, not a dome
    pts += _cbez(iwt, cr, (0.0, -5.0), (0.0, -2.5), _D_GUT)
    # top deck — a taut crowned shoulder that rolls over into the crease
    pts += _cbez(cr, wd, (0.0, 0.62 * c), (0.0, 0.80 * c), _D_DECK)
    # THE UNDERCUT — leaves the crease heading inboard, strongly concave
    f1, f2 = _flank_ctrl(wd, lp)
    pts += _cbez(wd, lp, f1, f2, _D_FLANK)
    # belly — bows UP into the body, so the underside is hollow from below
    scoop = 0.34 * max(iwb[1] - lp[1], 0.0) + 26.0
    pts += _cbez(lp, iwb, (0.0, scoop), (0.0, 0.86 * scoop), _D_CUT)
    # inner wall — slightly hollow
    pts += _cbez(iwb, iwt, (-3.0, 0.0), (-3.0, 0.0), _D_WALL)
    return pts


def _resample(pts, n: int = _N_SEC):
    """Uniform arc-length resample of a closed outline, anchored at pts[0]."""
    m = len(pts)
    seg = [
        math.hypot(pts[(i + 1) % m][0] - pts[i][0], pts[(i + 1) % m][1] - pts[i][1])
        for i in range(m)
    ]
    total = sum(seg)
    step = total / n
    out, idx, acc = [], 0, 0.0
    for k in range(n):
        target = k * step
        while idx < m - 1 and acc + seg[idx] < target:
            acc += seg[idx]
            idx += 1
        t = (target - acc) / max(seg[idx], 1e-9)
        a, b = pts[idx], pts[(idx + 1) % m]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


@lru_cache(maxsize=256)
def _outline(x: float):
    return _resample(_raw_outline(x))




def _inset(pts, thickness):
    """Offset a closed outline inward along its own normal by `thickness`."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % n]
        area += y0 * z1 - y1 * z0
    w = 1.0 if area > 0 else -1.0
    out = []
    for i in range(n):
        y, z = pts[i]
        ya, za = pts[(i - 1) % n]
        yb, zb = pts[(i + 1) % n]
        ty, tz = yb - ya, zb - za
        L = math.hypot(ty, tz) or 1.0
        ny, nz = -tz / L * w, ty / L * w
        t = thickness[i] if isinstance(thickness, (list, tuple)) else thickness
        out.append((y + ny * t, z + nz * t))
    return out


def _crosses(pts) -> bool:
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            r, s = pts[j], pts[(j + 1) % n]
            if ((side(r, s, p) > 0) != (side(r, s, q) > 0)) and (
                (side(p, q, r) > 0) != (side(p, q, s) > 0)
            ):
                return True
    return False


def _shrink(pts, t_mean: float):
    """Similarity shrink about the centroid — can never self-intersect."""
    cy = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)
    r = sum(math.hypot(p[0] - cy, p[1] - cz) for p in pts) / len(pts)
    k = max(0.05, 1.0 - t_mean / max(r, 1e-6))
    return [(cy + (p[0] - cy) * k, cz + (p[1] - cz) * k) for p in pts]


def _normals(pts):
    """Inward unit normals of a closed outline, one per point."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % n]
        area += y0 * z1 - y1 * z0
    w = 1.0 if area > 0 else -1.0
    out = []
    for i in range(n):
        ya, za = pts[(i - 1) % n]
        yb, zb = pts[(i + 1) % n]
        ty, tz = yb - ya, zb - za
        L = math.hypot(ty, tz) or 1.0
        out.append((-tz / L * w, ty / L * w))
    return out


def _ray_width(pts, i, normal, eps: float = 1e-6):
    """How far the section extends inward from point i along its own normal."""
    p = pts[i]
    dy, dz = normal
    n = len(pts)
    best = float("inf")
    for j in range(n):
        a = pts[j]
        b = pts[(j + 1) % n]
        ey, ez = b[0] - a[0], b[1] - a[1]
        den = dy * ez - dz * ey
        if abs(den) < 1e-12:
            continue
        wy, wz = a[0] - p[0], a[1] - p[1]
        s = (wy * ez - wz * ey) / den
        u = (wy * dz - wz * dy) / den
        if s > eps and -1e-9 <= u <= 1.0 + 1e-9:
            best = min(best, s)
    return best


def _cap_thickness(pts, thickness, frac: float = 0.42):
    """Clamp per-point wall thickness to a fraction of the local section width.

    A constant normal offset is what gives the inlet its even carbon lip, but
    where the section pinches — the acute undercut lip, the 20 mm wedge under
    the crease, the blade tail — a constant offset walks straight through the
    far wall. Capping each point at `frac` of the width the section actually
    has along that point's own normal keeps the offset inside by construction
    and only thins the wall exactly where there is no room for it.
    """
    n = len(pts)
    ns = _normals(pts)
    base = (
        list(thickness)
        if isinstance(thickness, (list, tuple))
        else [float(thickness)] * n
    )
    return [min(base[i], frac * _ray_width(pts, i, ns[i])) for i in range(n)]


def _safe_inset(pts, thickness):
    """Normal offset, capped to the local section width, then relaxed if needed.

    Blending toward a similarity shrink (what this used to do) is fine on a
    convex outline and wrong on this one: a similarity shrink of a CONCAVE
    section sits partly OUTSIDE it, so the duct loft poked back through the
    flank under the crease and the shell boolean opened a slit along the
    feature line. The capped normal offset stays inside by construction; the
    shrink is kept only as a last-ditch fallback.
    """
    capped = _cap_thickness(pts, thickness)
    for scale in (1.0, 0.82, 0.66, 0.5, 0.36, 0.24):
        off = _inset(pts, [t * scale for t in capped])
        if not _crosses(off):
            return off
    tm = (
        sum(thickness) / len(thickness)
        if isinstance(thickness, (list, tuple))
        else thickness
    )
    return _shrink(pts, tm)


def _wall_t(x: float, pts):
    """Per-point skin thickness at station x, never below spec.SKIN_T.

    The deck that carries the crease has body; the undercut and its lip thin
    down toward a blade, which is what makes the lower lip read as sharp.
    """
    s = _sec(x)
    h = max(s["CR"][1], s["WD"][1]) - s["LP"][1]
    wdt = s["WD"][0] - s["IWT"][0]
    base = min(max(min(h, wdt) * 0.105, spec.SKIN_T), 11.5)
    z_lo = min(p[1] for p in pts)
    z_hi = max(p[1] for p in pts)
    span = max(z_hi - z_lo, 1e-6)
    return [
        max(base * (0.56 + 0.44 * spec.smoothstep((p[1] - z_lo) / span)), spec.SKIN_T)
        for p in pts
    ]


# The duct does not run out of the back of the panel: the tail has to close to
# a thin blade. Instead the cavity walks inboard behind x = -2200 and breaks
# out through the panel's inner wall — the coke-bottle exit, dumping hot air at
# the gearbox exactly where a real car does.
_EXIT_X0 = -2200.0
_EXIT_X1 = -2540.0
_EXIT_DY = 104.0


def _exit_shift(x: float) -> float:
    if x >= _EXIT_X0:
        return 0.0
    t = spec.smoothstep((_EXIT_X0 - x) / (_EXIT_X0 - _EXIT_X1))
    return _EXIT_DY * t


# THE LETTERBOX. Insetting the whole section gives a crescent-shaped hole that
# reads as an open scoop, not a modern inlet. So near the nose the duct section
# is squeezed into a slot: every point is pulled in z toward the LOCAL middle of
# the section at its own y.
#
# A single global z-band (which is what this used to be) only works on a section
# that is tall at every y. The undercut made the outboard end of the section a
# thin wedge, so a global band put the slot's lower edge clean outside the skin
# below the crease. Clamping per-y instead keeps the slot strictly between the
# section's own upper and lower arcs at every station, so the mouth follows the
# pod's plan shape and keeps a real carbon lip all the way round. By `_MOUTH_X1`
# the duct has opened out to the full section and the throat runs rearward.
_MOUTH_X1 = -1120.0
_MOUTH_HALF_H = 34.0
_MOUTH_BIAS = 0.06  # slot sits slightly above the section's mid-line
_MOUTH_MARGIN = 0.12  # min lip, as a fraction of the local section height


def _z_cuts(poly, y: float):
    hits = []
    n = len(poly)
    for i in range(n):
        y0, z0 = poly[i]
        y1, z1 = poly[(i + 1) % n]
        if (y0 <= y < y1) or (y1 <= y < y0):
            hits.append(z0 + (z1 - z0) * (y - y0) / (y1 - y0))
    return hits


def _z_span(poly, y: float, eps: float = 0.05):
    """(z_low, z_high) of a closed (y, z) polygon on the vertical line at y.

    Probed either side of y, because the queries all land exactly ON vertices:
    a half-open edge test at a vertex returns one crossing on one side and
    three on the other, and a single degenerate answer there put a spike in the
    inlet slot that self-intersected the section.
    """
    hits = []
    for d in (-eps, eps):
        h = _z_cuts(poly, y + d)
        if len(h) >= 2:
            hits += h
    return (min(hits), max(hits)) if len(hits) >= 2 else None


def _letterbox(out, half_h: float):
    """Squeeze a closed section into a slot, per-y, so it stays inside itself."""
    res = []
    for y, z in out:
        span = _z_span(out, y)
        if span is None:  # the section's own y extremes: already degenerate
            res.append((y, z))
            continue
        zlo, zhi = span
        h_local = zhi - zlo
        mid = 0.5 * (zlo + zhi) + _MOUTH_BIAS * h_local
        h = min(half_h, (0.5 - _MOUTH_MARGIN) * h_local)
        lo = max(mid - h, zlo + _MOUTH_MARGIN * h_local)
        hi = min(mid + h, zhi - _MOUTH_MARGIN * h_local)
        if hi < lo:
            lo = hi = 0.5 * (zlo + zhi)
        res.append((y, min(max(z, lo), hi)))
    return res


@lru_cache(maxsize=256)
def _cavity_outline(x: float):
    skin = _outline(x)
    out = _resample(_safe_inset(skin, _wall_t(x, skin)))
    if x > _MOUTH_X1:
        slot = _resample(_letterbox(out, _MOUTH_HALF_H))
        t = spec.smoothstep((_X_NOSE - x) / (_X_NOSE - _MOUTH_X1))
        out = [
            (spec.lerp(a[0], b[0], t), spec.lerp(a[1], b[1], t))
            for a, b in zip(slot, out)
        ]
        if not _inside(out, skin):
            raise ValueError(f"inlet mouth at x={x:.0f} breaks through the skin")
    dy = _exit_shift(x)
    return out if dy == 0.0 else [(p[0] - dy, p[1]) for p in out]


# ==========================================================================
# THE PANEL
# ==========================================================================


def _bounded(solid, outlines, xs, tol: float, what: str):
    """Assert a loft actually stayed inside the envelope of its own sections.

    A smooth loft can bulge far outside the stations it was built from, and the
    result is still a "valid" solid — it just is not the shape that was drawn.
    Checking it is the difference between a glassy panel and a crumpled one.
    At 21 stations this skin lofted out to y = 1664; at 25 it lands within 3 mm.
    The tolerance is loose because `lib.bbox` bounds B-spline poles rather than
    the surface, so a healthy loft still reads a little proud.
    """
    lo, hi = lib.bbox(solid)
    ys = [p[0] for o in outlines for p in o]
    zs = [p[1] for o in outlines for p in o]
    want = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
    for i in range(3):
        if lo[i] < want[0][i] - tol or hi[i] > want[1][i] + tol:
            raise ValueError(
                f"{what} loft escaped its sections on axis {'xyz'[i]}: "
                f"got [{lo[i]:.0f},{hi[i]:.0f}] want [{want[0][i]:.0f},{want[1][i]:.0f}]"
            )
    return solid


def _skin_solid():
    outs = [_outline(x) for x in _STATIONS]
    faces = [lib.section_face(x, o) for x, o in zip(_STATIONS, outs)]
    return _bounded(lib.body_loft(faces), outs, _STATIONS, 22.0, "sidepod skin")


def _duct_solid(fn=_cavity_outline, front=8.0):
    """Loft of the inner volume, run past the mouth plane so it cuts through.

    It ends on the inboard breakout at `_EXIT_X1`, not at the panel's trailing
    edge, so the tail can still close to a thin blade.
    """
    xs = [_X_NOSE + front]
    outs = [fn(_X_NOSE)]
    for x in _STATIONS:
        if x > _EXIT_X1:
            xs.append(x)
            outs.append(fn(x))
    xs += [_EXIT_X1, _EXIT_X1 - 34.0]
    outs += [fn(_EXIT_X1), [(p[0] - 46.0, p[1]) for p in fn(_EXIT_X1)]]
    faces = [lib.section_face(x, o) for x, o in zip(xs, outs)]
    return _bounded(lib.body_loft(faces), outs, xs, 22.0, "sidepod duct")


# ---------------------------------------------------------------- louvres

_LOUVRE_N = 7
_LOUVRE_X0 = -1560.0
_LOUVRE_ROOT_CHORD = 58.0
_LOUVRE_ROOT_GAP = 18.0
# `lib.section_plane()` used to YAW a section instead of pitching it, so this
# 21 deg "incidence" was silently doing nothing. With the fix it became a real
# pitch and the bank stood up off the deck like a row of shark fins — 21 mm of
# trailing edge in the air on a 58 mm chord. A gill is a slot, not a wing: the
# slat now sits 8 mm INTO the deck and lifts its trailing edge back out to
# roughly flush, so what you see is the shadowed opening, not the blade.
_LOUVRE_BASE_TWIST = 9.0
_LOUVRE_SINK = 8.0


def _louvre_plan():
    """Rhythmic gill bank: chord, gap and incidence all progress smoothly."""
    chords = spec.cascade_chords(_LOUVRE_ROOT_CHORD, _LOUVRE_N, 0.93)
    gaps = spec.cascade_gaps(_LOUVRE_ROOT_GAP, _LOUVRE_N, spec.GAP_RATIO)
    twist, d = _LOUVRE_BASE_TWIST, 0.9
    plan, x_le = [], _LOUVRE_X0
    for i in range(_LOUVRE_N):
        plan.append({"x": x_le, "chord": chords[i], "twist": twist})
        if i < _LOUVRE_N - 1:
            x_le -= chords[i] + gaps[i]
            twist += d
            d += 0.15
    return plan


def _louvre_span(x: float):
    s = _sec(x)
    return s["CR"][0] + 26.0, s["WD"][0] - 62.0


def _deck_slab_face(x: float, y0: float, y1: float, up: float, down: float):
    """A deck-following slab section — constant depth below the top surface."""
    n = 7
    top = [
        (spec.lerp(y0, y1, k / n), _deck_z(x, spec.lerp(y0, y1, k / n)) + up)
        for k in range(n + 1)
    ]
    bot = [
        (spec.lerp(y1, y0, k / n), _deck_z(x, spec.lerp(y1, y0, k / n)) - down)
        for k in range(n + 1)
    ]
    return lib.section_face(x, top + bot)


def _louvres():
    """(slats, slot cutters) — raised carbon gills with a slot behind each."""
    slats, cutters = [], []
    for p in _louvre_plan():
        x_le, chord, twist = p["x"], p["chord"], p["twist"]
        y0, y1 = _louvre_span(x_le)
        ym = 0.5 * (y0 + y1)
        stations = []
        for y, k in ((y0, 0.0), (ym, 0.5), (y1, 1.0)):
            stations.append(
                {
                    "le": (x_le, y, _deck_z(x_le, y) - _LOUVRE_SINK),
                    "chord": chord * (1.0 - 0.10 * k),
                    "twist": twist,
                    "thickness": 0.075,
                    "camber": 0.050,
                    "te": spec.TE_THICKNESS,
                }
            )
        slats.append(lib.wing_element(stations))
        cutters.append(
            lib.body_loft(
                [
                    _deck_slab_face(x_le - 0.50 * chord, y0 + 8.0, y1 - 8.0, 7.0, 30.0),
                    _deck_slab_face(x_le - 1.20 * chord, y0 + 8.0, y1 - 8.0, 7.0, 30.0),
                ],
                ruled=True,
            )
        )
    return slats, cutters


# ---------------------------------------------------------------- furniture


def _mouth_box():
    pts = _cavity_outline(_X_NOSE)
    ys = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(ys), max(ys), min(zs), max(zs)


def _splitter_vane():
    """The horizontal splitter that halves the letterbox mouth."""
    y0, y1, z0, z1 = _mouth_box()
    zm = 0.5 * (z0 + z1) + 2.0
    ym = 0.5 * (y0 + y1)
    st = []
    for y, k in ((y0 - 3.0, 0.0), (ym, 0.5), (y1 + 3.0, 1.0)):
        st.append(
            {
                "le": (_X_NOSE - 10.0, y, zm + 5.0 * math.sin(math.pi * k)),
                "chord": 108.0,
                "twist": 6.0,
                "thickness": 0.085,
                "camber": 0.045,
                "te": spec.TE_THICKNESS,
            }
        )
    return lib.wing_element(st)


def _turning_vane():
    """Deflector rooted in the flank, hanging out into the undercut throat.

    It used to sit level with the inlet's outer lip, where the flank was almost
    vertical and there was nothing for it to articulate. Now it starts inside
    the skin just below the crease and sweeps OUTBOARD and DOWN across the mouth
    of the undercut, so from a low three-quarter it is the one lit edge inside
    the tunnel and the eye follows it under the pod. Twist steps up outboard so
    the section is visibly turning the air toward the floor edge.
    """
    st = []
    for k in (0.0, 0.5, 1.0):
        x_le = spec.lerp(-872.0, -902.0, k)
        y = spec.lerp(548.0, 668.0, k)
        z = spec.lerp(272.0, 242.0, k) - 14.0 * k * k
        st.append(
            {
                "le": (x_le, y, z),
                "chord": spec.lerp(104.0, 58.0, k),
                "twist": spec.lerp(5.0, 17.0, k),
                "sweep": 14.0,
                "thickness": 0.068,
                "camber": 0.065,
                "te": spec.TE_THICKNESS,
            }
        )
    return lib.wing_element(st)


def _outset(pts, d: float):
    """Grow a closed outline outward by d, backing off until it stays simple.

    The mouth outline pinches to a near-point at both ends of the slot, and a
    normal offset run outward through a pinch folds a small loop back on
    itself. The loop still lofts to a "valid" ring that OCC then refuses to
    build a face from, several calls later.
    """
    for k in (1.0, 0.8, 0.65, 0.5, 0.35):
        off = _inset(pts, -d * k)
        if not _crosses(off):
            return _resample(off)
    return _resample(_shrink(pts, -d))


def _lip_bezel():
    """THE accent: a 6 mm vermillion ring round the inlet aperture."""
    inner = _cavity_outline(_X_NOSE)
    outer = _outset(inner, 6.0)
    ring_out = lib.body_loft(
        [lib.section_face(-822.0, outer), lib.section_face(-813.0, outer)], ruled=True
    )
    ring_in = lib.body_loft(
        [lib.section_face(-824.0, inner), lib.section_face(-810.0, inner)], ruled=True
    )
    return ring_out - ring_in


# ---------------------------------------------------------------- assembly


@lru_cache(maxsize=1)
def _cavity_solid():
    return _duct_solid()


@lru_cache(maxsize=1)
def _left_panel():
    shell = _skin_solid() - _cavity_solid()
    slats, cutters = _louvres()
    for c in cutters:
        shell = shell - c
    for s in slats:
        shell = shell + s
    return shell


@lru_cache(maxsize=1)
def _left_furniture():
    return _splitter_vane(), _turning_vane(), _lip_bezel()


def build_sidepod(side: str):
    s = 1.0 if side == "left" else -1.0

    def put(shape):
        return shape if s > 0 else lib.mirror_y(shape)

    vane, turn, bezel = _left_furniture()
    return lib.group(
        f"sidepod_{side}",
        [
            lib.styled(put(_left_panel()), f"sidepod_panel:{side}", spec.CARBON_GLOSS),
            lib.styled(put(vane), f"inlet_splitter:{side}", spec.CARBON_MATTE),
            lib.styled(put(turn), f"inlet_turning_vane:{side}", spec.CARBON_MATTE),
            lib.styled(put(bezel), f"inlet_lip_stripe:{side}", spec.ACCENT),
        ],
    )


# ==========================================================================
# COOLING PACK — lives inside the panel, revealed when it lifts away
# ==========================================================================

_PACK_STATIONS = (-812.0, -1000.0, -1240.0, -1500.0, -1780.0, -2020.0, -2250.0)
_PACK_MARGIN = 13.0  # air gap between the coolers and the inside of the skin


@lru_cache(maxsize=128)
def _pack_ref(x: float):
    """The duct section at x, pulled in by the packaging air gap."""
    return _resample(_safe_inset(_cavity_outline(x), _PACK_MARGIN), 72)


def _inside(pts, poly) -> bool:
    """Every point of `pts` strictly inside the closed polygon `poly`."""
    n = len(poly)
    for y, z in pts:
        hit = False
        for i in range(n):
            ay, az = poly[i]
            by, bz = poly[(i + 1) % n]
            if (az > z) != (bz > z):
                if y < ay + (z - az) / (bz - az) * (by - ay):
                    hit = not hit
        if not hit:
            return False
    return True


def _pack_pts(x, shrink, waves=0, amp=0.0, dy=0.0, dz=0.0):
    # A periodic spline needs ~13 samples per fin to stay a fin instead of an
    # oscillation; under-sampled corrugation lofts to "BRep_API: command not done".
    n = max(72, 13 * waves)
    # ...and the corrugation only runs across the outboard face, dying to zero at
    # both ends of that window. Waving the tightly-curved inboard corners as well
    # is what makes the loft fail outright.
    w0, w1 = 0.16, 0.72
    """A cooler section derived from the duct itself, so it fits by shape.

    Radial corrugation gives fin ridges that run with the flow once lofted
    along X. Containment is asserted against the duct section rather than
    trusted to a boolean — a finned loft is boolean-hostile, and a silently
    empty intersection is how radiators end up outside the bodywork.
    """
    ref = _pack_ref(x)
    base = _resample(_safe_inset(ref, shrink + amp), n)
    cy = sum(p[0] for p in base) / n
    cz = sum(p[1] for p in base) / n
    out = []
    for k, (y, z) in enumerate(base):
        r = 0.0
        if waves and amp:
            u = (k / n - w0) / (w1 - w0)
            if 0.0 < u < 1.0:
                env = math.sin(math.pi * u) ** 2
                r = amp * env * math.sin(2.0 * math.pi * waves * u)
        vy, vz = y - cy, z - cz
        L = math.hypot(vy, vz) or 1.0
        out.append((y + vy / L * r + dy, z + vz / L * r + dz))
    return out, _inside(out, ref)


_PACK_LADDER = (0.0, 4.0, 9.0, 15.0, 23.0, 33.0, 46.0)


def _pack_body(x0, x1, shrink, amp=0.0, **kw):
    """Loft a cooler between two stations at ONE shrink that fits at both.

    Solving the two stations independently lets them land on different rungs of
    the ladder, and the ruled loft between two mismatched sections fails; so the
    body picks the smallest rung that clears the duct everywhere it spans. Fin
    amplitude then backs off the same way `lib.safe_fillet` backs off a radius:
    a slightly shallower fin always beats no radiator.
    """
    for extra in _PACK_LADDER:
        for a_scale in (1.0, 0.6, 0.35, 0.0):
            a, ok_a = _pack_pts(x0, shrink + extra, amp=amp * a_scale, **kw)
            b, ok_b = _pack_pts(x1, shrink + extra, amp=amp * a_scale, **kw)
            if not (ok_a and ok_b):
                continue
            try:
                out = lib.body_loft(
                    [lib.section_face(x0, a), lib.section_face(x1, b)], ruled=True
                )
                if out is not None and out.is_valid and out.volume > 0:
                    return out
            except Exception:
                continue
    raise ValueError(f"cooler {x0:.0f}..{x1:.0f} will not fit inside the duct")


@lru_cache(maxsize=1)
def _left_cooling():
    # --- side radiator: a pod-shaped finned core, the hero of the strip-down
    core = _pack_body(-1200.0, -1720.0, shrink=20.0, waves=11, amp=3.0)
    # --- end tanks: proud caps on each end of the core ---------------------
    tank_f = _pack_body(-1152.0, -1200.0, shrink=14.0)
    tank_r = _pack_body(-1720.0, -1772.0, shrink=14.0)
    # --- charge-air intercooler: smaller, higher and inboard, sitting right
    #     behind the letterbox so it is what you see through the mouth ------
    inter = _pack_body(
        -890.0, -1130.0, shrink=40.0, waves=8, amp=2.2, dy=-20.0, dz=10.0
    )
    # --- header pipes leaving each core toward the engine ------------------
    hot = _pipe(
        [
            (-1772.0, -0.15, 0.42),
            (-1880.0, -0.20, 0.40),
            (-2010.0, -0.28, 0.36),
            (-2140.0, -0.36, 0.32),
        ],
        [30.0, 28.0, 26.0, 24.0],
    )
    cold = _pipe(
        [
            (-1772.0, -0.18, 0.02),
            (-1880.0, -0.24, 0.04),
            (-2010.0, -0.32, 0.06),
            (-2140.0, -0.40, 0.10),
        ],
        [26.0, 24.0, 22.0, 20.0],
    )
    return core, tank_f, tank_r, inter, hot, cold


def _pipe(route, chords):
    """A header pipe routed in DUCT-RELATIVE coordinates.

    Waypoints are `(x, fy, fz)` with fy/fz in [-1, 1] of the duct section's own
    bounding box at that station, so the run follows the pod instead of being
    keyed to absolute millimetres that stop being inside the bodywork the moment
    the section law changes. Each waypoint is retracted toward the middle (and
    the pipe thinned) until its section box provably fits.
    """
    pts, cs = [], []
    for (x, fy, fz), c in zip(route, chords):
        ref = _pack_ref(x)
        ys = [p[0] for p in ref]
        zs = [p[1] for p in ref]
        cy = 0.5 * (min(ys) + max(ys))
        hy = 0.5 * (max(ys) - min(ys))
        placed = None
        for k in (1.0, 0.86, 0.72, 0.58, 0.44, 0.30, 0.16, 0.0):
            y = cy + fy * hy * k
            span = _z_span(ref, y)
            if span is None:
                continue
            # z is placed on the section's OWN local spine at that y, not on the
            # bounding box's centre line: this section is a crescent and its box
            # centre is out in the undercut void, not inside the duct at all.
            z = 0.5 * (span[0] + span[1]) + fz * 0.5 * (span[1] - span[0]) * k
            for s in (1.0, 0.85, 0.70, 0.55):
                cc = c * s
                box = [
                    (y - 0.5 * cc, z - 0.42 * cc),
                    (y + 0.5 * cc, z - 0.42 * cc),
                    (y + 0.5 * cc, z + 0.42 * cc),
                    (y - 0.5 * cc, z + 0.42 * cc),
                ]
                if _inside(box, ref):
                    placed = ((x, y, z), cc)
                    break
            if placed:
                break
        if placed is None:
            raise ValueError(f"header pipe waypoint x={x:.0f} will not fit the duct")
        pts.append(placed[0])
        cs.append(placed[1])
    return lib.blade_path(pts, cs, thickness_ratio=0.84)


def build_cooling():
    core, tank_f, tank_r, inter, hot, cold = _left_cooling()
    bodies = []
    for name, shape, color in (
        ("radiator_core", core, spec.COPPER),
        ("radiator_tank_front", tank_f, spec.ALLOY),
        ("radiator_tank_rear", tank_r, spec.ALLOY),
        ("intercooler", inter, spec.ANODIZED),
        ("header_pipe_hot", hot, spec.ALLOY),
        ("header_pipe_cold", cold, spec.ANODIZED),
    ):
        bodies.append(lib.styled(shape, f"{name}:left", color))
        bodies.append(lib.styled(lib.mirror_y(shape), f"{name}:right", color))
    return lib.group("cooling", bodies)
