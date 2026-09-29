"""Accessory system: the rear accessory section (y 262 ..~545) and everything it carries.

    case          `accessory:case` one casting: front flange y 262..274 (r 150..233,
                  18 clearance holes on r 200 for the blower's studs + nuts), a
                  recessed neck r 164 behind the nut ring, and the lobed rear body
                  y 290..338 whose outline is the smooth union of a r 176 drum,
                  two magneto lobes, generator + fuel-pump lobes and the bottom
                  sump rail. Raised machined pads (skins `*_pad`) at y 344, a cast
                  parting bead at y 314, a lifting-eye boss on top.
    magnetos      `accessory:magneto_L|R` (+ `_cap`, `_coil_cover`, `_outlet`,
                  clips, ground terminal, gasket, studs/nuts): axes along +Y at
                  (-+150, 30), drive flange y 345.4, body to y 468, distributor
                  cap to y 494. The high-tension OUTLET on top has its mating face
                  at y 370, centre (-+150, 370, 130), radius 21 -- the ignition
                  feed terminal's rear face (`ignition:feed_terminal_L|R`).
    starter       `accessory:starter_*` on the centre pad (axis = crank axis).
    generator     `accessory:generator_*` lower right seen from the rear (-108, -124).
    fuel pump     `accessory:fuel_pump_*` lower left seen from the rear (108, -124).
    oil pump      `accessory:oil_pump_*` bottom centre (0, -180); copper oil line
                  to the oil-screen housing cast on the sump.
    tach drive    `accessory:tach_cover` + nuts at (0, 134).
    sump          `accessory:sump` bolted under the case rail (z -228), finned,
                  drain plug + oil-screen cap safety-wired.

Every mounted item stacks: case pad face y 344 | machined skin 0.4 | gasket 1.0 |
flange from y 345.4. Studs are seated at y 344 (12 mm into drilled holes).
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("braid", "brass", "case_silver", "copper", "fastener", "gasket", "machined_alu",
             "magneto_black", "safety_wire", "steel_polished")

# ---------------------------------------------------------------------------
# Stations (engine frame, mm)
# ---------------------------------------------------------------------------
Y_FACE = 262.0            # blower machined face
Y_FL = 274.0              # flange rear (blower nuts seat here)
NECK_R = 164.0
Y_B0, Y_B1 = 290.0, 338.0  # lobed rear body
Y_PAD = 344.0             # machined pad face (studs seat here)
Y_SKIN = Y_PAD + 0.4
Y_EQ = Y_SKIN + 1.0       # equipment flanges seat on the gasket here
ACC_STUD_R = 200.0
ACC_ANGLES = [10.0 + 20.0 * j for j in range(18)]

MAG = {"L": (-162.0, 22.0), "R": (162.0, 22.0)}
MAG_EAR = 68.0
TERMINAL_X, TERMINAL_Y, TERMINAL_Z = 150.0, 370.0, 130.0   # |x|; L at -150
GEN = (-108.0, -124.0)
FUEL = (108.0, -124.0)
OILP = (0.0, -180.0)
TACH = (0.0, 134.0)
RAIL_Z = -228.0           # case bottom (sump joint)

TAP8 = 2 * F._shank_radius(8.0) + 0.05
TAP6 = 2 * F._shank_radius(6.0) + 0.05
TAP10 = 2 * F._shank_radius(10.0) + 0.05

_INFO: dict = {}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _one(shape):
    sols = shape.solids()
    if len(sols) == 1:
        return sols[0]
    return max(sols, key=lambda s: s.volume)


def _st(shape, label, color):
    return P.style(shape, label, color)


def _V2(p):
    return bd.Vector(p[0], p[1], 0.0)


def _prof_face(start, segs):
    """Closed (r, y) profile in the XY plane: ("L", p) | ("A", mid, end)."""
    cur = start
    edges = []
    for sg in segs:
        if sg[0] == "L":
            edges.append(bd.Line(_V2(cur), _V2(sg[1])))
            cur = sg[1]
        else:
            edges.append(bd.ThreePointArc(_V2(cur), _V2(sg[1]), _V2(sg[2])))
            cur = sg[2]
    if abs(cur[0] - start[0]) + abs(cur[1] - start[1]) > 1e-9:
        edges.append(bd.Line(_V2(cur), _V2(start)))
    return bd.Face(bd.Wire(edges))


def _rev(start, segs, cx=0.0, cz=0.0):
    """Solid of revolution about the axis parallel to Y through (cx, cz)."""
    body = bd.revolve(_prof_face(start, segs), axis=bd.Axis.Y, revolution_arc=360.0)
    if cx or cz:
        body = bd.Pos(cx, 0, cz) * body
    return body


def _revp(pts, cx=0.0, cz=0.0):
    return _rev(pts[0], [("L", p) for p in pts[1:]], cx, cz)


def _arc_pt(corner, r, d_in, d_out):
    """(start, mid, end) of a radius-r round at a 90-degree profile corner."""
    cx, cy = corner
    s = (cx - d_in[0] * r, cy - d_in[1] * r)
    e = (cx + d_out[0] * r, cy + d_out[1] * r)
    c = (s[0] + d_out[0] * r, s[1] + d_out[1] * r)
    m = ((s[0] + e[0]) / 2 - c[0], (s[1] + e[1]) / 2 - c[1])
    n = math.hypot(*m)
    return s, (c[0] + m[0] / n * r, c[1] + m[1] / n * r), e


def _cyl(p0, p1, d):
    return geo.cyl_along(p0, p1, d)


def _yhole(x, z, y0, y1, d):
    return geo.cyl_y(y0, y1, d, x, z)


# ---------------------------------------------------------------------------
# Signed-distance outlines (smooth unions -> one periodic spline -> slab)
# ---------------------------------------------------------------------------
def sd_circle(cx, cz, r):
    return lambda x, z: math.hypot(x - cx, z - cz) - r


def sd_capsule(a, b, r):
    ax, az = a
    bx, bz = b

    def f(x, z):
        vx, vz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((x - ax) * vx + (z - az) * vz) / (vx * vx + vz * vz)))
        return math.hypot(x - ax - t * vx, z - az - t * vz) - r
    return f


def sd_rbox(cx, cz, hx, hz, r):
    def f(x, z):
        qx = abs(x - cx) - (hx - r)
        qz = abs(z - cz) - (hz - r)
        return math.hypot(max(qx, 0.0), max(qz, 0.0)) + min(max(qx, qz), 0.0) - r
    return f


def _smin(ds, s):
    m = min(ds)
    return m - math.log(sum(math.exp(-s * (d - m)) for d in ds)) / s


def outline_pts(sdfs, centre, s=0.2, off=0.0, n=160):
    cx, cz = centre
    pts = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        ux, uz = math.cos(a), math.sin(a)

        def f(t):
            return _smin([d(cx + t * ux, cz + t * uz) for d in sdfs], s) - off
        lo, hi = 0.0, 500.0
        assert f(lo) < 0.0 < f(hi)
        for _ in range(48):
            mid = 0.5 * (lo + hi)
            if f(mid) < 0.0:
                lo = mid
            else:
                hi = mid
        t = 0.5 * (lo + hi)
        pts.append((cx + t * ux, cz + t * uz))
    return pts


def slab(pts, y0, y1):
    """Prism of the closed (x, z) outline between stations y0 < y1."""
    edge = bd.Spline(*[bd.Vector(x, y0, z) for x, z in pts], periodic=True)
    face = bd.Face(bd.Wire([edge]))
    return bd.extrude(face, amount=y1 - y0, dir=(0, 1, 0))


def outline_slab(sdfs, centre, y0, y1, s=0.2, off=0.0, n=160):
    return slab(outline_pts(sdfs, centre, s, off, n), y0, y1)


def _edges_at_y(part, y, tol=0.05):
    return [e for e in part.edges() if abs(C.edge_center(e).Y - y) < tol
            and e.bounding_box().size.Y < tol]


# ---------------------------------------------------------------------------
# Mount outlines (flange shapes; pads are the flange + 3 mm)
# ---------------------------------------------------------------------------
def mag_sdfs(side, grow=0.0):
    x, z = MAG[side]
    return [sd_circle(x, z, 62.0 + grow),
            sd_capsule((x, z - MAG_EAR), (x, z + MAG_EAR), 14.0 + grow)]


def gen_sdfs(grow=0.0):
    return [sd_circle(GEN[0], GEN[1], 64.0 + grow)]


def fuel_sdfs(grow=0.0):
    return [sd_circle(FUEL[0], FUEL[1], 50.0 + grow)]


def starter_sdfs(grow=0.0):
    return [sd_circle(0.0, 0.0, 86.0 + grow)]


def oilp_sdfs(grow=0.0):
    return [sd_rbox(OILP[0], OILP[1], 41.0 + grow, 32.0 + grow, 10.0 + grow)]


def tach_sdfs(grow=0.0):
    return [sd_circle(TACH[0], TACH[1], 28.0 + grow)]


def mount_studs():
    """name -> list of (x, z) stud positions."""
    out = {}
    for side, (x, z) in MAG.items():
        out[f"magneto_{side}"] = [(x, z - MAG_EAR), (x, z + MAG_EAR)]
    out["starter"] = [(76.0 * math.cos(math.radians(22.5 + 45 * j)), 76.0 * math.sin(math.radians(22.5 + 45 * j)))
                      for j in range(8)]
    out["generator"] = [(GEN[0] + 55.0 * math.cos(math.radians(45 + 90 * j)),
                         GEN[1] + 55.0 * math.sin(math.radians(45 + 90 * j))) for j in range(4)]
    out["fuel_pump"] = [(FUEL[0] + 40.0 * math.cos(math.radians(45 + 90 * j)),
                         FUEL[1] + 40.0 * math.sin(math.radians(45 + 90 * j))) for j in range(4)]
    out["oil_pump"] = [(OILP[0] + sx * 31.0, OILP[1] + sz * 23.0) for sx in (-1, 1) for sz in (-1, 1)]
    out["tach"] = [(TACH[0] + 20.0 * math.cos(math.radians(45 + 90 * j)),
                    TACH[1] + 20.0 * math.sin(math.radians(45 + 90 * j))) for j in range(4)]
    return out


MOUNTS = [  # name, sdf fn, centre, stud size, flange thickness
    ("magneto_L", lambda g: mag_sdfs("L", g), MAG["L"], 8.0, 10.0),
    ("magneto_R", lambda g: mag_sdfs("R", g), MAG["R"], 8.0, 10.0),
    ("starter", starter_sdfs, (0.0, 0.0), 8.0, 10.0),
    ("generator", gen_sdfs, GEN, 8.0, 8.0),
    ("fuel_pump", fuel_sdfs, FUEL, 8.0, 8.0),
    ("oil_pump", oilp_sdfs, OILP, 8.0, 8.0),
    ("tach", tach_sdfs, TACH, 6.0, 6.0),
]


# ---------------------------------------------------------------------------
# The case casting
# ---------------------------------------------------------------------------
def body_sdfs(grow=0.0):
    g = grow
    return [sd_circle(0.0, 0.0, 176.0 + g),
            sd_circle(MAG["L"][0], MAG["L"][1], 71.0 + g),
            sd_capsule((MAG["L"][0], MAG["L"][1] - MAG_EAR), (MAG["L"][0], MAG["L"][1] + MAG_EAR), 25.0 + g),
            sd_circle(MAG["R"][0], MAG["R"][1], 71.0 + g),
            sd_capsule((MAG["R"][0], MAG["R"][1] - MAG_EAR), (MAG["R"][0], MAG["R"][1] + MAG_EAR), 25.0 + g),
            sd_circle(GEN[0], GEN[1], 78.0 + g),
            sd_circle(FUEL[0], FUEL[1], 64.0 + g),
            sd_rbox(0.0, RAIL_Z / 2.0, 96.0 + g, -RAIL_Z / 2.0 + g, 22.0)]


Y_BASE = 318.0            # rear face of the base casting; drive towers rise from it to Y_B1
TOWER_GROW = 6.0
OIL_TOWER = (0.0, -192.0, 84.0, 40.0, 14.0)   # gear-pump / sump-rail block (cx, cz, hx, hz, r)
RIB_ANG = (35.0, -35.0)                        # radial ribs from the starter tower (deg from +Z)
RIB_R = (86.0, 162.0)


def _rib_seg(a):
    s_, c_ = math.sin(math.radians(a)), math.cos(math.radians(a))
    return (RIB_R[0] * s_, RIB_R[0] * c_), (RIB_R[1] * s_, RIB_R[1] * c_)


def tower_sdfs():
    out = []
    for name, fn, _, _, _ in MOUNTS:
        if name != "oil_pump":
            out += fn(3.0 + TOWER_GROW)
    out.append(sd_rbox(*OIL_TOWER))
    return out


def _seg_dist(p, a, b):
    vx, vz = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vz) / (vx * vx + vz * vz)))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vz)


def case_bolt_points():
    """Cast bolt bosses on the base face round its outline, clear of towers and ribs; mirror-symmetric."""
    ts = tower_sdfs()
    out = []
    for off in (-14.0, -40.0):
        for p in outline_pts(body_sdfs(), (0.0, -20.0), s=0.1, off=off, n=720):
            if p[0] < 8.0 or p[1] < -200.0 or (p[0] < 34.0 and p[1] > 135.0):
                continue
            if min(min(f(*p) for f in ts), min(f(-p[0], p[1]) for f in ts)) < 10.5:
                continue
            if any(_seg_dist(p, *_rib_seg(a)) < 14.0 for a in RIB_ANG):
                continue
            if out and min(math.dist(p, q) for q in out) < 34.0:
                continue
            out.append(p)
    out = [p for p in out if min(math.dist(p, b) for b in BLANKS[:1]) > 20.0]
    return out + [(-x, z) for x, z in out]


BLANKS = [(95.0, 97.0), (-95.0, 97.0)]       # blanked drive pads (cast boss + machined cover, 3 screws)
BLANK_Y = (Y_BASE - 1.0, Y_BASE + 8.0)


BOSS_Y = (Y_BASE - 1.0, Y_BASE + 5.0)


def case_front():
    f = _arc_pt((NECK_R, Y_FL), 7.0, (-1, 0), (0, 1))
    segs = [("L", (147.0, 266.0)), ("L", (150.0, 263.0)), ("L", (150.0, Y_FACE)), ("L", (232.0, Y_FACE)),
            ("L", (233.5, Y_FACE + 1.5)), ("L", (233.5, Y_FL - 1.5)), ("L", (232.0, Y_FL)),
            ("L", f[0]), ("A", f[1], f[2]), ("L", (NECK_R, Y_B0 + 6.0)), ("L", (0.0, Y_B0 + 6.0))]
    return _rev((0.0, 266.0), segs)


def case():
    import time
    t0 = time.time()
    front = case_front()
    rear = outline_slab(body_sdfs(), (0.0, -20.0), Y_B0, Y_BASE, s=0.1)
    rear, got_r = C.safe_fillet(rear, _edges_at_y(rear, Y_BASE), 8.0, min_r=2.0)
    rear, got_f = C.safe_fillet(rear, _edges_at_y(rear, Y_B0), 4.0, min_r=1.0)
    _INFO["case_rear_fillets"] = (got_r, got_f)
    bead = outline_slab(body_sdfs(0.7), (0.0, -20.0), 303.4, 304.6, s=0.1)
    # drive towers: one per mounted accessory, rising from the base face to the pads
    towers = []
    for name, fn, c, _, _ in MOUNTS:
        if name == "oil_pump":
            continue
        tw = outline_slab(fn(3.0 + TOWER_GROW), c, Y_BASE - 2.0, Y_B1, s=0.25, n=144)
        tw, _ = C.safe_fillet(tw, _edges_at_y(tw, Y_B1), 4.5, min_r=1.0)
        towers.append(tw)
    ox, oz, ohx, ohz, orr = OIL_TOWER
    otw = outline_slab([sd_rbox(*OIL_TOWER)], (ox, oz), Y_B0 + 1.0, Y_B1, s=0.3, n=144)
    otw, _ = C.safe_fillet(otw, _edges_at_y(otw, Y_B1), 4.5, min_r=1.0)
    towers.append(otw)
    # lifting-eye boss on top
    eye_boss = bd.Pos(0, 293.0, 150.0) * bd.Box(46.0, 42.0, 34.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    ee = [e for e in eye_boss.edges() if abs(e.tangent_at(0.5).Z) > 0.99]
    eye_boss, _ = C.safe_fillet(eye_boss, ee, 8.0, min_r=2.0)
    # machined pad bosses (flange + 3 mm), 7 mm proud of the rear face
    pads = [outline_slab(fn(3.0), c, Y_B1 - 1.0, Y_PAD, s=0.25, n=144) for _, fn, c, _, _ in MOUNTS]
    # cast stiffening ribs on the rear face, pad to pad
    ribs = []
    for a in RIB_ANG:
        p0, p1 = _rib_seg(a)
        L = math.dist(p0, p1)
        d = ((p1[0] - p0[0]) / L, 0.0, (p1[1] - p0[1]) / L)
        rb = C.rib(L, 15.0, 10.0, 3.0, end_r=4.0, top_r=3.0)
        ribs.append(geo.plane((p0[0], Y_BASE - 1.0, p0[1]), (0, 1, 0), d).location * rb)
    bosses = [_revp([(0.0, BOSS_Y[0]), (8.5, BOSS_Y[0]), (8.0, BOSS_Y[1] - 1.2), (6.8, BOSS_Y[1]), (0.0, BOSS_Y[1])], x, z)
              for x, z in case_bolt_points()]
    bosses += [_revp([(0.0, BLANK_Y[0]), (15.5, BLANK_Y[0]), (15.1, BLANK_Y[1] - 1.2), (14.3, BLANK_Y[1]),
                      (0.0, BLANK_Y[1])], x, z) for x, z in BLANKS]
    _INFO["case_bolts"] = len(bosses)
    # staged fuses: each stage is one multi-operand boolean (fuse_all falls back pairwise if unsound)
    body = _one(C.fuse_all([rear, bead, eye_boss] + ribs + bosses))
    _INFO["t_fuse_base"] = round(time.time() - t0)
    body = _one(C.fuse_all([body] + towers))
    _INFO["t_fuse_towers"] = round(time.time() - t0)
    body = _one(C.fuse_all([body, front] + pads))
    _INFO["t_case_fuse"] = round(time.time() - t0)
    # holes
    tools = []
    for b in ACC_ANGLES:
        x, _, z = S.inplane(b, ACC_STUD_R)
        tools.append(_yhole(x, z, Y_FACE - 1.0, Y_FL + 1.0, 9.0))
    for name, _, _, d, _ in MOUNTS:
        tap = TAP8 if d == 8.0 else TAP6
        for (x, z) in mount_studs()[name]:
            tools.append(_yhole(x, z, Y_PAD - 13.0, Y_PAD + 1.0, tap))
    tools.append(_cyl((0, EYE_HOLE_Y, 164.0), (0, EYE_HOLE_Y, 185.0), TAP10))
    for x, z in case_bolt_points():
        tools.append(_yhole(x, z, BOSS_Y[1] - 18.0, BOSS_Y[1] + 1.0, TAP6))
    for x, z in BLANKS:
        for a in (90.0, 210.0, 330.0):
            tools.append(_yhole(x + 9.5 * math.cos(math.radians(a)), z + 9.5 * math.sin(math.radians(a)),
                                BLANK_Y[1] - 9.0, BLANK_Y[1] + 1.0, 2 * F._shank_radius(5.0) + 0.1))
    for (x, y) in SUMP_BOLTS:
        tools.append(_cyl((x, y, RAIL_Z - 1.0), (x, y, RAIL_Z + 16.0), TAP6))
    # the smooth-union outline bulges a little below the rail: face it flat
    tools.append(bd.Pos(0, 314.0, RAIL_Z) * bd.Box(400.0, 120.0, 60.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)))
    body = _one(C.cut_all(body, tools))
    _INFO["t_case"] = round(time.time() - t0)
    return body


def _near_pad(e):
    c = C.edge_center(e)
    for _, fn, cen, _, _ in MOUNTS:
        d = min(f(c.X, c.Z) for f in fn(3.0))
        if abs(d) < 6.0:
            return True
    return False


def pad_skin(name, fn, centre, d):
    sk = outline_slab(fn(3.0), centre, Y_PAD, Y_SKIN, s=0.25, n=144)
    holes = [_yhole(x, z, Y_PAD - 1, Y_SKIN + 1, 9.0 if d == 8.0 else 7.0) for x, z in mount_studs()[name]]
    return _one(C.cut_all(sk, holes))


def gasket(name, fn, centre, d):
    g = outline_slab(fn(0.0), centre, Y_SKIN, Y_EQ, s=0.25, n=144)
    holes = [_yhole(x, z, Y_SKIN - 1, Y_EQ + 1, 9.0 if d == 8.0 else 7.0) for x, z in mount_studs()[name]]
    return _one(C.cut_all(g, holes))


# ---------------------------------------------------------------------------
# Magneto (authored for L at (-150, 30); R is its mirror)
# ---------------------------------------------------------------------------
MB_W, MB_H, MB_R = 124.0, 112.0, 22.0    # body section
MB_Y = (Y_EQ + 10.0 - 0.4, 440.0)
MD_R, MD_Y = 64.0, (436.0, 468.0)       # distributor housing
CAP_R = MD_R - 1.0
CAP_Y1 = 494.0


def magneto_flange(side="L"):
    xm, zm = MAG[side]
    fl = outline_slab(mag_sdfs(side), (xm, zm), Y_EQ, Y_EQ + 10.0, s=0.25, n=144)
    fl, _ = C.safe_fillet(fl, _edges_at_y(fl, Y_EQ + 10.0), 1.5, min_r=0.5)
    return _one(fl - [_yhole(xm, zm + sz * MAG_EAR, Y_EQ - 1, Y_EQ + 11, 9.0) for sz in (-1, 1)])


RIB_Z = (-30.0, -18.0, 18.0, 30.0)


def magneto_body(side="L"):
    xm, zm = MAG[side]
    y0 = Y_EQ + 10.0
    sec = bd.Plane(origin=(xm, y0, zm), x_dir=(1, 0, 0), z_dir=(0, 1, 0)) * bd.RectangleRounded(MB_W, MB_H, MB_R)
    box = bd.extrude(sec, amount=MD_Y[0] - y0)
    box, got = C.safe_fillet(box, _edges_at_y(box, MD_Y[0]), 7.0, min_r=2.0)
    box, got2 = C.safe_fillet(box, _edges_at_y(box, y0), 3.0, min_r=1.0)
    _INFO["mag_body_rounds"] = (got, got2)
    ribs = []
    for sx in (-1, 1):
        for rz in RIB_Z:
            rb = bd.Pos(xm + sx * (MB_W / 2.0 + 1.5), 395.0, zm + rz) * bd.Box(4.0, 62.0, 3.2)
            re = [e for e in rb.edges() if abs(e.tangent_at(0.5).Y) < 0.5 and C.edge_center(e).X * sx > (xm + sx * (MB_W / 2.0 + 1.5)) * sx]
            re += [e for e in rb.edges() if abs(e.tangent_at(0.5).Y) > 0.99 and (C.edge_center(e).X - xm) * sx > MB_W / 2.0 + 2.0]
            rb, _ = C.safe_fillet(rb, re, 1.4, min_r=0.4)
            ribs.append(rb)
    housing = _revp([(0.0, MD_Y[0]), (MD_R - 3.0, MD_Y[0]), (MD_R, MD_Y[0] + 3.0), (MD_R, MD_Y[1]),
                     (0.0, MD_Y[1])], xm, zm)
    # clip posts on the housing sides
    posts = [bd.Pos(xm + sx * (MD_R + 1.0), 446.0, zm) * bd.Box(6.0, 6.0, 9.0) for sx in (-1, 1)]
    # distributor lead boss on the housing top, with its threaded spigot
    lboss = _cyl((xm, LEAD_Y, zm + MD_R - 6.0), (xm, LEAD_Y, zm + LEAD_BOSS_Z), 18.0)
    lspig = _cyl((xm, LEAD_Y, zm + LEAD_BOSS_Z - 0.5), (xm, LEAD_Y, zm + LEAD_BOSS_Z + 7.0), 12.0)
    return _one(C.fuse_all([box, housing] + posts + ribs + [lboss, lspig]))


LEAD_Y = 452.0
LEAD_BOSS_Z = 72.0        # boss top above the magneto axis
LEAD_R = 5.0              # braided distributor lead conduit


def lead_nut():
    """Brass ferrule nut on a O12 spigot (z 0..7), sliding on the O10 conduit above."""
    body = F._wrench_head(14.0, 0.0, 13.5, chamfer_bottom=True)
    b1 = bd.Pos(0, 0, -1.0) * bd.Cylinder(6.05, 8.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    b2 = bd.Pos(0, 0, 6.9) * bd.Cylinder(LEAD_R + 0.05, 8.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return bd.Pos(0, 0, 0.5) * _one(C.cut_all(body, [b1, b2]))


def magneto_lead(side="L"):
    """Braided conduit: distributor lead boss -> high-tension outlet horn's rear spigot."""
    xm, zm = MAG[side]
    xh = -TERMINAL_X if xm < 0 else TERMINAL_X
    s0 = (xm, LEAD_Y, zm + LEAD_BOSS_Z + 7.0)
    pts = [s0, (xm, LEAD_Y, TERMINAL_Z), (xh, 432.0, TERMINAL_Z), (xh, 411.0, TERMINAL_Z)]
    return wire_tube(pts, [12.0, 12.0], LEAD_R)


def magneto_cap(side="L"):
    xm, zm = MAG[side]
    a = _arc_pt((CAP_R, CAP_Y1), 13.0, (0, 1), (-1, 0))
    segs = [("L", (CAP_R, MD_Y[1])), ("L", a[0]), ("A", a[1], a[2]), ("L", (0.0, CAP_Y1))]
    cap = _rev((0.0, MD_Y[1]), segs, xm, zm)
    grooves = [_revp([(r0, CAP_Y1 - 0.8), (r0 + 1.6, CAP_Y1 - 0.8), (r0 + 1.6, CAP_Y1 + 1.0), (r0, CAP_Y1 + 1.0)], xm, zm)
               for r0 in (15.0, 30.0)]
    ring = _revp([(CAP_R - 0.6, MD_Y[1] + 3.0), (CAP_R + 0.5, MD_Y[1] + 3.0), (CAP_R + 0.5, MD_Y[1] + 5.0),
                  (CAP_R - 0.6, MD_Y[1] + 5.0)], xm, zm)
    holes = [_yhole(xm + 44.0 * math.cos(math.radians(a)), zm + 44.0 * math.sin(math.radians(a)),
                    CAP_Y1 - 7.0, CAP_Y1 + 1.0, 2 * F._shank_radius(4.0) + 0.1) for a in CAP_SCREW_ANG]
    return _one(C.cut_all(cap, grooves + [ring] + holes))


CAP_SCREW_ANG = (60.0, 120.0, 240.0, 300.0)


def magneto_vent(side="L"):
    xm, zm = MAG[side]
    return _revp([(0.0, CAP_Y1), (11.0, CAP_Y1), (11.0, CAP_Y1 + 3.0), (8.0, CAP_Y1 + 6.0), (0.0, CAP_Y1 + 6.0)], xm, zm)


def magneto_coil_cover(side="L"):
    xm, zm = MAG[side]
    z0 = zm + MB_H / 2.0
    cov = bd.Pos(xm, 366.0, z0) * bd.Box(80.0, 66.0, 12.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    ve = [e for e in cov.edges() if abs(e.tangent_at(0.5).Z) > 0.99]
    cov, _ = C.safe_fillet(cov, ve, 8.0, min_r=2.0)
    te = [e for e in cov.edges() if abs(C.edge_center(e).Z - (z0 + 12.0)) < 0.01]
    cov, _ = C.safe_fillet(cov, te, 3.5, min_r=1.0)
    holes = [_cyl((xm + sx * 32.0, 366.0 + sy, z0 + 2.0), (xm + sx * 32.0, 366.0 + sy, z0 + 13.0), 2 * F._shank_radius(4.0) + 0.1)
             for sx in (-1, 1) for sy in (8.0, 60.0)]
    return _one(cov - holes), [(xm + sx * 32.0, 366.0 + sy, z0 + 12.0) for sx in (-1, 1) for sy in (8.0, 60.0)]


def magneto_outlet(side="L"):
    """High-tension outlet: front face at y 370 on the ignition feed terminal."""
    xm, zm = MAG[side]
    xm = -TERMINAL_X if xm < 0 else TERMINAL_X
    horn = _revp([(0.0, TERMINAL_Y), (21.0, TERMINAL_Y), (21.0, TERMINAL_Y + 6.0), (16.0, TERMINAL_Y + 8.0),
                  (16.0, 398.0), (12.5, 404.0), (6.0, 404.0), (6.0, 411.0), (0.0, 411.0)], xm, TERMINAL_Z)
    z_top = zm + MB_H / 2.0 + 12.0
    neck = _cyl((xm, 390.0, z_top), (xm, 390.0, TERMINAL_Z), 26.0)
    foot = geo.plane((xm, 390.0, z_top), (0, 0, 1), (1, 0, 0)).location * _foot_z(17.0, 13.0, 4.0)
    out = _one(C.fuse_all([horn, neck, foot]))
    return out


def _foot_z(r0, r1, h):
    """Revolved foot about +Z: base radius r0 at z 0, r1 at z h."""
    face = bd.Plane.XZ * bd.Polygon((0, 0), (r0, 0), (r0, 1.2), (r1, h), (0, h), align=None)
    return bd.revolve(face, axis=bd.Axis.Z)


def magneto_clip(side="L", sx=1):
    xm, zm = MAG[side]
    r_run = MD_R + 0.2 + 0.6
    ca = (CAP_R - 13.0, 481.0)
    rr = r_run - ca[0]
    c45 = math.cos(math.radians(45.0))

    def V(r, y):
        return bd.Vector(xm + sx * r, y, zm)
    edges = [bd.Edge.make_line(V(r_run, 449.0), V(r_run, ca[1])),
             bd.Edge.make_three_point_arc(V(r_run, ca[1]), V(ca[0] + rr * c45, ca[1] + rr * c45), V(ca[0], ca[1] + rr)),
             bd.Edge.make_line(V(ca[0], ca[1] + rr), V(22.0, ca[1] + rr))]
    path = bd.Wire(edges)
    prof = bd.Plane(origin=(xm + sx * r_run, 449.0, zm), x_dir=(0, 0, 1), z_dir=(0, 1, 0)) * bd.Rectangle(8.0, 1.2)
    return _one(bd.sweep(prof, path=path, is_frenet=False, transition=bd.Transition.ROUND))


def magneto_ground(side="L"):
    xm, zm = MAG[side]
    sx = -1.0 if xm < 0 else 1.0
    x0 = xm + sx * MB_W / 2.0
    hexb = F._hex_prism(10.0, 0.0, 5.0)
    stud = bd.Cylinder(2.2, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    nut = bd.Pos(0, 0, 7.0) * F._hex_prism(7.0, 0.0, 3.0)
    t = _one(C.fuse_all([hexb, stud, nut]))
    return F.place(t, (x0, 405.0, zm), (sx, 0, 0), (0, 1, 0))


# ---------------------------------------------------------------------------
# Starter (centre pad, axis = crank axis)
# ---------------------------------------------------------------------------
def starter_housing():
    y0 = Y_EQ
    rr = _arc_pt((72.0, 422.0), 8.0, (0, 1), (-1, 0))
    segs = [("L", (84.5, y0)), ("L", (86.0, y0 + 1.5)), ("L", (86.0, y0 + 8.5)), ("L", (84.5, y0 + 10.0)),
            ("L", (60.0, y0 + 10.0)), ("L", (60.0, 362.0)), ("A", (61.8, 367.2), (66.0, 371.0)), ("L", (72.0, 375.0)),
            ("L", rr[0]), ("A", rr[1], rr[2]), ("L", (0.0, 422.0))]
    body = _rev((0.0, y0), segs)
    holes = [_yhole(x, z, y0 - 1, y0 + 11, 9.0) for x, z in mount_studs()["starter"]]
    return _one(C.cut_all(body, holes))


def starter_motor():
    body = _revp([(0.0, 422.0), (56.0, 422.0), (56.0, 468.0), (0.0, 468.0)])
    boss = _cyl((0, 459.0, 48.0), (0, 459.0, 63.0), 16.0)
    fins = [_revp([(55.0, y), (59.0, y + 0.8), (59.0, y + 1.8), (55.0, y + 2.6)]) for y in (425.0, 430.0)]
    return _one(C.fuse_all([body, boss] + fins))


def starter_end_bell():
    a = _arc_pt((56.0, 484.0), 12.0, (0, 1), (-1, 0))
    segs = [("L", (56.0, 468.0)), ("L", a[0]), ("A", a[1], a[2]), ("L", (17.0, 484.0)), ("L", (17.0, 492.0)),
            ("L", (0.0, 492.0))]
    bell = _rev((0.0, 468.0), segs)
    grooves = [_revp([(r0, 483.2), (r0 + 1.4, 483.2), (r0 + 1.4, 485.0), (r0, 485.0)]) for r0 in (24.0, 34.0)]
    holes = [_yhole(40.0 * math.cos(math.radians(a)), 40.0 * math.sin(math.radians(a)), 477.0, 485.0,
                    2 * F._shank_radius(4.0) + 0.1) for a in range(30, 360, 60)]
    return _one(C.cut_all(bell, grooves + holes))


def starter_housing_band():
    return _revp([(72.05, 386.0), (74.8, 386.0), (75.6, 387.5), (75.6, 396.5), (74.8, 398.0), (72.05, 398.0)])


def starter_band():
    band = _revp([(56.05, 436.0), (58.0, 436.0), (58.0, 450.0), (56.05, 450.0)])
    lug = bd.Pos(62.5, 443.0, 0) * bd.Box(10.0, 10.0, 10.0)
    lug = lug - _cyl((63.5, 443.0, -6.0), (63.5, 443.0, 6.0), 2 * F._shank_radius(5.0) + 0.1)
    return _one(C.fuse_all([band, lug]))


def starter_band_screw():
    b = F.socket_cap_bolt(5.0, 8.0)
    return F.place(b, (63.5, 443.0, 5.0), (0, 0, 1), (1, 0, 0))


def starter_jaw():
    j = _revp([(0.0, 492.0), (12.0, 492.0), (12.0, 510.0), (11.0, 511.0), (0.0, 511.0)])
    slots = [bd.Pos(0, 507.0, 0) * bd.Rot(0, a, 0) * bd.Box(30.0, 10.0, 5.0) for a in (0.0, 90.0)]
    return _one(C.cut_all(j, [C.fuse_all(slots)]))


def starter_terminal():
    hexn = F._hex_prism(11.0, 0.0, 5.0)
    stud = bd.Cylinder(2.5, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    t = _one(C.fuse_all([hexn, stud]))
    return F.place(t, (0.0, 459.0, 63.0), (0, 0, 1), (1, 0, 0))


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------
def generator_flange():
    gx, gz = GEN
    y0 = Y_EQ
    fl = _revp([(20.0, y0), (62.5, y0), (64.0, y0 + 1.5), (64.0, y0 + 6.5), (62.5, y0 + 8.0), (20.0, y0 + 8.0)], gx, gz)
    holes = [_yhole(x, z, y0 - 1, y0 + 9, 9.0) for x, z in mount_studs()["generator"]]
    return _one(C.cut_all(fl, holes))


def generator_body():
    gx, gz = GEN
    y0 = Y_EQ + 8.0
    segs = [("L", (42.0, y0)), ("L", (42.0, 364.0)), ("A", (43.3, 368.0), (46.0, 371.0)), ("L", (50.0, 375.0)),
            ("L", (50.0, 478.0)), ("L", (51.6, 479.5)), ("L", (51.6, 484.5)), ("L", (50.0, 486.0)),
            ("L", (50.0, 506.0)), ("L", (0.0, 506.0))]
    body = _rev((0.0, y0), segs, gx, gz)
    tb = bd.Pos(gx, 398.0, gz + 40.0) * bd.Box(30.0, 34.0, 20.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    ve = [e for e in tb.edges() if abs(e.tangent_at(0.5).Z) > 0.99 or abs(e.tangent_at(0.5).Y) > 0.99]
    tb, _ = C.safe_fillet(tb, ve, 4.0, min_r=1.0)
    spig = _revp([(0.0, Y_EQ + 0.5), (19.9, Y_EQ + 0.5), (19.9, y0 + 0.1), (0.0, y0 + 0.1)], gx, gz)
    return _one(C.fuse_all([body, tb, spig]))


def generator_end_bell():
    gx, gz = GEN
    a = _arc_pt((50.0, 526.0), 14.0, (0, 1), (-1, 0))
    segs = [("L", (50.0, 506.0)), ("L", a[0]), ("A", a[1], a[2]), ("L", (21.0, 526.0)), ("L", (21.0, 542.0)),
            ("L", (19.5, 543.5)), ("L", (15.0, 543.5)), ("L", (15.0, 530.0)), ("L", (0.0, 530.0))]
    bell = _rev((0.0, 506.0), segs, gx, gz)
    holes = [_yhole(gx + 29.0 * math.cos(math.radians(a)), gz + 29.0 * math.sin(math.radians(a)), 519.0, 527.0,
                    2 * F._shank_radius(4.0) + 0.1) for a in range(0, 360, 60)]
    return _one(C.cut_all(bell, holes))


def generator_band():
    gx, gz = GEN
    band = _revp([(50.05, 450.0), (52.0, 450.0), (52.0, 466.0), (50.05, 466.0)], gx, gz)
    return band


def generator_posts():
    gx, gz = GEN
    hexn = F._hex_prism(9.0, 0.0, 4.0)
    stud = bd.Cylinder(2.0, 11.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    t = _one(C.fuse_all([hexn, stud]))
    return [F.place(t, (gx + sx * 7.0, 415.0, gz + 60.0), (0, 0, 1), (1, 0, 0)) for sx in (-1, 1)]


# ---------------------------------------------------------------------------
# Fuel pump
# ---------------------------------------------------------------------------
FP_FIT_Y = 384.0


def fuel_pump_body():
    fx, fz = FUEL
    y0 = Y_EQ
    rr = _arc_pt((38.0, 398.0), 6.0, (0, 1), (-1, 0))
    segs = [("L", (48.5, y0)), ("L", (50.0, y0 + 1.5)), ("L", (50.0, y0 + 6.5)), ("L", (48.5, y0 + 8.0)),
            ("L", (27.0, y0 + 8.0)), ("L", (27.0, 364.0)), ("A", (28.2, 367.4), (31.0, 370.0)), ("L", (38.0, 374.0)),
            ("L", rr[0]), ("A", rr[1], rr[2]), ("L", (0.0, 398.0))]
    body = _rev((0.0, y0), segs, fx, fz)
    b_in = _cyl((fx + 30.0, FP_FIT_Y, fz), (fx + 46.0, FP_FIT_Y, fz), 20.0)
    b_out = _cyl((fx, FP_FIT_Y, fz - 30.0), (fx, FP_FIT_Y, fz - 46.0), 20.0)
    body = _one(C.fuse_all([body, b_in, b_out]))
    holes = [_yhole(x, z, y0 - 1, y0 + 9, 9.0) for x, z in mount_studs()["fuel_pump"]]
    holes += [_cyl((fx + 36.0, FP_FIT_Y, fz), (fx + 47.0, FP_FIT_Y, fz), TAP10),
              _cyl((fx, FP_FIT_Y, fz - 36.0), (fx, FP_FIT_Y, fz - 47.0), TAP10)]
    return _one(C.cut_all(body, holes))


def fuel_pump_relief():
    fx, fz = FUEL
    h = F._wrench_head(30.0, 0.0, 10.0, chamfer_bottom=True)
    dome = _foot_z(13.0, 9.0, 8.0)
    dome = bd.Pos(0, 0, 10.0) * dome
    screw = bd.Pos(0, 0, 17.0) * bd.Cylinder(4.0, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lock = bd.Pos(0, 0, 18.0) * F._wrench_head(12.0, 0.0, 5.0, chamfer_bottom=True)
    t = _one(C.fuse_all([h, dome, screw, lock]))
    return F.place(t, (fx, 398.0, fz), (0, 1, 0), (1, 0, 0))


def _nipple(d_boss=10.0):
    """AN union nipple, seat at z 0 on a boss face: thread shank below, hex, flare spigot."""
    shank = bd.Pos(0, 0, -9.0) * bd.Cylinder(F._shank_radius(d_boss), 9.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    hexb = F._wrench_head(16.0, 0.0, 7.0, chamfer_bottom=True)
    spig = _foot_z(6.0, 5.2, 9.0)
    spig = bd.Pos(0, 0, 7.0) * bd.Cylinder(5.5, 9.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body = _one(C.fuse_all([shank, hexb, spig]))
    bore = bd.Pos(0, 0, -10.0) * bd.Cylinder(2.5, 30.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return _one(body - bore)


def _dust_cap():
    """Cap threaded over the nipple spigot (spigot z 7..16 from the nipple seat)."""
    h = F._wrench_head(16.0, 0.0, 10.0, chamfer_bottom=True)
    dome = bd.Pos(0, 0, 10.0) * _foot_z(8.0, 5.0, 3.0)
    t = _one(C.fuse_all([h, dome]))
    bore = bd.Pos(0, 0, -1.0) * bd.Cylinder(5.55, 10.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return bd.Pos(0, 0, 7.5) * _one(t - bore)


def carb_bnut():
    """B-nut threaded on the carburettor's brass inlet nipple (their flare tip at y 144.8), O8 fuel tube."""
    x, z = CARB_FUEL[0], CARB_FUEL[2]
    body = F._wrench_head(16.0, 0.0, 22.5, chamfer_bottom=True)
    b1 = bd.Pos(0, 0, -1.0) * bd.Cylinder(4.05, 9.7, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    b2 = bd.Pos(0, 0, 8.6) * bd.Cylinder(8.1, 15.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return F.place(_one(C.cut_all(body, [b1, b2])), (x, CARB_FUEL[1] - 8.8, z), (0, 1, 0), (1, 0, 0))


# intake:carb_fuel_inlet flare tip: their FUEL_IN + CARB_SHIFT = (-37, 200, -457), nipple along -Y, tip 29.2 ahead
CARB_FUEL = (-37.0, 170.8, -457.0)


def _bnut():
    """B-nut threaded on the nipple spigot, bore sliding on an O8 tube; seat z 7.5 of the nipple frame."""
    body = F._wrench_head(14.0, 0.0, 14.0, chamfer_bottom=True)
    bore1 = bd.Pos(0, 0, -1.0) * bd.Cylinder(5.55, 9.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    bore2 = bd.Pos(0, 0, 8.4) * bd.Cylinder(4.05, 7.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return bd.Pos(0, 0, 7.5) * _one(C.cut_all(body, [bore1, bore2]))


# ---------------------------------------------------------------------------
# Oil pump
# ---------------------------------------------------------------------------
OP_BODY = (40.0, 44.0)       # w, h
OP_Y = (Y_EQ + 8.0 - 0.4, 390.0)
OP_OUT = (OILP[0] - 10.0, 372.0)   # (x, y) of the outlet on the pump bottom


def oil_pump_body():
    ox, oz = OILP
    fl = outline_slab(oilp_sdfs(), OILP, Y_EQ, Y_EQ + 8.0, s=0.3, n=144)
    fl, _ = C.safe_fillet(fl, _edges_at_y(fl, Y_EQ + 8.0), 1.5, min_r=0.5)
    sec = bd.Plane(origin=(ox, OP_Y[0], oz), x_dir=(1, 0, 0), z_dir=(0, 1, 0)) * bd.RectangleRounded(*OP_BODY, 8.0)
    box = bd.extrude(sec, amount=OP_Y[1] - OP_Y[0])
    zb = oz - OP_BODY[1] / 2.0
    b_out = _cyl((OP_OUT[0], OP_OUT[1], zb + 2.0), (OP_OUT[0], OP_OUT[1], zb - 6.0), 20.0)
    b_in = _cyl((ox + OP_BODY[0] / 2.0 - 2.0, 375.0, oz - 4.0), (ox + OP_BODY[0] / 2.0 + 6.0, 375.0, oz - 4.0), 20.0)
    body = _one(C.fuse_all([fl, box, b_out, b_in]))
    tools = [_yhole(x, z, Y_EQ - 1, Y_EQ + 9, 9.0) for x, z in mount_studs()["oil_pump"]]
    tools += [_cyl((OP_OUT[0], OP_OUT[1], zb - 7.0), (OP_OUT[0], OP_OUT[1], zb + 4.0), TAP10),
              _cyl((ox + OP_BODY[0] / 2.0 + 7.0, 375.0, oz - 4.0), (ox + OP_BODY[0] / 2.0 - 4.0, 375.0, oz - 4.0), TAP10)]
    tools += [_yhole(ox + sx * 11.0, oz + sz * 12.0, OP_Y[1] - 9.0, OP_Y[1] + 1.0, TAP6) for sx in (-1, 1) for sz in (-1, 1)]
    return _one(C.cut_all(body, tools))


def oil_pump_cover():
    ox, oz = OILP
    sec = bd.Plane(origin=(ox, OP_Y[1], oz), x_dir=(1, 0, 0), z_dir=(0, 1, 0)) * bd.RectangleRounded(*OP_BODY, 8.0)
    cov = bd.extrude(sec, amount=6.0)
    cov, _ = C.safe_fillet(cov, _edges_at_y(cov, OP_Y[1] + 6.0), 1.5, min_r=0.5)
    holes = [_yhole(ox + sx * 11.0, oz + sz * 12.0, OP_Y[1] - 1.0, OP_Y[1] + 7.0, 6.6) for sx in (-1, 1) for sz in (-1, 1)]
    return _one(C.cut_all(cov, holes))


def drilled_bolt(d, length):
    b = F.hex_flange_bolt(d, length)
    k = F._key(d)
    s, dc, head_h, c = F._FLANGE_BOLT[k]
    zh = c + (head_h - c) * 0.5
    return b - _cyl((-s, 0.0, zh), (s, 0.0, zh), 1.6), zh


def wire_tube(pts, radii, r):
    """Tube of radius r swept along a filleted polyline (lines + true arcs)."""
    edges = []
    prev = pts[0]
    for i in range(1, len(pts) - 1):
        c = pts[i]
        d_in = _unit(_sub(c, pts[i - 1]))
        d_out = _unit(_sub(pts[i + 1], c))
        th = math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(d_in, d_out)))))
        if th < 1e-4:
            continue
        R = radii[i - 1]
        tl = R * math.tan(th / 2.0)
        a = _add(c, d_in, -tl)
        b = _add(c, d_out, tl)
        u = _unit(_sub(d_out, d_in))
        mid = _add(c, u, R / math.cos(th / 2.0) - R)
        if math.dist(a, prev) > 1e-6:
            edges.append(bd.Edge.make_line(bd.Vector(*prev), bd.Vector(*a)))
        edges.append(bd.Edge.make_three_point_arc(bd.Vector(*a), bd.Vector(*mid), bd.Vector(*b)))
        prev = b
    edges.append(bd.Edge.make_line(bd.Vector(*prev), bd.Vector(*pts[-1])))
    w = bd.Wire(edges)
    e0 = w.edges()[0]
    prof = bd.Plane(origin=e0.position_at(0.0), z_dir=e0.tangent_at(0.0)) * bd.Circle(r)
    return _one(bd.sweep(prof, path=w, is_frenet=False, transition=bd.Transition.ROUND))


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _add(a, b, s=1.0):
    return tuple(x + s * y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Sump (under the case rail) with the oil-screen housing
# ---------------------------------------------------------------------------
SUMP_LIP = (76.0, 291.0, 337.0)          # half-width x, y0, y1
SUMP_BOLTS = [(sx * 68.0, y) for sx in (-1, 1) for y in (299.0, 314.0, 329.0)]
SUMP_Z = (RAIL_Z - 8.0, -284.0)         # lip bottom, tub bottom
SUMP_RET = (30.0, 340.0, -275.0)       # scavenge-return boss face on the sump's rear wall (+Y)
SCREEN_X, SCREEN_Y = -36.0, 314.0      # oil-screen housing under the tub, axis -Z
SCREEN_FACE_Z = -298.0                  # housing face (cap seat)
SCREEN_IN_Z = -289.0                    # rear-facing inlet boss axis height


def sump():
    hx, y0, y1 = SUMP_LIP
    zl = SUMP_Z[0]
    lip = bd.Pos(0, y0, zl) * bd.Box(2 * hx, y1 - y0, RAIL_Z - zl, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    le = [e for e in lip.edges() if abs(e.tangent_at(0.5).Z) > 0.99]
    lip, _ = C.safe_fillet(lip, le, 10.0, min_r=2.0)
    # tub: loft of two rounded rectangles (drafted)
    top = bd.Plane(origin=(0, 314.0, zl + 0.5), x_dir=(1, 0, 0), z_dir=(0, 0, 1)) * bd.RectangleRounded(118.0, 34.0, 12.0)
    bot = bd.Plane(origin=(0, 314.0, SUMP_Z[1]), x_dir=(1, 0, 0), z_dir=(0, 0, 1)) * bd.RectangleRounded(104.0, 28.0, 10.0)
    tub = bd.loft([bot.faces()[0], top.faces()[0]])
    # fins on the rear face and the bottom
    fins = []
    for z in (-246.0, -256.0, -266.0):
        f = bd.Pos(0, 322.0, z) * bd.Box(96.0 - (z + 246.0) * -0.4, 16.0, 2.6, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
        fe = [e for e in f.edges() if abs(e.tangent_at(0.5).Z) > 0.99]
        f, _ = C.safe_fillet(f, fe, 1.25, min_r=0.3)
        fins.append(f)
    # bottom drain boss + wire lug
    boss = _cyl((0, 314.0, SUMP_Z[1] + 2.0), (0, 314.0, SUMP_Z[1] - 6.0), 24.0)
    # oil-screen housing on the -X wall, with a rear-facing inlet boss
    housing = _cyl((SCREEN_X, SCREEN_Y, SUMP_Z[1] + 2.0), (SCREEN_X, SCREEN_Y, SCREEN_FACE_Z), 36.0)
    inlet = _cyl((SCREEN_X, SCREEN_Y, SCREEN_IN_Z), (SCREEN_X, 338.0, SCREEN_IN_Z), 16.0)
    ret = _cyl((SUMP_RET[0], 320.0, SUMP_RET[2]), (SUMP_RET[0], SUMP_RET[1], SUMP_RET[2]), 14.0)
    body = _one(C.fuse_all([lip, tub, boss] + fins + [housing, inlet, ret]))
    tools = [_cyl((x, y, zl - 1.0), (x, y, RAIL_Z + 1.0), 6.6) for x, y in SUMP_BOLTS]
    tools.append(_cyl((0, 314.0, SUMP_Z[1] - 7.0), (0, 314.0, SUMP_Z[1] + 6.0), TAP10))
    tools.append(_cyl((SCREEN_X, SCREEN_Y, SCREEN_FACE_Z - 1.0), (SCREEN_X, SCREEN_Y, SCREEN_FACE_Z + 12.0),
                      2 * F._shank_radius(16.0) + 0.05))
    tools.append(_cyl((SCREEN_X, 327.0, SCREEN_IN_Z), (SCREEN_X, 339.0, SCREEN_IN_Z), TAP10))
    tools.append(_cyl((SUMP_RET[0], SUMP_RET[1] - 11.0, SUMP_RET[2]), (SUMP_RET[0], SUMP_RET[1] + 1.0, SUMP_RET[2]), TAP10))
    return _one(C.cut_all(body, tools))


def screen_cap():
    """Oil-screen cap: hex plug with a drilled corner for the wire."""
    h = F._wrench_head(27.0, 0.0, 11.0, chamfer_bottom=True)
    flange = _foot_z(17.0, 16.0, 2.0)
    shank = bd.Pos(0, 0, -11.0) * bd.Cylinder(F._shank_radius(16.0), 11.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    t = _one(C.fuse_all([flange, bd.Pos(0, 0, 1.5) * h, shank]))
    t = t - _cyl((-20.0, 0.0, 7.0), (20.0, 0.0, 7.0), 1.6)
    return F.place(t, (SCREEN_X, SCREEN_Y, SCREEN_FACE_Z), (0, 0, -1), (1, 0, 0))


# ---------------------------------------------------------------------------
# Lifting eye
# ---------------------------------------------------------------------------
EYE_HOLE_Y = 304.0
EYE_Z = 184.0


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def nut(d):
    """Flange nut whose bore clears the (pitch-diameter) stud shank: no thread overlap."""
    n = F.flange_nut(d)
    return _one(n - bd.Pos(0, 0, -1.0) * bd.Cylinder(F._shank_radius(d) + 0.04, 30.0,
                                                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))


def _mirror_x(shape):
    return bd.mirror(shape, about=bd.Plane.YZ)


def build() -> list:
    import time
    t0 = time.time()
    CS, MA, MB, FA, SW, BR, CU, SP, GK = (P.CASE_SILVER, P.MACHINED_ALU, P.MAGNETO_BLACK, P.FASTENER,
                                          P.SAFETY_WIRE, P.BRASS, P.COPPER, P.STEEL_POLISHED, P.GASKET)
    parts = []
    parts.append(_st(case(), "accessory:case", CS))
    _INFO["t_case_total"] = round(time.time() - t0)
    studs = mount_studs()
    stud8 = {}
    for name, fn, cen, d, ft in MOUNTS:
        parts.append(_st(pad_skin(name, fn, cen, d), f"accessory:{name}_pad", MA))
        parts.append(_st(gasket(name, fn, cen, d), f"accessory:{name}_gasket", GK))
        nutp = nut(d)
        nut_h = F._FLANGE_NUT[F._key(d)][2]
        out = Y_EQ + ft + nut_h + 1.6 - Y_PAD
        key = (d, round(out, 2))
        if key not in stud8:
            stud8[key] = F.stud(d, out, 12.0)
        for i, (x, z) in enumerate(studs[name], start=1):
            radial = (x - cen[0], 0.0, z - cen[1])
            if math.hypot(radial[0], radial[2]) < 1e-6:
                radial = (1.0, 0.0, 0.0)
            parts.append(_st(F.place(stud8[key], (x, Y_PAD, z), (0, 1, 0), radial), f"accessory:{name}_stud_{i}", FA))
            parts.append(_st(F.place(nutp, (x, Y_EQ + ft, z), (0, 1, 0), radial), f"accessory:{name}_nut_{i}", FA))
    # --- magnetos
    body = magneto_body("L")
    mflange = magneto_flange("L")
    cap = magneto_cap("L")
    vent = magneto_vent("L")
    cover, screw_pts = magneto_coil_cover("L")
    outlet = magneto_outlet("L")
    clips = [magneto_clip("L", sx) for sx in (-1, 1)]
    ground = magneto_ground("L")
    screw = F.socket_cap_bolt(4.0, 8.0)
    mag_parts = [(body, "magneto_{s}", MB), (mflange, "magneto_{s}_flange", MA), (cap, "magneto_{s}_cap", MA),
                 (vent, "magneto_{s}_vent", BR), (cover, "magneto_{s}_coil_cover", MA), (outlet, "magneto_{s}_outlet", MA),
                 (clips[0], "magneto_{s}_cap_clip_1", SP), (clips[1], "magneto_{s}_cap_clip_2", SP),
                 (ground, "magneto_{s}_ground_terminal", BR)]
    for i, p in enumerate(screw_pts, start=1):
        mag_parts.append((F.place(screw, p, (0, 0, 1), (1, 0, 0)), f"magneto_{{s}}_cover_screw_{i}", FA))
    xm0, zm0 = MAG["L"]
    for i, a in enumerate(CAP_SCREW_ANG, start=1):
        pt = (xm0 + 44.0 * math.cos(math.radians(a)), CAP_Y1, zm0 + 44.0 * math.sin(math.radians(a)))
        mag_parts.append((F.place(F.socket_cap_bolt(4.0, 6.0), pt, (0, 1, 0), (1, 0, 0)), f"magneto_{{s}}_cap_screw_{i}", FA))
    ln = lead_nut()
    mag_parts.append((F.place(ln, (xm0, LEAD_Y, zm0 + LEAD_BOSS_Z), (0, 0, 1), (1, 0, 0)), "magneto_{s}_lead_nut", BR))
    mag_parts.append((F.place(ln, (-TERMINAL_X, 404.0, TERMINAL_Z), (0, 1, 0), (1, 0, 0)), "magneto_{s}_outlet_nut", BR))
    mag_parts.append((magneto_lead("L"), "magneto_{s}_lead", P.BRAID))
    for shp, lab, col in mag_parts:
        parts.append(_st(shp, "accessory:" + lab.format(s="L"), col))
        parts.append(_st(_mirror_x(shp), "accessory:" + lab.format(s="R"), col))
    # --- starter
    parts.append(_st(starter_housing(), "accessory:starter_housing", CS))
    parts.append(_st(starter_motor(), "accessory:starter_motor", MB))
    parts.append(_st(starter_end_bell(), "accessory:starter_end_bell", MA))
    s4 = F.socket_cap_bolt(4.0, 6.0)
    for i, a in enumerate(range(30, 360, 60), start=1):
        parts.append(_st(F.place(s4, (40.0 * math.cos(math.radians(a)), 484.0, 40.0 * math.sin(math.radians(a))),
                                 (0, 1, 0), (1, 0, 0)), f"accessory:starter_end_bell_screw_{i}", FA))
    parts.append(_st(starter_housing_band(), "accessory:starter_housing_band", SP))
    parts.append(_st(starter_band(), "accessory:starter_band_clamp", SP))
    parts.append(_st(starter_band_screw(), "accessory:starter_band_screw", FA))
    parts.append(_st(starter_jaw(), "accessory:starter_jaw", SP))
    parts.append(_st(starter_terminal(), "accessory:starter_terminal", BR))
    # --- generator
    parts.append(_st(generator_flange(), "accessory:generator_flange", MA))
    parts.append(_st(generator_body(), "accessory:generator", MB))
    parts.append(_st(generator_end_bell(), "accessory:generator_end_bell", MA))
    for i, a in enumerate(range(0, 360, 60), start=1):
        parts.append(_st(F.place(F.socket_cap_bolt(4.0, 6.0), (GEN[0] + 29.0 * math.cos(math.radians(a)), 526.0,
                                                               GEN[1] + 29.0 * math.sin(math.radians(a))), (0, 1, 0), (1, 0, 0)),
                         f"accessory:generator_end_bell_screw_{i}", FA))
    parts.append(_st(generator_band(), "accessory:generator_band_clamp", SP))
    for i, p in enumerate(generator_posts(), start=1):
        parts.append(_st(p, f"accessory:generator_terminal_{i}", BR))
    # --- fuel pump
    fx, fz = FUEL
    parts.append(_st(fuel_pump_body(), "accessory:fuel_pump", CS))
    parts.append(_st(fuel_pump_relief(), "accessory:fuel_pump_relief_valve", SP))
    nip, capn = _nipple(), _dust_cap()
    for tag, pt, dirn, xd in (("inlet", (fx + 46.0, FP_FIT_Y, fz), (1, 0, 0), (0, 1, 0)),
                              ("outlet", (fx, FP_FIT_Y, fz - 46.0), (0, 0, -1), (0, 1, 0))):
        parts.append(_st(F.place(nip, pt, dirn, xd), f"accessory:fuel_pump_{tag}_fitting", BR))
        if tag == "inlet":
            parts.append(_st(F.place(capn, pt, dirn, xd), f"accessory:fuel_pump_{tag}_cap", BR))
        else:
            parts.append(_st(F.place(_bnut(), pt, dirn, xd), "accessory:fuel_pump_outlet_bnut", BR))
    # fuel line: pump outlet -> down and across behind the carburettor -> forward in the lane between the
    # carburettor and cylinder 5's intake pipe (clear of cylinder 6's elbow) -> its inlet from the front
    fp0 = (fx, FP_FIT_Y, fz - 46.0 - 16.0)
    fuel = wire_tube([fp0, (fx, FP_FIT_Y, -330.0), (-86.0, 320.0, -420.0), (-86.0, 165.0, -425.0),
                      (CARB_FUEL[0], 140.0, CARB_FUEL[2]), CARB_FUEL], [25.0, 20.0, 15.0, 10.0], 4.0)
    parts.append(_st(fuel, "accessory:fuel_line", SP))
    parts.append(_st(carb_bnut(), "accessory:fuel_line_carb_bnut", BR))
    # --- oil pump
    ox, oz = OILP
    parts.append(_st(oil_pump_body(), "accessory:oil_pump", CS))
    parts.append(_st(oil_pump_cover(), "accessory:oil_pump_cover", MA))
    dbolt, zh = drilled_bolt(6.0, 10.0)
    for i, (sx, sz) in enumerate(((-1, 1), (1, 1), (-1, -1), (1, -1)), start=1):
        parts.append(_st(F.place(dbolt, (ox + sx * 11.0, OP_Y[1] + 6.0, oz + sz * 12.0), (0, 1, 0), (1, 0, 0)),
                         f"accessory:oil_pump_cover_bolt_{i}", FA))
    yw = OP_Y[1] + 6.0 + zh
    for j, sz in enumerate((1, -1), start=1):
        z = oz + sz * 12.0
        pts = [(ox - 21.0, yw, z), (ox - 4.2, yw, z), (ox, yw + 2.2, z - sz * 1.5), (ox + 4.2, yw, z), (ox + 21.0, yw, z)]
        parts.append(_st(wire_tube(pts, [2.5, 2.5, 2.5], 0.4), f"accessory:oil_pump_cover_wire_{j}", SW))
    zb = oz - OP_BODY[1] / 2.0
    bnut = _bnut()
    out_pt = (OP_OUT[0], OP_OUT[1], zb - 6.0)
    parts.append(_st(F.place(nip, out_pt, (0, 0, -1), (0, 1, 0)), "accessory:oil_pump_outlet_fitting", BR))
    parts.append(_st(F.place(bnut, out_pt, (0, 0, -1), (0, 1, 0)), "accessory:oil_pump_outlet_bnut", BR))
    in_pt = (ox + OP_BODY[0] / 2.0 + 6.0, 375.0, oz - 4.0)
    parts.append(_st(F.place(nip, in_pt, (1, 0, 0), (0, 1, 0)), "accessory:oil_pump_inlet_fitting", BR))
    parts.append(_st(F.place(bnut, in_pt, (1, 0, 0), (0, 1, 0)), "accessory:oil_pump_inlet_bnut", BR))
    parts.append(_st(F.place(nip, SUMP_RET, (0, 1, 0), (1, 0, 0)), "accessory:sump_return_fitting", BR))
    parts.append(_st(F.place(bnut, SUMP_RET, (0, 1, 0), (1, 0, 0)), "accessory:sump_return_bnut", BR))
    q0 = (in_pt[0] + 16.0, in_pt[1], in_pt[2])
    q1 = (SUMP_RET[0], SUMP_RET[1] + 16.0, SUMP_RET[2])
    ret = wire_tube([q0, (66.0, in_pt[1], in_pt[2]), (q1[0], 380.0, q1[2]), q1], [8.0, 10.0], 4.0)
    parts.append(_st(ret, "accessory:oil_return_line", CU))
    # --- sump + oil screen + oil line
    parts.append(_st(sump(), "accessory:sump", CS))
    sb = F.hex_flange_bolt(6.0, 22.0)
    for i, (x, y) in enumerate(SUMP_BOLTS, start=1):
        parts.append(_st(F.place(sb, (x, y, SUMP_Z[0]), (0, 0, -1), (1, 0, 0)), f"accessory:sump_bolt_{i}", FA))
    dplug, zh10 = drilled_bolt(10.0, 11.0)
    parts.append(_st(F.place(dplug, (0, 314.0, SUMP_Z[1] - 6.0), (0, 0, -1), (1, 0, 0)), "accessory:sump_drain_bolt", FA))
    zp = SUMP_Z[1] - 6.0 - zh10
    parts.append(_st(screen_cap(), "accessory:oil_screen_cap", SP))
    zc = SCREEN_FACE_Z - 7.0
    # one wire: oil-screen cap -> drain plug (each tightening pulls the other)
    parts.append(_st(wire_tube([(SCREEN_X - 20.0, SCREEN_Y, zc), (-16.0, SCREEN_Y, zc), (-11.0, SCREEN_Y, zp),
                                (14.0, SCREEN_Y, zp)], [2.5, 2.5], 0.4), "accessory:sump_drain_wire", SW))
    in_screen = (SCREEN_X, 338.0, SCREEN_IN_Z)
    parts.append(_st(F.place(nip, in_screen, (0, 1, 0), (1, 0, 0)), "accessory:oil_screen_fitting", BR))
    parts.append(_st(F.place(bnut, in_screen, (0, 1, 0), (1, 0, 0)), "accessory:oil_screen_bnut", BR))
    p0 = (out_pt[0], out_pt[1], out_pt[2] - 16.0)
    p1 = (SCREEN_X, 338.0 + 16.0, SCREEN_IN_Z)
    line = wire_tube([p0, (p0[0], p0[1], -255.0), (SCREEN_X, 372.0, SCREEN_IN_Z), p1], [16.0, 12.0], 4.0)
    parts.append(_st(line, "accessory:oil_line", CU))
    # --- tach cover
    tx, tz = TACH
    tc = _revp([(0.0, Y_EQ), (27.0, Y_EQ), (28.0, Y_EQ + 1.0), (28.0, Y_EQ + 5.0), (27.0, Y_EQ + 6.0), (11.0, Y_EQ + 6.0),
                (11.0, Y_EQ + 11.0), (9.0, Y_EQ + 13.0), (0.0, Y_EQ + 13.0)], tx, tz)
    tc = _one(tc - [_yhole(x, z, Y_EQ - 1, Y_EQ + 7, 7.0) for x, z in studs["tach"]])
    parts.append(_st(tc, "accessory:tach_cover", MA))
    # --- case cover bolts in the cast bosses
    cb = F.hex_flange_bolt(6.0, 14.0)
    for i, (x, z) in enumerate(case_bolt_points(), start=1):
        rad = (x, 0.0, z) if math.hypot(x, z) > 1e-6 else (1.0, 0.0, 0.0)
        parts.append(_st(F.place(cb, (x, BOSS_Y[1], z), (0, 1, 0), rad), f"accessory:case_bolt_{i}", FA))
    # --- blanking covers on the spare drive pads
    for j, (x, z) in enumerate(BLANKS, start=1):
        cov = _revp([(0.0, BLANK_Y[1]), (13.5, BLANK_Y[1]), (14.0, BLANK_Y[1] + 0.5), (14.0, BLANK_Y[1] + 2.5),
                     (13.0, BLANK_Y[1] + 3.5), (4.0, BLANK_Y[1] + 3.5), (3.0, BLANK_Y[1] + 4.5), (0.0, BLANK_Y[1] + 4.5)], x, z)
        hs = [(x + 9.5 * math.cos(math.radians(a)), z + 9.5 * math.sin(math.radians(a))) for a in (90.0, 210.0, 330.0)]
        cov = _one(cov - [_yhole(hx, hz, BLANK_Y[1] - 1, BLANK_Y[1] + 5, 5.6) for hx, hz in hs])
        parts.append(_st(cov, f"accessory:blank_cover_{j}", MA))
        for i, (hx, hz) in enumerate(hs, start=1):
            parts.append(_st(F.place(F.socket_cap_bolt(5.0, 10.0), (hx, BLANK_Y[1] + 3.5, hz), (0, 1, 0), (1, 0, 0)),
                             f"accessory:blank_cover_{j}_bolt_{i}", FA))
    # --- lifting eye
    eye = F.lifting_eye()
    parts.append(_st(F.place(eye, (0.0, EYE_HOLE_Y, EYE_Z), (0, 0, 1), (0, 1, 0)), "accessory:lifting_eye", SP))
    eb = F.hex_flange_bolt(10.0, 22.0)
    parts.append(_st(F.place(eb, (0.0, EYE_HOLE_Y, EYE_Z + 10.0), (0, 0, 1), (0, 1, 0)), "accessory:lifting_eye_bolt", FA))
    _INFO["t_build"] = round(time.time() - t0)
    return parts


if __name__ == "__main__":
    import sys
    import time
    t0 = time.time()
    ps = build()
    print(f"{len(ps)} leaves in {time.time() - t0:.0f}s; info {_INFO}", flush=True)
    bad = [p.label for p in ps if not geo.sound(p)]
    print("unsound:", bad)
