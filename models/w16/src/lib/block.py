"""Cylinder block / crankcase (engine frame): one aluminium casting.

The W section with two decks, the valley, the skirt down to the pan rail, 16
bores, the crank tunnel with five main webs and their saddles, front and rear
walls, and the museum section on bank 1 — dressed as a real sand casting:
scalloped water-jacket bulges following each bore row, a vertical cast rib on
every main bulkhead, a longitudinal rib above the pan rail, cross-bolt bosses,
sump-rail bolt bosses, engine-mount pads, front seal/water-pump/timing bosses,
a rear seal + bell-housing flange, a parting line and two ID pads.

Machined faces (both decks, front, rear, sump rail, mount and pump pads) are
carried as separate 0.3 mm skin solids coloured `palette.MACHINED`.

Interfaces held fixed: deck planes (h = 226, m +/-125), the 16 bores, the bay
clearance cylinders (R 86), the five 22 mm main webs and their O74 saddles, the
lower interior, the pan rail at z = -95, front face x = 306, rear face x = -318.

Self-test:  cd src && ../../../.venv/bin/python -m lib.block
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C, fasteners as F, geo, palette as P, spec as S
from lib import oil_system as O   # circular with oil_system.block_trim; both only touch each other at build time
from lib.castings import safe_fillet, is_sound

SKIRT_HALF_Y = 165.0
WALL_T = 12.0
WEB_T = 19.0                  # bay ends 0.5 mm clear of the crank web faces (webs start at MAIN_X +/- 10)

# --- cast detail -----------------------------------------------------------
JACKET_PROUD = 5.0            # water-jacket bulge on the outer bank wall
JACKET_D = 100.0              # bulge diameter per cylinder (they overlap: 74 pitch)
JACKET_H = (150.0, 221.0)     # h band of the bulge (deck is 226)
RIB_W = 12.0                  # main-bulkhead rib width along X
RIB_PROUD = 5.0
RIB_TOP_H = 176.0             # rib runs from the rail up into the jacket
RAIL_RIB_Z = -75.0            # longitudinal rib centre, 20 above the rail
RAIL_BOSS_D = 24.0
RAIL_BOSS_TOP = -81.0
CROSS_Z = -25.0               # cross-bolt axis height
CROSS_BOSS_D = 22.0
CROSS_PROUD = 12.0
CROSS_DEPTH = 24.0
# Engine-mount pad: flush (the ancillaries mount ear beds 4 mm INTO this face),
# centred on the middle bulkhead, sized around the ear's own bolt square.
MOUNT_W, MOUNT_H = 150.0, 74.0
MOUNT_PAD_Z = -33.0
# 4 mm proud, not 8: the bank-1 chain guide blades start at x = 311.
SEAL_F_OD, SEAL_F_ID, SEAL_F_PROUD = 110.0, 68.0, 4.0
SEAL_R_OD, SEAL_R_ID = 150.0, 120.0

SKIRT_SLOPE_N = (0.96139, -0.27530)   # outward normal of the lower skirt face


def section_outline():
    """Block cross-section as a CCW (y, z) polygon."""
    a1 = S.bank_point(1, 0, S.HEAD_M_HALF - 5, S.DECK_H)[1:]
    b1 = S.bank_point(1, 0, -(S.HEAD_M_HALF - 5), S.DECK_H)[1:]
    c1 = (b1[0] - 70 * 0.70710678, b1[1] - 70 * 0.70710678)
    d1 = (SKIRT_HALF_Y, S.SUMP_RAIL_Z)
    valley = (0.0, 205.0)
    right = [d1, c1, b1, a1]
    left = [(-y, z) for y, z in reversed(right)]
    return [(-SKIRT_HALF_Y, S.SUMP_RAIL_Z)] + right + [valley] + left[:-1]


def inner_outline():
    """Lower crankcase interior (below the crank axis), inset from the skirt."""
    return [(-(SKIRT_HALF_Y - WALL_T), S.SUMP_RAIL_Z - 1), (SKIRT_HALF_Y - WALL_T, S.SUMP_RAIL_Z - 1),
            (SKIRT_HALF_Y - WALL_T - 8, 0.0), (-(SKIRT_HALF_Y - WALL_T - 8), 0.0)]


def bays():
    """(x_rear, x_front) of each open crankcase bay between main webs."""
    out = []
    for k in range(len(S.MAIN_X) - 1):
        out.append((S.MAIN_X[k + 1] + WEB_T / 2, S.MAIN_X[k] - WEB_T / 2))
    return out


# ---------------------------------------------------------------------------
# Section-profile geometry (all in the (y, z) plane, +y side)
# ---------------------------------------------------------------------------

def _corners():
    """(d1 rail corner, c1 skirt/bank corner, b1 deck outer corner) on +y."""
    o = section_outline()
    return o[1], o[2], o[3]


def _unit2(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n)


def _band(p0, p1, n, inn, out, ext0=0.0, ext1=0.0):
    """Quad (y, z) polygon: a band along p0->p1, `inn` inside the face and
    `out` proud of it, extended past each end."""
    t = _unit2((p1[0] - p0[0], p1[1] - p0[1]))
    a = (p0[0] - ext0 * t[0], p0[1] - ext0 * t[1])
    b = (p1[0] + ext1 * t[0], p1[1] + ext1 * t[1])
    return [(a[0] - inn * n[0], a[1] - inn * n[1]),
            (b[0] - inn * n[0], b[1] - inn * n[1]),
            (b[0] + out * n[0], b[1] + out * n[1]),
            (a[0] + out * n[0], a[1] + out * n[1])]


def _mirror(poly):
    return [(-y, z) for y, z in reversed(poly)]


def _prism(poly, x0, x1, sy):
    return geo.prism_yz(poly if sy > 0 else _mirror(poly), x0, x1)


# ---------------------------------------------------------------------------
# Cast additions
# ---------------------------------------------------------------------------

def _jacket(bank: int):
    """Scalloped water-jacket bulge on a bank's outer wall (m = -125)."""
    out = -S.bank_m(bank)[1], -S.bank_m(bank)[2]
    axis = (0.0, out[0], out[1])
    lumps = []
    for c in [c for c in S.CYLINDERS if c.bank == bank]:
        base = S.bank_point(bank, c.x, -(S.HEAD_M_HALF - 5) + 2.0,
                            (JACKET_H[0] + JACKET_H[1]) / 2.0)
        lumps.append(geo.locate(C.boss(JACKET_D, JACKET_PROUD + 2.0, draft_deg=12.0,
                                       fillet_r=6.0), base, axis))
    band = C.fuse_all(lumps)
    clip = [S.bank_point(bank, 0, m, h)[1:]
            for m, h in ((-400, JACKET_H[0]), (400, JACKET_H[0]),
                         (400, JACKET_H[1]), (-400, JACKET_H[1]))]
    if bank == 2:
        clip = list(reversed(clip))
    return band & geo.prism_yz(clip, S.BLOCK_REAR_X, S.BLOCK_FRONT_X)


def _crest_edges(solid, n):
    """Edges of `solid` lying on its outermost face along direction `n`."""
    def proj(v):
        return v.X * n[0] + v.Y * n[1] + v.Z * n[2]
    dmax = max(proj(v.center()) for v in solid.vertices())
    return [e for e in solid.edges()
            if all(abs(proj(v.center()) - dmax) < 0.25 for v in e.vertices())]


def _soften_crest(solid, n2, r=2.5):
    """Round the proud face of a cast rib so it reads as sand-cast, not sheet."""
    n = (0.0, n2[0], n2[1])
    out, _ = safe_fillet(solid, _crest_edges(solid, n), r, min_r=0.8)
    return out


def _bulkhead_ribs():
    """A vertical cast rib on the outer skirt at every main station."""
    d1, c1, b1 = _corners()
    up = (S.bank_up(1)[1], S.bank_up(1)[2])
    n_low = SKIRT_SLOPE_N
    n_up = (-S.bank_m(1)[1], -S.bank_m(1)[2])
    top = (c1[0] + (RIB_TOP_H - 156.0) * up[0], c1[1] + (RIB_TOP_H - 156.0) * up[1])
    lower = _band(d1, c1, n_low, 6.0, RIB_PROUD, ext0=4.0, ext1=2.0)
    upper = _band(c1, top, n_up, 8.0, RIB_PROUD, ext0=8.0)
    out = []
    for xm in S.MAIN_X:
        x0 = max(xm - RIB_W / 2, S.BLOCK_REAR_X)
        x1 = min(xm + RIB_W / 2, S.BLOCK_FRONT_X)
        for sy in (1, -1):
            nl = (sy * n_low[0], n_low[1])
            nu = (sy * n_up[0], n_up[1])
            out.append(_soften_crest(_prism(lower, x0, x1, sy), nl))
            out.append(_soften_crest(_prism(upper, x0, x1, sy), nu))
    return out


def _rail_rib():
    """Longitudinal cast rib along the skirt, 20 mm above the pan rail."""
    d1, c1, _ = _corners()
    up = _unit2((c1[0] - d1[0], c1[1] - d1[1]))
    s = (RAIL_RIB_Z - d1[1]) / up[1]
    p0 = (d1[0] + (s - 7.0) * up[0], d1[1] + (s - 7.0) * up[1])
    p1 = (d1[0] + (s + 7.0) * up[0], d1[1] + (s + 7.0) * up[1])
    poly = _band(p0, p1, SKIRT_SLOPE_N, 6.0, 5.0)
    return [_soften_crest(_prism(poly, S.BLOCK_REAR_X + 6.0, S.BLOCK_FRONT_X - 6.0, sy),
                          (sy * SKIRT_SLOPE_N[0], SKIRT_SLOPE_N[1]), r=2.0)
            for sy in (1, -1)]


def _rail_bosses(envelope):
    """A boss under every sump-pan bolt, clipped flush to the skirt."""
    out = []
    for bx, by in S.pan_bolt_points():
        b = geo.cyl_along((bx, by, S.SUMP_RAIL_Z - 2.0), (bx, by, RAIL_BOSS_TOP),
                          RAIL_BOSS_D)
        out.append(b & envelope)
    return out


# ---------------------------------------------------------------------------
# Drilling: every hole is checked against the 16 bore cylinders
# ---------------------------------------------------------------------------

def _bore_clear(p, r: float, extra: float = 2.0) -> bool:
    """True when a hole of radius `r` at `p` keeps `extra` mm of metal to every
    bore wall."""
    for c in S.CYLINDERS:
        vy, vz = p[1] - c.foot[1], p[2] - c.foot[2]
        along = vy * c.axis[1] + vz * c.axis[2]
        if along < S.BORE_BOTTOM_S - 6.0:
            continue
        py, pz = vy - along * c.axis[1], vz - along * c.axis[2]
        if math.hypot(p[0] - c.x, math.hypot(py, pz)) < S.BORE / 2 + r + extra:
            return False
    return True


def _drill(p0, direction, depth: float, d: float, over: float = 1.5,
           check: bool = True):
    """A drilling tool from `p0` (on the surface) `depth` into the metal, with
    `over` of overshoot outside. Returns None when it would break into a bore."""
    u = geo._unit(direction)
    a = tuple(p0[i] - u[i] * over for i in range(3))
    b = tuple(p0[i] + u[i] * depth for i in range(3))
    if check:
        for t in (0.0, 0.5, 1.0):
            q = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
            if not _bore_clear(q, d / 2.0):
                return None
    return geo.cyl_along(a, b, d)


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------

HEAD_BOLT_M = (-112.0, -94.0, 94.0, 112.0)   # inner pair just outside the bore edge (m = 88.9 at the deck)
COOLANT_MID_M = 0.0            # the channel between the two bore rows
COOLANT_ROW_M = 72.0           # beside each bore, on its free side
HEAD_BOLT_D, HEAD_BOLT_DEPTH = 13.0, 30.0
COOLANT_D, COOLANT_DEPTH = 10.0, 40.0
DOWEL_D = 12.0


def deck_stations(bank: int):
    """Transverse bolt stations: one between every pair of bores — seven per
    deck, four head bolts each."""
    xs = sorted([c.x for c in S.CYLINDERS if c.bank == bank], reverse=True)
    mids = [(xs[i] + xs[i + 1]) / 2.0 for i in range(len(xs) - 1)]
    # No stations beyond the end cylinders: in the head those holes run straight
    # through the end cylinder's intake and exhaust ports, so both castings
    # carry the seven midpoint stations only (28 bolts per deck).
    return mids


def _deck_cuts(bank: int):
    up = S.bank_up(bank)
    stations = deck_stations(bank)
    out = []
    for i, x in enumerate(stations):
        for m in HEAD_BOLT_M:
            out.append(_drill(S.bank_point(bank, x, m, S.DECK_H), tuple(-v for v in up),
                              HEAD_BOLT_DEPTH, HEAD_BOLT_D))
        if 0 < i < len(stations) - 1:
            out.append(_drill(S.bank_point(bank, x, COOLANT_MID_M, S.DECK_H),
                              tuple(-v for v in up), COOLANT_DEPTH, COOLANT_D))
    cyls = sorted([c for c in S.CYLINDERS if c.bank == bank], key=lambda c: -c.x)
    for c in cyls:
        m = -COOLANT_ROW_M if c.row == "inner" else COOLANT_ROW_M
        out.append(_drill(S.bank_point(bank, c.x, m, S.DECK_H), tuple(-v for v in up),
                          COOLANT_DEPTH, COOLANT_D))
    # two dowels, each on the free side of the end cylinder's bore
    for c, dx in ((cyls[0], 20.0), (cyls[-1], -20.0)):
        m = -70.0 if c.row == "inner" else 70.0
        out.append(_drill(S.bank_point(bank, c.x + dx, m, S.DECK_H),
                          tuple(-v for v in up), 22.0, DOWEL_D))
    missing = out.count(None)
    assert missing == 0, f"bank {bank}: {missing} deck holes foul a bore"
    return out


# ---------------------------------------------------------------------------
# Front face, rear face, skirt
# ---------------------------------------------------------------------------

def _perimeter(poly, pitch: float, inset: float):
    """Points walked at `pitch` around `poly` inset by `inset` (CCW = inward)."""
    n = len(poly)
    ins = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        n1 = _unit2((-(p1[1] - p0[1]), p1[0] - p0[0]))
        n2 = _unit2((-(p2[1] - p1[1]), p2[0] - p1[0]))
        k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        ins.append((p1[0] + inset * (n1[0] + n2[0]) / k,
                    p1[1] + inset * (n1[1] + n2[1]) / k))
    segs = [(ins[i], ins[(i + 1) % n]) for i in range(n)]
    total = sum(math.dist(a, b) for a, b in segs)
    count = max(4, int(round(total / pitch)))
    step = total / count
    out, s = [], 0.0
    for i in range(count):
        d = i * step
        for a, b in segs:
            L = math.dist(a, b)
            if d <= L + 1e-9:
                t = d / L
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
            d -= L
    return out


def spacer_points():
    """The four chain-guide spacer feet that land on the block front face."""
    return [(41.1, -19.2), (-19.2, 41.1), (19.2, 41.1), (-41.1, -19.2)]


def _wp_bolt_points(bank: int):
    """Water-pump flange bolts, identical to the ancillaries pattern."""
    s = S.sign_of_bank(bank)
    cy, cz = s * 148.0, -40.0
    return [(cy + s * 24.0 * math.cos(math.radians(30 + 60 * k)),
             cz + 24.0 * math.sin(math.radians(30 + 60 * k))) for k in range(6)]


BELL_R_PCD = S.BELL_HOUSING_D / 2.0 - 15.0     # 200: the ancillaries bolt circle
BELL_ANGLES = [30.0 * k + 15.0 for k in range(12)]
FRONT_DOWEL = [(86.0, -70.0), (-86.0, -70.0)]


def _bell_points():
    return [(BELL_R_PCD * math.cos(math.radians(a)), BELL_R_PCD * math.sin(math.radians(a)))
            for a in BELL_ANGLES]


def _face_clearance(p) -> float:
    """Signed distance from (y, z) to the block section outline: positive
    inside. The outline is NOT convex (the valley vertex is reflex), so this
    is a real point-in-polygon test plus a segment distance, not a stack of
    half-planes."""
    poly = section_outline()
    n = len(poly)
    inside = False
    best = 1e18
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]):
            xx = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < xx:
                inside = not inside
        vy, vz = b[0] - a[0], b[1] - a[1]
        L2 = vy * vy + vz * vz
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * vy + (p[1] - a[1]) * vz) / L2))
        best = min(best, math.dist(p, (a[0] + t * vy, a[1] + t * vz)))
    return best if inside else -best


def _inside_face(p, margin: float = 8.0) -> bool:
    """Is (y, z) at least `margin` inside the block section outline?"""
    return _face_clearance(p) >= margin


def _front_cuts():
    """Seal bore, guide-spacer reliefs and threads, pump bolts, dowels and the
    timing-cover bolt ring."""
    xf = S.BLOCK_FRONT_X
    cuts = [geo.cyl_x(xf - 2.0, xf + SEAL_F_PROUD + 4.0, SEAL_F_ID)]
    for y, z in spacer_points():
        cuts.append(C.fuse_all([
            geo.cyl_x(xf - 0.2, xf + SEAL_F_PROUD + 3.0, 18.0, y, z),
            geo.cyl_x(xf - 24.0, xf + 1.0, 7.4, y, z)]))
    for bank in (1, 2):
        for y, z in _wp_bolt_points(bank):
            cuts.append(_drill((xf, y, z), (-1, 0, 0), 20.0, 7.4))
    for y, z in FRONT_DOWEL:
        cuts.append(_drill((xf, y, z), (-1, 0, 0), 12.0, DOWEL_D))
    blocked = [(0.0, 0.0, 70.0)] + [(S.sign_of_bank(b) * 148.0, -40.0, 46.0) for b in (1, 2)] \
        + [(y, z, 22.0) for y, z in FRONT_DOWEL]
    for y, z in _perimeter(section_outline(), 60.0, 13.0):
        if any(math.dist((y, z), (by, bz)) < r for by, bz, r in blocked):
            continue
        cuts.append(_drill((xf, y, z), (-1, 0, 0), 14.0, 7.4))
    return [c for c in cuts if c is not None]


def _rear_cuts():
    xr = S.BLOCK_REAR_X
    cuts = [C.fuse_all([geo.cyl_x(xr - 2.0, xr + 5.5, SEAL_R_OD),
                        geo.cyl_x(xr - 2.0, xr + 12.5, SEAL_R_ID)])]
    for y, z in _bell_points():
        if not _inside_face((y, z), 14.0) and not _inside_face((y, z), -20.0):
            continue                                  # no metal and no lug: skip
        cuts.append(_drill((xr, y, z), (1, 0, 0), 15.0, 11.0))
    for y, z in FRONT_DOWEL:
        cuts.append(_drill((xr, y, z), (1, 0, 0), 12.0, DOWEL_D))
    return [c for c in cuts if c is not None]


def _bell_lugs():
    """Cast lugs for the two bell-housing bolts that fall off the skirt."""
    out = []
    for y, z in _bell_points():
        if _inside_face((y, z), 14.0) or not _inside_face((y, z), -20.0):
            continue
        out.append(geo.locate(C.boss(46.0, 16.0, draft_deg=6.0, fillet_r=4.0),
                              (S.BLOCK_REAR_X, y, z), (1, 0, 0)))
    return out


def skirt_point(sy: float, z: float):
    """(x-free) point on the lower skirt face at height z, sign sy."""
    return (sy * (165.0 + (198.7 - 165.0) * (z + 95.0) / 116.9), z)


def _skirt_normal(sy: float):
    return (0.0, sy * SKIRT_SLOPE_N[0], SKIRT_SLOPE_N[1])


# Cross-bolt stations: every main web except x = 0 (the engine-mount pad) and
# the two the oil filter housing / oil pump bracket already occupy.
CROSS_STATIONS = [(296.0, 1), (-148.0, 1), (-296.0, 1),
                  (148.0, -1), (-148.0, -1), (-296.0, -1)]
MOUNT_BOLTS = [(-46.0, -62.0), (46.0, -62.0), (-46.0, -4.0), (46.0, -4.0)]
MAIN_BOLT_Y = 40.0            # bottom_end seats the cap bolts here
MAIN_BOLT_DEPTH = 52.0


def _cross_bosses():
    out = []
    for xm, sy in CROSS_STATIONS:
        y, z = skirt_point(sy, CROSS_Z)
        out.append(geo.locate(C.boss(CROSS_BOSS_D + 8.0, CROSS_PROUD + 4.0, draft_deg=7.0,
                                     fillet_r=3.0),
                              (xm, y - _skirt_normal(sy)[1] * 4.0, z - _skirt_normal(sy)[2] * 4.0),
                              _skirt_normal(sy)))
    return out


def _skirt_cuts():
    out = []
    for xm, sy in CROSS_STATIONS:
        y, z = skirt_point(sy, CROSS_Z)
        n = _skirt_normal(sy)
        p = (xm, y + n[1] * CROSS_PROUD, z + n[2] * CROSS_PROUD)
        out.append(_drill(p, (0, -n[1], -n[2]), CROSS_PROUD + CROSS_DEPTH, 9.2))
    for sy in (1, -1):
        n = _skirt_normal(sy)
        for bx, bz in MOUNT_BOLTS:
            y, z = skirt_point(sy, bz)
            out.append(_drill((bx, y, z), (0, -n[1], -n[2]), 20.0, 11.0))
    for bx, by in S.pan_bolt_points():
        out.append(_drill((bx, by, S.SUMP_RAIL_Z), (0, 0, 1), 18.0, 7.4))
    # tappings the oil system bolts into: windage tray, filter housing ears,
    # pump bracket — positions read straight off oil_system so they cannot drift
    for xm in O.TRAY_BOLT_X:
        for sy in (1.0, -1.0):
            out.append(geo.cyl_along((xm, sy * O.TRAY_BOLT_Y, O.TRAY_FLANGE_Z - 2.0),
                                     (xm, sy * O.TRAY_BOLT_Y, O.TRAY_FLANGE_Z + 30.0), 7.4))
    n1, s1 = O.skirt_normal(1), O.skirt_slope_dir(1)
    fc = O.skirt_point(1, O.FILTER_X, O.FILTER_Z)
    for dx in (-66.0, 66.0):
        for ds in (-36.0, 40.0):
            pt = (fc[0] + dx, fc[1] + ds * s1[1], fc[2] + ds * s1[2])
            out.append(_drill(pt, (-n1[0], -n1[1], -n1[2]), 20.0, 9.2))
    n2 = O.skirt_normal(2)
    for dx in (-50.0, 0.0, 50.0):
        pt = O.skirt_point(2, O.PUMP_C[0] + dx, -45.0)
        out.append(_drill(pt, (-n2[0], -n2[1], -n2[2]), 24.0, 9.2))
    # main-cap bolts thread up into every bulkhead from the saddle split line
    for xm in S.MAIN_X:
        for sy in (1, -1):
            out.append(geo.cyl_along((xm, sy * MAIN_BOLT_Y, -4.0),
                                     (xm, sy * MAIN_BOLT_Y, MAIN_BOLT_DEPTH), 11.2))
    return [c for c in out if c is not None]


def _parting_bead(body):
    """The mould flash along the skirt at z = PARTING_Z, kept off the machined
    faces and out of the crankcase (the R 86 bay clearance is sacred)."""
    slab = bd.Box(700.0, 700.0, 1.4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER)
                  ).moved(bd.Location((0, 0, PARTING_Z)))
    band = body & slab
    if not is_sound(band):
        return body
    try:
        bead = bd.offset(band, amount=0.4)
    except Exception:
        return body
    keep = [bd.Box(S.BLOCK_FRONT_X - 1.0 - (S.BLOCK_REAR_X + 1.0), 160.0, 12.0,
                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER)).moved(
        bd.Location(((S.BLOCK_FRONT_X + S.BLOCK_REAR_X) / 2.0, sy * 230.0, PARTING_Z)))
        for sy in (1, -1)]
    bead = bead & C.fuse_all(keep)
    if not is_sound(bead):
        return body
    out = body + bead
    return out if is_sound(out) else body


PARTING_Z = -20.0
# The front of the bank-2 skirt carries the oil-pump bracket (x 186..314) and
# the mount pad (|x| < 75), so the ID pads sit either side of the mount pad.
ID_PADS = [(105.0, -45.0), (-100.0, -45.0)]


def _skirt_root_edges(body):
    """Edges lying in the lower skirt face: the rib, boss and pad roots."""
    d1 = _corners()[0]
    out = []
    for e in body.edges():
        c = C.edge_center(e)
        d = (abs(c.Y) - d1[0]) * SKIRT_SLOPE_N[0] + (c.Z - d1[1]) * SKIRT_SLOPE_N[1]
        if abs(d) < 0.4 and e.length < 170.0 and -92.0 < c.Z < 18.0:
            out.append(e)
    return out


def _casting(sectioned: bool = True):
    """(body, [(label, machined skin)]) — the whole casting."""
    body = geo.prism_yz(section_outline(), S.BLOCK_REAR_X, S.BLOCK_FRONT_X)
    envelope = geo.prism_yz(section_outline(), S.BLOCK_REAR_X - 1.0, S.BLOCK_FRONT_X + 1.0)
    _, c1, _ = _corners()
    body, _ = safe_fillet(body, [e for e in body.edges()
                                 if math.dist((abs(C.edge_center(e).Y), C.edge_center(e).Z), c1) < 1e-3],
                          10.0, min_r=3.0)
    body, _ = safe_fillet(body, [e for e in body.edges()
                                 if abs(C.edge_center(e).Y) < 1e-6
                                 and abs(C.edge_center(e).Z - 205.0) < 1e-3], 14.0, min_r=4.0)
    seal = geo.locate(C.boss(SEAL_F_OD, SEAL_F_PROUD + 2.0, draft_deg=5.0, fillet_r=4.0),
                      (S.BLOCK_FRONT_X - 2.0, 0, 0), (1, 0, 0))
    adds = ([_jacket(1), _jacket(2)] + _bulkhead_ribs() + _rail_rib()
            + _rail_bosses(envelope) + _cross_bosses() + _bell_lugs() + [seal])
    body = C.fuse_all([body] + adds)
    body, _ = safe_fillet(body, _skirt_root_edges(body), 5.0, min_r=1.0)
    # bores
    cutters = []
    for c in S.CYLINDERS:
        p0 = c.point(S.BORE_BOTTOM_S)
        p1 = c.point(320.0)
        cutters.append(geo.cyl_along(p0, p1, S.BORE))
    body = C.cut_all(body, cutters)
    # crank tunnel bays (above the pan rail, rods swing here) + lower interior
    tunnel = []
    for x_r, x_f in bays():
        tunnel.append(geo.cyl_x(x_r, x_f, 2 * S.CRANKCASE_CLEAR_R))
    lower = geo.prism_yz(inner_outline(), S.BLOCK_REAR_X + WALL_T, S.BLOCK_FRONT_X - WALL_T)
    body = C.cut_all(body, tunnel + [lower])
    # main saddles through every web and the end walls, ending in the two seal
    # registers (which also clear the crank's rear flange and seal journal)
    body = C.cut_all(body, [geo.cyl_x(S.BLOCK_REAR_X + 12.5, S.BLOCK_FRONT_X + 0.5, S.MAIN_D + 4.0)])
    body = C.cut_all(body, _rear_cuts())
    body = C.cut_all(body, _front_cuts())
    body = C.cut_all(body, _deck_cuts(1) + _deck_cuts(2))
    body = C.cut_all(body, _skirt_cuts())
    # the rail is a machined flange: trim everything the ribs left below it
    body = C.cut_all(body, [bd.Box(1200.0, 700.0, 60.0,
                                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
        bd.Location((0, 0, S.SUMP_RAIL_Z)))])
    body = _parting_bead(body)

    parts = []
    skins = [("deck_1", C.frame(S.bank_point(1, 0, 0, S.DECK_H), S.bank_up(1), (1, 0, 0)), 0.3),
             ("deck_2", C.frame(S.bank_point(2, 0, 0, S.DECK_H), S.bank_up(2), (1, 0, 0)), 0.3),
             ("front", C.frame((S.BLOCK_FRONT_X, 0, 0), (1, 0, 0), (0, 1, 0)), 0.3),
             ("rear", C.frame((S.BLOCK_REAR_X, 0, 0), (-1, 0, 0), (0, 1, 0)), 0.3),
             ("sump_rail", C.frame((0, 0, S.SUMP_RAIL_Z), (0, 0, -1), (1, 0, 0)), 0.3)]
    for name, plane, t in skins:
        skin = C.machined_skin(body, plane, t=t)
        if skin is None:
            continue
        body = body - skin
        parts.append((f"block_face:{name}", skin))
    for sy, tag in ((1, "1"), (-1, "2")):
        n = _skirt_normal(sy)
        y, z = skirt_point(sy, MOUNT_PAD_Z)
        pad = bd.Pos(0, 0, -0.3) * bd.extrude(bd.RectangleRounded(MOUNT_W, MOUNT_H, 12.0), amount=0.3)
        skin = body & geo.locate(pad, (0.0, y, z), n, (1, 0, 0))
        if is_sound(skin):
            body = body - skin
            parts.append((f"block_face:mount_pad_{tag}", skin))

    body = geo.sectioned(body, 1, sectioned)
    assert is_sound(body), "block not sound"
    return body, parts


def build_block(sectioned: bool = True):
    """The casting alone (lib.collide takes this as the static block)."""
    return P.style(_casting(sectioned)[0], "block", P.CAST)


def build_fasteners(sectioned: bool = True):
    """Cross bolts through the skirt into the main caps, and two ID pads."""
    parts = []
    bolt = F.hex_flange_bolt(10.0, 30.0)
    for xm, sy in CROSS_STATIONS:
        y, z = skirt_point(sy, CROSS_Z)
        n = _skirt_normal(sy)
        seat = (xm, y + n[1] * CROSS_PROUD, z + n[2] * CROSS_PROUD)
        if geo.in_section_void(seat, 1, sectioned):
            continue
        parts.append(P.style(F.place(bolt, seat, n, (1, 0, 0)),
                             f"cross_bolt:{'f' if xm > 0 else 'r'}{abs(int(xm))}_"
                             f"{'l' if sy > 0 else 'r'}", P.TITANIUM))
    pad = F.id_pad(56.0, 30.0, 2.0)
    for i, (px, pz) in enumerate(ID_PADS, start=1):
        y, z = skirt_point(-1, pz)
        n = _skirt_normal(-1)
        parts.append(P.style(F.place(pad, (px, y, z), n, (1, 0, 0)),
                             f"block_id_pad:{i}", P.MACHINED))
    return parts


def build(sectioned: bool = True):
    body, skins = _casting(sectioned)
    out = [P.style(body, "block", P.CAST)]
    for label, skin in skins:
        skin = geo.sectioned(skin, 1, sectioned)
        if is_sound(skin):
            out.append(P.style(skin, label, P.MACHINED))
    return out + build_fasteners(sectioned)


if __name__ == "__main__":
    import time

    t0 = time.time()
    ps = build(True)
    print(f"{len(ps)} parts in {time.time() - t0:.1f}s")
    for p in ps:
        print(" ", p.label, "sound" if geo.sound(p) else "UNSOUND")
