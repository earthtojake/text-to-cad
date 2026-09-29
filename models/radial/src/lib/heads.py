"""Heads: nine cast-aluminium cylinder heads with integral rocker boxes, bronze
valve seats and guides, machined rocker-box covers (bolted, safety-wired),
exhaust-flange studs and nuts, and eighteen shielded spark plugs.

Authored ONCE for cylinder 1 in its local frame (t = +X, y = +Y, h = +Z) and
placed on cylinders 2..9 with `geo.on_cylinder`; cylinder 1 is the museum
section (front half removed by `geo.section_cutter()`), its hardware seated in
the removed region omitted.

THE CASTING (cylinder-local mm)
  skirt      h 385..402.2, bore R 79.7, screwed over the barrel spigot (R 79.5)
  chamber    hemisphere R 70 about (t 0, h 389); both valve axes pass through
             its centre, seats (h 440, |t| 37) lie on it; squish cone to the
             bore (R 73) at h 402.2
  fins       34 fins perpendicular to the cylinder axis wrapping the whole
             head, h 393..551.4 at 4.8 pitch, 1.8 thick at the root tapering
             (6 mm bevel) to a 1.1 tip band; rounded-rectangle outlines whose
             t half-width grows 125 -> 160 (tips >= 16.8 from the mid-plane to
             each neighbour), y from -128 (easing to -110 above h 495) to
             +104. Notched round the pushrod tubes and plugs, running into
             the rocker boxes, spring towers, ports and plug bosses.
  body       terraced core inside the fins (fin depth 38; each terrace step
             on a fin's mid-plane, hidden inside it) up to a crown at h 553.5.
  boxes      one per valve: a slab 125 x 162 tilted 10 deg outboard (its lid
             normal), lid face at proj 615.5 along (sin10, 0, cos10) from the
             frame origin; spring tower R 30 down the valve axis; pushrod inlet
             boss (OD 40) whose face is PUSHROD_TUBE_END_FROM_TOP below the top
             ball along the pushrod rest axis; shaft bores O20 blind at y -113
             and +15. Interior: rocker hub region y -110..+12 (R 22 about the
             shaft), valve pocket y -17..+12, spring well R 23.5 (floor at
             85.5 from the seat), pushrod pocket y -114..-86.
  ports      intake (+t) curves rearward to a threaded stub, face y 110, axis
             (t 80, h 468) along +y, stub OD 56 to y 124; exhaust (-t) curves
             forward to a 2-stud flange, face y -100, centre (t -98, h 462),
             studs at h 462 +- 38 (M8), nuts seated on y -108 (an 8 mm stack
             flange sits between).
  plugs      front/rear on t = 0: seat face centre (y -+95, h 478), axis
             (0, -+sin50, cos50) outward; terminal end 54 mm along the axis.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import geo, kin, palette as P, spec as S
from lib.fasteners import _wrench_head

MATERIALS = ("cast_alu", "machined_alu", "ceramic", "bronze", "steel_polished", "fastener", "safety_wire", "section_red")

# ---------------------------------------------------------------------------
# Numbers (cylinder-1 local: x = t, y = y, z = h)
# ---------------------------------------------------------------------------
INC = math.radians(S.VALVE_INCLINE_DEG)
H_SKIRT = 385.0
H_SHOULDER = 402.2
R_SKIRT_BORE = 79.7
CH_C = 389.0                  # chamber-sphere centre (on the cylinder axis)
CH_R = 70.0
R_WALL = 90.0                 # wall radius above the skirt (inside the fin stack)
LID_TILT = math.radians(10.0)
LID_N = (math.sin(LID_TILT), 0.0, math.cos(LID_TILT))
LID_U = (math.cos(LID_TILT), 0.0, -math.sin(LID_TILT))
# Rocker boxes: close-fitting cast skins round the rocker's swept envelope,
# split on a plane tilted 10 deg outboard (normal LID_N) at proj P_SPLIT; what
# lies above the split is the domed cover.
BOX_W = 4.5                   # wall
HUB_R_IN = 20.0
HUB_R_OUT = HUB_R_IN + BOX_W
P_SPLIT = 596.0
LUG_R, LUG_OUT, LUG_DOWN, LUG_UP = 7.0, 3.5, 11.0, 5.0
LUG_Y = (-104.0, -64.0, -30.0, 8.0)
COVER_T = LUG_UP              # bolt seats on the cover lug top


PLUG_ELEV = math.radians(50.0)          # plug axis angle from the cylinder axis
PLUG_FACE = {"F": (0.0, -95.0, 478.0), "R": (0.0, 95.0, 478.0)}
PLUG_AXIS = {"F": (0.0, -math.sin(PLUG_ELEV), math.cos(PLUG_ELEV)),
             "R": (0.0, math.sin(PLUG_ELEV), math.cos(PLUG_ELEV))}
PLUG_TERMINAL = 54.0

INTAKE_STUB = {"centre": (80.0, 110.0, 468.0), "axis": (0.0, 1.0, 0.0), "od": 56.0, "end_y": 124.0}
# Exhaust: rear-facing on the -t side, the intake's mirror. Flange face y 110
# (plate y 100..110), 2 x M8 studs on the flange's long axis (along h), nuts
# seated on y 118 (an 8 mm stack flange sits between).
EXHAUST_FLANGE = {"centre": (-80.0, 110.0, 468.0), "axis": (0.0, 1.0, 0.0),
                  "studs_h": (468.0 - 38.0, 468.0 + 38.0), "stud_d": 8.0, "nut_seat_y": 118.0}


def side(v):
    return 1.0 if v == "I" else -1.0


# ---------------------------------------------------------------------------
# Small vector helpers
# ---------------------------------------------------------------------------
def V(*a):
    return bd.Vector(*a)


def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _unit(a):
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)
    return (a[0] / n, a[1] / n, a[2] / n)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vaxis(v):
    return (side(v) * math.sin(INC), 0.0, math.cos(INC))


def vout(v):
    """Unit normal to the valve axis in the h-t plane, pointing outboard/down."""
    return (side(v) * math.cos(INC), 0.0, -math.sin(INC))


def seat(v):
    return (side(v) * S.VALVE_SEAT_T, 0.0, S.VALVE_SEAT_H)


def on_axis(v, s, n=0.0, y=0.0):
    p = _add(seat(v), vaxis(v), s)
    p = _add(p, vout(v), n)
    return (p[0], p[1] + y, p[2])


def pushrod_line(v):
    """(bottom ball, top ball, unit bottom->top) of the pushrod at rest, cylinder 1."""
    b, t = kin.pushrod_bottom0(1, v), kin.pushrod_top0(1, v)
    return b, t, _unit((t[0] - b[0], t[1] - b[1], t[2] - b[2]))


def pushrod_boss_face(v):
    b, t, u = pushrod_line(v)
    return _add(t, u, -S.PUSHROD_TUBE_END_FROM_TOP), u


def _one(shape):
    sols = shape.solids()
    if len(sols) != 1:
        sols = sorted(sols, key=lambda s: -s.volume)
        if len(sols) > 1 and sols[1].volume > 1.0:
            raise RuntimeError(f"expected one solid, got {[round(s.volume) for s in sols]}")
    return sols[0]


def _face_xz(pts):
    return bd.Face(bd.Wire.make_polygon([V(x, 0, z) for x, z in pts], close=True))


def _fillet_verts(face, pts, idx, r):
    targets = []
    for i in idx:
        x, z = pts[i]
        for vx in face.vertices():
            if abs(vx.X - x) < 1e-6 and abs(vx.Z - z) < 1e-6:
                targets.append(vx)
                break
    return face.fillet_2d(r, targets) if targets else face


def _rev_z(pts):
    return bd.revolve(_face_xz(pts), axis=bd.Axis.Z, revolution_arc=360.0)


def _cyl(p0, p1, r):
    return geo.cyl_along(p0, p1, 2 * r)


def _cone(p0, p1, r0, r1):
    d = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    L = math.sqrt(_dot(d, d))
    c = bd.Cone(r0, r1, L, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return geo.locate(c, p0, d)


def _sweep_circle(path, r):
    p0, t0 = path @ 0.0, path % 0.0
    prof = bd.Plane(origin=p0, z_dir=t0) * bd.Circle(r)
    return _one(bd.sweep(prof, path=path, is_frenet=False))


# ---------------------------------------------------------------------------
# The casting
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# The wrap-around fin stack ("wrap"): every fin a plane perpendicular to the
# cylinder axis, wrapping the whole head from the barrel joint up under the
# rocker boxes. Each fin is ONE planar slab: a rounded-rectangle outline in the
# (t, y) plane, tapered 1.8 -> 1.1 over its last WRAP_BEVEL mm by a ruled loft
# through four copies of the outline (no booleans per fin). The core is a
# smooth loft through the same outlines inset by the fin depth. Fins touch
# only the core, never each other: core + fins are ONE multi-operand fuse.
# Outline limits (cylinder-local):
#   t   the fin tip stays WRAP_GAP from the mid-plane to each neighbour
#       (the rear ignition lead climbs in that plane), and <= WRAP_WMAX;
#   y   front -128 low down, easing back to -110 above h 495 (plug elbow,
#       rocker-shaft nuts; the pushrod tubes pass in front, relieved round
#       their axes); rear 104 (the port flanges' faces are y 110), drawn in
#       to 82 over h 518..544 (the rear ignition lead crosses there).
# ---------------------------------------------------------------------------
WRAP_P = 4.8
WRAP_H = [393.0 + WRAP_P * i for i in range(34)]      # 393 .. 551.4
WRAP_ROOT, WRAP_TIP = 1.8, 1.1
WRAP_BEVEL = 6.0
WRAP_GAP = 16.8
WRAP_WMAX = 160.0
WRAP_D = 38.0                   # fin depth over the core
WRAP_YF = (-128.0, -110.0, 455.0, 495.0)   # front: low value, high value, blend from/to h
WRAP_YR = 104.0
WRAP_YR_DROP = 22.0             # the top fins draw in at the rear: the rear ignition lead
                                # swings over the -t rear corner at h 518..555, y 78..97
WRAP_CORE_TOP = 553.5
WRAP_ROUND = 0.72               # corner radius / the smaller half-extent: a rounded, bulbous plan
WRAP_SHOULDER = 22.0            # inward draw of the top fin
WRAP_SHOULDER_H = 522.0         # ... starting from this height
_S20, _C20 = math.sin(math.radians(20.0)), math.cos(math.radians(20.0))


def _smooth(x, x0, x1):
    f = min(1.0, max(0.0, (x - x0) / (x1 - x0)))
    return f * f * (3.0 - 2.0 * f)


def wrap_outline(h):
    """(W, y_front, y_rear, corner R) of the fin outline centred at height h."""
    hb = h - WRAP_ROOT / 2.0
    W = min((hb * _S20 - WRAP_GAP) / _C20, WRAP_WMAX)
    yf = WRAP_YF[0] + (WRAP_YF[1] - WRAP_YF[0]) * _smooth(h, WRAP_YF[2], WRAP_YF[3])
    yr = WRAP_YR - WRAP_YR_DROP * _smooth(h, 518.0, 544.0)
    # the top fins draw in all round: the stack's shoulder rolls over into
    # the rocker boxes instead of ending in a flat plate
    sh = WRAP_SHOULDER * max(0.0, (h - WRAP_SHOULDER_H) / (WRAP_H[-1] - WRAP_SHOULDER_H)) ** 2
    W, yf, yr = W - sh, yf + sh, yr - sh
    Rc = WRAP_ROUND * min(W, (yr - yf) / 2.0)
    return W, yf, yr, Rc


def _rrect_wire(W, yf, yr, Rc, inset, h):
    """Rounded rectangle (t half-width W, y from yf to yr, corner radius Rc)
    offset inward by `inset`, in the plane at height h: exact lines and arcs,
    so fins and core are planes, cylinders and cones (fast, exact booleans)."""
    W, yf, yr, Rc = W - inset, yf + inset, yr - inset, Rc - inset
    x0, x1, y0, y1 = -W, W, yf, yr
    return bd.Wire([bd.Line(V(x1, y0 + Rc, h), V(x1, y1 - Rc, h)),
                    bd.CenterArc(V(x1 - Rc, y1 - Rc, h), Rc, 0.0, 90.0),
                    bd.Line(V(x1 - Rc, y1, h), V(x0 + Rc, y1, h)),
                    bd.CenterArc(V(x0 + Rc, y1 - Rc, h), Rc, 90.0, 90.0),
                    bd.Line(V(x0, y1 - Rc, h), V(x0, y0 + Rc, h)),
                    bd.CenterArc(V(x0 + Rc, y0 + Rc, h), Rc, 180.0, 90.0),
                    bd.Line(V(x0 + Rc, y0, h), V(x1 - Rc, y0, h)),
                    bd.CenterArc(V(x1 - Rc, y0 + Rc, h), Rc, 270.0, 90.0)])


def _wrap_fin(h):
    """One fin: ruled loft through the outline inset by WRAP_BEVEL on the root
    faces (1.8 thick) and the full outline on the tip band (1.1 thick): the
    rim is a pair of shallow cones/planes that catch the light."""
    o = wrap_outline(h)
    a, b = WRAP_ROOT / 2.0, WRAP_TIP / 2.0
    secs = [_rrect_wire(*o, WRAP_BEVEL, h - a), _rrect_wire(*o, 0.0, h - b),
            _rrect_wire(*o, 0.0, h + b), _rrect_wire(*o, WRAP_BEVEL, h + a)]
    return bd.Solid.make_loft(secs, ruled=True)


WRAP_CORE_STEP = 3          # fins per core terrace


def _wrap_core():
    """The head body inside the fins: terraced prisms of the fin outline inset
    by WRAP_D, each step lying on a fin's mid-plane (hidden inside that fin),
    from the second fin up to a crown just over the top fin, its top edge
    rounded."""
    hs = WRAP_H[1::WRAP_CORE_STEP]
    if hs[-1] != WRAP_H[-1]:
        hs.append(WRAP_H[-1])
    prisms = []
    for i, (h0, h1) in enumerate(zip(hs[:-1], hs[1:])):
        top = h1 + 0.5 if i < len(hs) - 2 else WRAP_CORE_TOP
        samples = [h0 + (h1 - h0) * j / 6.0 for j in range(7)] + [top]
        outs = [wrap_outline(x) for x in samples]
        W = min(o[0] for o in outs)
        yf = max(o[1] for o in outs)
        yr = min(o[2] for o in outs)
        Rc = min(0.55 * min(W, (yr - yf) / 2.0), min(o[3] for o in outs))
        face = bd.Face(_rrect_wire(W, yf, yr, Rc, WRAP_D, h0))
        prisms.append(bd.extrude(face, amount=top - h0, dir=(0, 0, 1)))
    crown = prisms[-1]
    rim = [e for e in crown.edges() if abs(e.bounding_box().center().Z - WRAP_CORE_TOP) < 1e-3]
    prisms[-1], _ = C.safe_fillet(crown, rim, 1.6, min_r=0.6)
    return prisms


def _lower_body_v0():
    pts = [(R_SKIRT_BORE, H_SKIRT), (92.0, H_SKIRT), (93.0, H_SKIRT + 1.0), (93.0, 389.0),
           (R_WALL, 391.0), (R_WALL, 447.0), (84.0, 452.0), (0.0, 452.0), (0.0, H_SHOULDER),
           (R_SKIRT_BORE, H_SHOULDER)]
    return _rev_z(pts)


def _lid_h(t, proj=P_SPLIT):
    return (proj - t * LID_N[0]) / LID_N[2]


def _split_point(u, y, above=0.0):
    """Point on the split plane (+t side): u along LID_U from t = 96, then `above` along LID_N."""
    o = (96.0, y, _lid_h(96.0))
    return _add(_add(o, LID_U, u), LID_N, above)


def _mirror_t(shape, v):
    return shape if v == "I" else shape.mirror(bd.Plane.YZ)


def _mirror_pt(p, v):
    return p if v == "I" else (-p[0], p[1], p[2])


def _resample_closed(pts, step):
    """Evenly spaced points (about `step` apart) round a closed polyline, so a
    periodic spline through them cannot overshoot between crowded vertices."""
    segs = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    lens = [math.dist(a, b) for a, b in segs]
    total = sum(lens)
    n = max(12, int(round(total / step)))
    out, acc, k = [], 0.0, 0
    for i in range(n):
        d = total * i / n
        while acc + lens[k] < d:
            acc += lens[k]
            k += 1
        f = (d - acc) / lens[k]
        a, b = segs[k]
        out.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
    return out


def _smooth_prism(which, y0, y1, r_end=5.0):
    # a periodic spline through the (convex) pocket hull, pushed out by the
    # wall: a smooth skin with no flat facets between hull vertices
    hull = _hull(_grow(POCKET_HULL[which], BOX_W, 24))
    spline = bd.Spline(*[V(x, y0, z) for x, z in _resample_closed(hull, 10.0)], periodic=True)
    face = bd.Face(bd.Wire([spline]))
    prism = bd.extrude(face, amount=y1 - y0, dir=(0, 1, 0))
    ends = [e for e in prism.edges() if e.bounding_box().size.Y < 1e-3]
    prism, _ = C.safe_fillet(prism, ends, r_end, min_r=1.0)
    return prism


_CORE = None


def _housing_core():
    """+t rocker-box skin (no inlet boss, no lugs): the shaft tube, the valve-
    end and pushrod-end pockets each wrapped in a 4.5 mm cast wall with arc-
    offset sections and rounded ends, and a drafted spring tower flaring into
    the head. Rounded where the pieces meet."""
    global _CORE
    if _CORE is not None:
        return _CORE
    px, pz = S.ROCKER_PIVOT[1], S.ROCKER_PIVOT[0]
    tube = _cyl((px, S.ROCKER_SHAFT_Y[0], pz), (px, S.ROCKER_SHAFT_Y[1], pz), HUB_R_OUT)
    tube, _ = C.safe_fillet(tube, [e for e in tube.edges() if e.bounding_box().size.Y < 1e-3], 2.5)
    valve = _smooth_prism("valve", POCKET_Y["valve"][0] - BOX_W, POCKET_Y["valve"][1] + BOX_W, 6.0)
    push = _smooth_prism("push", POCKET_Y["push"][0] - BOX_W, POCKET_Y["push"][1] + BOX_W, 6.0)
    tower = _cone(on_axis("I", 10.0), on_axis("I", 152.0), 36.0, 28.0)
    body = _one(tube.fuse(valve, push, tower).clean())
    parts = (tube, valve, push, tower)
    faces = [p.faces() for p in parts]

    def seam(e):
        c = e.bounding_box().center()
        hits = sum(1 for fs in faces if min(f.distance_to(c) for f in fs) < 1e-3)
        return hits >= 2
    keys = {C._edge_key(e) for e in body.edges() if seam(e)}
    plain = body
    body, r = C.fillet_all(body, 5.0, exclude=lambda e: C._edge_key(e) not in keys, min_r=1.5)
    if r is None or not C.is_sound(body) or len(body.solids()) != 1:
        C._warn(f"heads: rocker-box seam blends failed ({len(keys)} edges); left sharp")
        body = plain
    _CORE = body
    return body


_LUGS = {}


def _in_grown(pt, hull, g):
    """True when 2D point pt lies inside, or within g of, the convex polygon hull."""
    x, z = pt
    n = len(hull)
    best, signs = 1e9, set()
    for i in range(n):
        (ax, az), (bx, bz) = hull[i], hull[(i + 1) % n]
        ex, ez = bx - ax, bz - az
        f = max(0.0, min(1.0, ((x - ax) * ex + (z - az) * ez) / (ex * ex + ez * ez)))
        best = min(best, math.hypot(x - ax - f * ex, z - az - f * ez))
        signs.add(ex * (z - az) - ez * (x - ax) >= 0)
    return len(signs) == 1 or best <= g


def _lug_points(v):
    """Lug centres on the split plane just outside the skin, inboard and
    outboard, at each LUG_Y; computed analytically from the skin's parts
    (shaft tube, grown pocket sections) so they never depend on a classifier."""
    if v in _LUGS:
        return _LUGS[v]
    px, pz = S.ROCKER_PIVOT[1], S.ROCKER_PIVOT[0]
    out = []
    for y in LUG_Y:
        inside = []
        for i in range(-400, 500):
            u = i * 0.25
            q = _split_point(u, y)
            pt = (q[0], q[2])
            hit = math.hypot(pt[0] - px, pt[1] - pz) <= HUB_R_OUT
            for which in ("valve", "push"):
                y0, y1 = POCKET_Y[which]
                if y0 - BOX_W <= y <= y1 + BOX_W and _in_grown(pt, POCKET_HULL[which], BOX_W):
                    hit = True
            if hit:
                inside.append(u)
        u_in, u_out = min(inside), max(inside)
        for u in (u_in - LUG_OUT, u_out + LUG_OUT):
            out.append(_mirror_pt(_split_point(u, y), v))
    _LUGS[v] = out
    return out


def _lug(p, v):
    n = _mirror_pt(LID_N, v)
    lug = bd.Cylinder(LUG_R, LUG_DOWN + LUG_UP, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lug, _ = C.safe_fillet(lug, [e for e in lug.edges() if abs(e.bounding_box().center().Z) < 1e-3], 3.5)
    lug, _ = C.safe_fillet(lug, [e for e in lug.edges() if abs(e.bounding_box().center().Z - LUG_DOWN - LUG_UP) < 1e-3], 1.0)
    return geo.locate(lug, _add(p, n, -LUG_DOWN), n)


def _box_outer(v):
    core = _mirror_t(_housing_core(), v)
    face, u = pushrod_boss_face(v)
    boss = _cone(face, _add(face, u, 30.0), 21.5, 19.5)
    lugs = [_lug(p, v) for p in _lug_points(v)]
    return core, boss, lugs


_SHELL = {}


def _box_shell(v):
    """core + inlet boss + lugs as one solid (fused one at a time and checked:
    a lug that fails to join is a missing casting feature, not a loose part)."""
    if v in _SHELL:
        return _SHELL[v]
    core, boss, lugs = _box_outer(v)
    body = _one(core.fuse(boss))
    for lug in lugs:
        nxt = body.fuse(lug)
        if len(nxt.solids()) != 1:
            raise RuntimeError("heads: a cover lug did not join its rocker box")
        body = nxt.solids()[0]
    _SHELL[v] = body
    return body


def _above_split(v):
    half = geo.locate(bd.Box(700, 700, 300, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                      _split_point(0.0, 0.0), LID_N, LID_U)
    side_box = bd.Pos(8.0, -400.0, 300.0) * bd.Box(400, 800, 600, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    return _mirror_t(half & side_box, v)


def _box_air(v):
    """Everything inside a rocker box, per side."""
    s = side(v)
    piv = (s * S.ROCKER_PIVOT[1], 0.0, S.ROCKER_PIVOT[0])
    tools = []
    tools.append(_cyl((piv[0], HUB_Y[0], piv[2]), (piv[0], HUB_Y[1], piv[2]), HUB_R_IN))
    tools.append(_cyl((piv[0], SHAFT_FACE_Y[0] - 1.0, piv[2]), (piv[0], SHAFT_FACE_Y[1] + 1.0, piv[2]), 7.4))
    tools.append(_cyl((piv[0], SHAFT_FACE_Y[0], piv[2]), (piv[0], SHAFT_FACE_Y[0] - 40.0, piv[2]), 12.5))
    tools.append(_cyl((piv[0], SHAFT_FACE_Y[1], piv[2]), (piv[0], SHAFT_FACE_Y[1] + 40.0, piv[2]), 12.5))
    tools.append(_cyl(on_axis(v, SPRING_FLOOR), on_axis(v, 150.0), 23.5))
    tools.append(_pocket(v, "valve"))
    tools.append(_pocket(v, "push"))
    face, u = pushrod_boss_face(v)
    tools.append(_cyl(_add(face, u, -2.0), _add(face, u, 36.0), 14.5))
    return tools


# Rocker-box pocket sections (t, h) for the +t side: the valvetrain's rocker
# (arm, bearings, adjuster, locknut) swept over 0..18.6 deg about the shaft, and
# the valve tip / retainer / keepers over the full lift, hulled and grown by
# >= 3.7 mm (tmp/heads/rocker_env.py + hull_simplify.py regenerate them from
# lib/valvetrain.py; the push hull includes the arm's rearward-leaning band).
POCKET_HULL = {
    "push": [[45.37, 589.62], [47.05, 585.16], [81.13, 556.41], [91.91, 555.62], [101.57, 560.3], [107.6, 569.19], [108.4, 579.85], [106.5, 585.7], [87.34, 623.02], [79.5, 628.9], [70.43, 630.24], [55.68, 623.37], [48.03, 616.32], [46.36, 607.54], [45.25, 598.24]],
    "valve": [[72.25, 562.48], [97.24, 537.35], [111.97, 526.65], [122.33, 522.21], [125.84, 521.51], [128.79, 522.3], [130.95, 524.46], [140.28, 537.29], [149.67, 574.31], [145.92, 582.39], [138.13, 587.8], [84.1, 596.38], [74.44, 591.72], [68.4, 582.81], [67.1, 576.04]],
}
POCKET_Y = {"push": (-110.0, -75.0), "valve": (-16.0, 11.0)}
HUB_Y = (-110.0, 8.5)
SHAFT_FACE_Y = (S.ROCKER_SHAFT_Y[0], S.ROCKER_SHAFT_Y[1])   # outer spot faces the shaft nuts bear on
SPRING_FLOOR = 83.3


LIFT_OUT = 40.0
LIFT_OUT_T = 72.0    # the lift-out slot spans the valve pocket from this t outboard


def _lift_out_slot():
    """+t valve-pocket air swept straight up the cylinder axis (the explode
    path) to the split plane: with the cover off, the rocker lifts out at ANY
    angle. At full lift its arm used to graze the pocket's inboard shoulder
    (t 73.5..75, h 591..592) just under the split. The slot starts at t 72 (the skin
    inboard of it, and every lug, stay as they were) and stops at the split,
    so the cover is untouched."""
    hull = POCKET_HULL["valve"]
    pts = [p for p in hull if p[0] >= LIFT_OUT_T]
    # plus the point where the slot's inboard wall t = LIFT_OUT_T meets the
    # hull's upper inboard edge
    for a, b in zip(hull, hull[1:] + hull[:1]):
        if (a[0] - LIFT_OUT_T) * (b[0] - LIFT_OUT_T) < 0 and max(a[1], b[1]) > 570.0:
            f = (LIFT_OUT_T - a[0]) / (b[0] - a[0])
            pts.append((LIFT_OUT_T, a[1] + f * (b[1] - a[1])))
    slot = _prism_xz(_hull(pts + [(x, z + LIFT_OUT) for x, z in pts]), *POCKET_Y["valve"])
    return slot.cut(_above_split("I"))


def _grow(pts, g, n=16):
    out = []
    for x, z in pts:
        out += [(x + g * math.cos(2 * math.pi * i / n), z + g * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return _hull(out)


def _prism_xz(pts, y0, y1):
    face = bd.Face(bd.Wire.make_polygon([V(x, y0, z) for x, z in pts], close=True))
    return bd.extrude(face, amount=y1 - y0, dir=(0, 1, 0))


def _pocket(v, which):
    y0, y1 = POCKET_Y[which]
    solid = _prism_xz(POCKET_HULL[which], y0, y1)
    if which == "valve":
        # the retainer's travel lives in the spring well; keep the prism above it
        keep = geo.locate(bd.Box(400, 400, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                          on_axis("I", 135.0), vaxis("I"), vout("I"))
        solid = _one(_fuse([solid, _lift_out_slot()]) & keep)
    return _mirror_t(solid, v)


def _hull(pts):
    pts = sorted(set((round(x, 4), round(z, 4)) for x, z in pts))

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _port_path(v):
    if v == "I":
        pts = [on_axis("I", 4.0), (66.0, 55.0, 478.0), INTAKE_STUB["centre"]]
        tans = [vaxis("I"), (0.0, 1.0, 0.0)]
    else:
        pts = [on_axis("E", 4.0), (-66.0, 55.0, 478.0), EXHAUST_FLANGE["centre"]]
        tans = [vaxis("E"), (0.0, 1.0, 0.0)]
    return bd.Spline(*[V(*p) for p in pts], tangents=[V(*t) for t in tans])


PORT_R = {"I": (24.0, 30.5), "E": (21.5, 28.0)}   # 30.0 met a fin tangentially


def _port_body(v):
    path = _port_path(v)
    return _sweep_circle(path, PORT_R[v][1])


def _port_bore(v):
    path = _port_path(v)
    bore = _sweep_circle(path, PORT_R[v][0])
    # the straight bore through the flange is a deliberate 0.4 mm step larger
    # than the swept bore: two coincident R-equal cylinders here left a sliver
    # face that came back from STEP with a bad sub-shape orientation
    r_ext = PORT_R[v][0] + 0.4
    if v == "I":
        c = INTAKE_STUB["centre"]
        ext = _cyl((c[0], c[1] - 6.0, c[2]), (c[0], INTAKE_STUB["end_y"] + 2.0, c[2]), r_ext)
    else:
        c = EXHAUST_FLANGE["centre"]
        ext = _cyl((c[0], c[1] - 6.0, c[2]), (c[0], c[1] + 3.0, c[2]), r_ext)
    throat = _cyl(on_axis(v, 2.0), on_axis(v, 12.0), PORT_R[v][0])
    return [bore, ext, throat]


def _intake_stub():
    c = INTAKE_STUB["centre"]
    x, z = c[0], c[2]
    flange = _cyl((x, 96.0, z), (x, 110.0, z), 36.0)
    flange, _ = C.safe_fillet(flange, flange.edges(), 2.0)
    prof = [(24.0, 109.0), (28.0, 109.0), (28.0, 117.0), (29.2, 118.0), (29.2, 120.0), (28.0, 121.0),
            (28.0, 123.2), (27.2, 124.0), (24.0, 124.0)]
    stub = bd.revolve(bd.Face(bd.Wire.make_polygon([V(r, 0, y) for r, y in prof], close=True)),
                      axis=bd.Axis.Z)
    stub = geo.locate(stub, (x, 0.0, z), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    return [flange, stub]


def _exhaust_flange():
    c = EXHAUST_FLANGE["centre"]
    y0 = c[1] - 10.0
    pl = geo.plane((c[0], y0, c[2]), z_dir=(0.0, 1.0, 0.0), x_dir=(1.0, 0.0, 0.0))
    sk = bd.SlotCenterToCenter(76.0, 60.0, rotation=90.0)
    fl = bd.extrude(pl * sk, amount=10.0)
    fl, _ = C.safe_fillet(fl, [e for e in fl.edges() if abs(e.bounding_box().center().Y - y0) < 0.3], 3.0)
    return fl


def _plug_boss(k):
    f, d = PLUG_FACE[k], PLUG_AXIS[k]
    return _cone(_add(f, d, -46.0), f, 19.0, 17.0)


def _plug_air(k):
    f, d = PLUG_FACE[k], PLUG_AXIS[k]
    return [_cyl(_add(f, d, -13.5), _add(f, d, 0.5), 8.9),
            _cyl(_add(f, d, -75.0), _add(f, d, -13.0), 6.0)]


def _plug_clear(k):
    f, d = PLUG_FACE[k], PLUG_AXIS[k]
    return _cyl(_add(f, d, 0.0), _add(f, d, 90.0), 18.0)


def _chamber_air():
    """Chamber (hemisphere + squish cone) and the skirt bore, one revolve."""
    zc = CH_C
    # sphere arc from the squish-cone top to the pole
    h_cone = 406.0
    r_cone = math.sqrt(CH_R ** 2 - (h_cone - zc) ** 2)
    edges = [bd.Line(V(0, 0, H_SKIRT - 1.0), V(R_SKIRT_BORE, 0, H_SKIRT - 1.0)),
             bd.Line(V(R_SKIRT_BORE, 0, H_SKIRT - 1.0), V(R_SKIRT_BORE, 0, H_SHOULDER)),
             bd.Line(V(R_SKIRT_BORE, 0, H_SHOULDER), V(S.BORE / 2.0, 0, H_SHOULDER)),
             bd.Line(V(S.BORE / 2.0, 0, H_SHOULDER), V(r_cone, 0, h_cone))]
    a0 = math.atan2(h_cone - zc, r_cone)
    am = (a0 + math.pi / 2) / 2
    edges.append(bd.ThreePointArc(V(r_cone, 0, h_cone), V(CH_R * math.cos(am), 0, zc + CH_R * math.sin(am)),
                                  V(0, 0, zc + CH_R)))
    edges.append(bd.Line(V(0, 0, zc + CH_R), V(0, 0, H_SKIRT - 1.0)))
    face = bd.Face(bd.Wire(edges))
    return bd.revolve(face, axis=bd.Axis.Z)


# seat inserts / guides (valve-axis frame: z = axis, x = outboard normal)
SEAT_OD = {"I": 72.0, "E": 66.0}
SEAT_IN = {"I": 30.6, "E": 28.1}
SEAT_THROAT = {"I": 26.0, "E": 23.5}
GUIDE = dict(s0=30.0, s_pad=SPRING_FLOOR, s1=94.0, od=20.0, od_top=18.0, bore=12.6)


def _axis_frame(v):
    return geo.plane(seat(v), z_dir=vaxis(v), x_dir=vout(v))


LINING_T = 0.6


def _chamber_lining():
    """A 0.6 mm lining on the chamber roof (inside the chamber air, so it never
    overlaps the casting), in a warm non-metallic finish: a metallic dome inside
    a closed cavity only mirrors the dark cavity, so on the museum section it
    read as a flat black mass; a diffuse surface answers the lights. Open at
    the seats, throats and plug holes."""
    shell = (bd.Pos(0, 0, CH_C) * bd.Sphere(CH_R)) - (bd.Pos(0, 0, CH_C) * bd.Sphere(CH_R - LINING_T))
    keep = bd.Pos(0, 0, 407.0) * bd.Box(300, 300, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lining = shell & keep
    holes = [_seat_pocket(v) for v in ("I", "E")]
    for k in ("F", "R"):
        holes += _plug_air(k)
    return _one(lining.cut(*holes))


def _seat_insert(v):
    """Seat ring. Its chamber-side face is a cone through the chamber sphere at
    the ring's inner and outer radii (within 0.1 mm of the hemisphere) - no
    sphere boolean, whose cut result exported to STEP as a runaway surface."""
    ro, ri, rt = SEAT_OD[v] / 2.0, SEAT_IN[v], SEAT_THROAT[v]
    d0 = math.dist(seat(v), (0.0, 0.0, CH_C))            # seat-centre distance from the sphere centre

    def s_sphere(r):
        return math.sqrt(CH_R ** 2 - r ** 2) - d0
    prof = [(ri, s_sphere(ri)), (ro, s_sphere(ro)), (ro - 0.6, 10.0), (rt, 10.0), (rt, 8.6), (ri, 4.0)]
    ring = bd.revolve(_face_xz(prof), axis=bd.Axis.Z)
    return _one(_axis_frame(v).location * ring)


def _seat_pocket(v):
    ro = SEAT_OD[v] / 2.0
    return _cyl(on_axis(v, -9.0), on_axis(v, 10.0), ro)


def _guide(v):
    g = GUIDE
    r, rt, rb = g["od"] / 2.0, g["od_top"] / 2.0, g["bore"] / 2.0
    prof = [(rb, g["s0"]), (r - 1.0, g["s0"]), (r, g["s0"] + 1.0), (r, g["s_pad"]), (rt, g["s_pad"]),
            (rt, g["s1"] - 0.8), (rt - 0.8, g["s1"]), (rb, g["s1"])]
    tube = bd.revolve(_face_xz(prof), axis=bd.Axis.Z)
    return _axis_frame(v).location * tube


def _guide_hole(v):
    return [_cyl(on_axis(v, GUIDE["s0"] - 2.0), on_axis(v, GUIDE["s_pad"] + 0.5), GUIDE["od"] / 2.0),
            _cyl(on_axis(v, 2.0), on_axis(v, 40.0), 8.0)]


def _tube_relief(v):
    b, t, u = pushrod_line(v)
    face = _add(t, u, -S.PUSHROD_TUBE_END_FROM_TOP)
    return _cyl(_add(t, u, -330.0), face, 20.0)


def _exhaust_stud_holes():
    c = EXHAUST_FLANGE["centre"]
    return [_cyl((c[0], c[1] - 13.0, h), (c[0], c[1] + 1.0, h), 3.75) for h in EXHAUST_FLANGE["studs_h"]]


def _fuse(items):
    items = list(items)
    return items[0].fuse(*items[1:])


def _port_reliefs():
    """Keep the fins off the exhaust stack flange and the intake coupling."""
    c = EXHAUST_FLANGE["centre"]
    ex = bd.Pos(c[0] - 38.0, c[1], c[2] - 76.0) * bd.Box(76.0, 60.0, 152.0,
                                                               align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    ci = INTAKE_STUB["centre"]
    end = INTAKE_STUB["end_y"]
    # a ring round the stub between the flange face and the stub end, then a
    # SOLID cylinder beyond the stub end (the intake union nut and pipe live there)
    ring = _cyl((ci[0], ci[1], ci[2]), (ci[0], end, ci[2]), 48.0) - \
        _cyl((ci[0], ci[1], ci[2]), (ci[0], end + 1.0, ci[2]), 29.4)
    beyond = _cyl((ci[0], end, ci[2]), (ci[0], 170.0, ci[2]), 48.0)
    return [ex, _fuse([ring, beyond])]


def _fuse_checked(body, tools, allow_many=False):
    """Multi-operand fuse, falling back to one tool at a time; a tool that will
    not fuse is a build error (never a silently missing feature)."""
    def ok(r):
        return r is not None and r.solids() and r.is_valid and (allow_many or len(r.solids()) == 1)
    try:
        r = body.fuse(*tools)
        if ok(r):
            return r
    except Exception:
        pass
    pending = list(tools)
    while pending:
        progress = False
        for t in list(pending):
            r = None
            for attempt in (lambda: body.fuse(t), lambda: t.fuse(body)):
                try:
                    r = attempt()
                except Exception:
                    r = None
                if ok(r):
                    break
            if ok(r):
                body = r
                pending.remove(t)
                progress = True
        if not progress:
            raise RuntimeError(f"heads: {len(pending)} casting feature(s) would not fuse")
    return body


def build_head_proto():
    """The cylinder-1 head casting (one solid): the wrap-around fin stack."""
    others = [_box_shell("I"), _box_shell("E"), _port_body("E"), _port_body("I")]
    others += _intake_stub() + [_exhaust_flange()]
    others += [_plug_boss(k) for k in ("F", "R")]
    return _build_wrap(others)


def _stage_ok(body, what, full=False):
    """Validity gate between stages: one valid, closed solid of positive volume
    (`full`: plus the BOP check of geo.sound and the STEP round trip, which
    cost minutes on the finished casting, so they run once, at the end)."""
    from OCP.BRep import BRep_Tool
    ok = body is not None and len(body.solids()) == 1 and body.is_valid
    if ok:
        s = body.solids()[0]
        ok = s.volume > 0 and all(BRep_Tool.IsClosed_s(sh.wrapped) for sh in s.shells())
    if ok and full:
        ok = geo.sound(body) and _step_roundtrip_ok(body)
    if not ok:
        raise RuntimeError(f"heads: {what} is not one sound solid")
    return body.solids()[0]


def _build_wrap(others):
    """Core + casting features, then (1) ALL fins in one multi-operand fuse,
    (2) the outside reliefs in one multi-tool cut (tube keep-outs, plug
    clearances, port couplings, the covers' share: disjoint tools), (3) the
    inside air in one cut. Each stage is gated sound."""
    core = _one(_fuse([_lower_body_v0(), *_wrap_core()]))
    core = _stage_ok(_fuse_checked(core, others), "core")
    fins = [_wrap_fin(h) for h in WRAP_H]
    for i, (h, f) in enumerate(zip(WRAP_H, fins)):
        # every fin is the same construction: the full BOP + STEP check on one
        # representative, the cheap gate on the rest
        _stage_ok(f, f"fin at h {h:.1f}", full=(i == len(fins) // 2))
    body = _stage_ok(core.fuse(*fins), "core + fins")
    reliefs = [*[_tube_relief(v) for v in ("I", "E")], *[_plug_clear(k) for k in ("F", "R")],
               *_port_reliefs(), *[_above_split(v) for v in ("I", "E")]]
    body = _stage_ok(_cut_checked(body, reliefs), "reliefs")
    air = [_chamber_air()]
    for v in ("I", "E"):
        air += _box_air(v) + _port_bore(v) + _guide_hole(v) + [_seat_pocket(v)] + _tap_holes(v)
    for k in ("F", "R"):
        air += _plug_air(k)
    air += _exhaust_stud_holes()
    body = _stage_ok(_cut_checked(body, [_fuse(air)]), "air", full=True)
    if body.volume < 3.0e6:
        raise RuntimeError(f"head lost material: {body.volume:.0f}")
    return body


def _main_solid(r, ref_volume, lost_max):
    """Largest solid of a cut result if the cut kept the casting, else None;
    detached scraps (plate ends cut free by a relief, < 4000 mm3) are dropped."""
    if r is None or not r.solids():
        return None
    sols = sorted(r.solids(), key=lambda x: -x.volume)
    main = sols[0]
    if main.volume < max(ref_volume - lost_max, 0.55 * ref_volume) or not main.is_valid:
        return None
    if any(x.volume > 4000.0 for x in sols[1:]):
        return None
    return main


def _cut_checked(body, tools, sequential=False):
    """Cut `tools` (single multi-tool cut; tool by tool if that one misbehaves).
    Each result must keep the casting whole (the removed volume can not exceed
    the tools' own volume)."""
    total = sum(t.volume for t in tools)
    r = None
    if not sequential:
        try:
            r = _main_solid(body.cut(*tools), body.volume, total + 1.0)
        except Exception:
            r = None
    if r is not None:
        return r
    for i, t in enumerate(tools):
        got = None
        for attempt in (lambda: body.cut(t), lambda: body - t):
            try:
                got = _main_solid(attempt(), body.volume, t.volume + 1.0)
            except Exception:
                got = None
            if got is not None:
                break
        if got is None:
            raise RuntimeError(f"heads: cut tool {i} broke the casting")
        body = got
    return body


# ---------------------------------------------------------------------------
# Covers, bolts, safety wire
# ---------------------------------------------------------------------------
WIRE_PAIRS = [(0, 2), (1, 3), (4, 6), (5, 7)]     # lug indices: (y0 in, y0 out, y1 in, y1 out, ...)
BOLT_AF, BOLT_HEAD_H, BOLT_D = 10.0, 4.5, 6.0
WASHER_OD, WASHER_T = 12.5, 1.0
TAP_R = 2.8
TAP_DEPTH = 9.0


def _cover(v):
    """The domed cover: the skin above the split plane (with the upper halves
    of the lugs), hollowed by the same air as the box, drilled for the bolts."""
    cap = _box_shell(v) & _above_split(v)
    n = _mirror_pt(LID_N, v)
    holes = [_cyl(_add(p, n, -1.0), _add(p, n, LUG_UP + 1.0), 3.3) for p in _lug_points(v)]
    return _one(cap.cut(_fuse(_box_air(v)), *holes, *_spot_faces(v)))


SPOT_R = 6.4


def _spot_faces(v):
    """Clearance above each lug for the bolt head and washer: where the skin
    rises beside a lug the cover is spot-faced down to the lug's seat."""
    n = _mirror_pt(LID_N, v)
    return [_cyl(_add(p, n, LUG_UP), _add(p, n, LUG_UP + 7.0), SPOT_R) for p in _lug_points(v)]


def _tap_holes(v):
    n = _mirror_pt(LID_N, v)
    return [_cyl(_add(p, n, 1.0), _add(p, n, -TAP_DEPTH), TAP_R) for p in _lug_points(v)]


def _bolt_proto():
    """AN-style hex bolt with its plain washer, seated on the cover (z = 0).
    One revolve for washer + shank (no washer bore sliver), hex head on top."""
    r_w = WASHER_OD / 2.0
    zb = -(COVER_T + TAP_DEPTH - 1.5)
    base = bd.revolve(_face_xz([(0.0, zb), (2.1, zb), (2.65, zb - 0.55 + 1.1), (2.65, 0.0), (r_w - 0.2, 0.0),
                                (r_w, 0.2), (r_w, WASHER_T), (0.0, WASHER_T)]), axis=bd.Axis.Z)
    head = _wrench_head(BOLT_AF, WASHER_T, WASHER_T + BOLT_HEAD_H, chamfer_bottom=False, rotation=30.0)
    return _one(base.fuse(head).clean())


def _bolt_frames(v):
    """Placement planes (origin on the cover lug top, z = split normal) of the cover bolts."""
    n, x = _mirror_pt(LID_N, v), _mirror_pt(LID_U, v)
    return [(_add(p, n, LUG_UP), n, x) for p in _lug_points(v)]


def _twisted_wire(points, n):
    """Two twisted Ø0.8 strands along a smooth centreline through `points`,
    twisted in the centreline's own moving frame. One leaf: two disjoint
    solids 0.24 mm apart, so nothing overlaps."""
    path = bd.Spline(*[V(*p) for p in points])
    nn = V(*n)
    L = path.length
    N = max(24, int(L / 4.0 * 12))
    strands = []
    for phase in (0.0, 180.0):
        pts = []
        for i in range(N + 1):
            f = i / N
            c = path.position_at(f)
            tang = path.tangent_at(f)
            side_v = tang.cross(nn).normalized()
            up = side_v.cross(tang).normalized()
            ang = math.radians(phase + 360.0 * L * f / 4.0)
            pts.append(c + side_v * (0.52 * math.cos(ang)) + up * (0.52 * math.sin(ang)))
        strands.append(_sweep_circle(bd.Spline(*pts), 0.4))
    return bd.Compound(strands)


def _overlap(a, b):
    x = a & b
    return 0.0 if x is None or not x.solids() else sum(s.volume for s in x.solids())


# Wires that must turn a corner of the skin run through a waypoint: (pair) ->
# (take t/h from lug "a" or "b", y station).
WIRE_WAYPOINT = {(0, 2): ("a", -66.0), (5, 7): ("b", -27.0)}


def _wires(v, frames, avoid):
    """One twisted pair per bolt pair, from bolt head to bolt head, lifted and
    bowed (or turned through a waypoint) just enough to clear `avoid`."""
    wires = []
    for i, j in WIRE_PAIRS:
        (pa, na, _), (pb, nb, _) = frames[i], frames[j]
        h = WASHER_T + BOLT_HEAD_H * 0.55
        A, B = _add(pa, na, h), _add(pb, nb, h)
        r_head = BOLT_AF / 2.0 / math.cos(math.radians(30.0)) + 0.5
        out = _mirror_pt(LID_U if i % 2 else tuple(-c for c in LID_U), v)
        chosen = None
        for lift, bow in ((1.5, 0.0), (2.5, 3.0), (3.5, 6.0), (4.5, 10.0)):
            if (i, j) in WIRE_WAYPOINT:
                which, yw = WIRE_WAYPOINT[(i, j)]
                base = A if which == "a" else B
                W = _add(_add((base[0], yw, base[2]), na, lift), out, bow * 0.5)
                d0 = _unit(tuple(W[k] - A[k] for k in range(3)))
                d1 = _unit(tuple(B[k] - W[k] for k in range(3)))
                pts = [_add(A, d0, r_head), W, _add(B, d1, -r_head)]
            else:
                d = _unit(tuple(B[k] - A[k] for k in range(3)))
                p0, p1 = _add(A, d, r_head), _add(B, d, -r_head)
                mid = _add(_add(tuple((p0[k] + p1[k]) / 2 for k in range(3)), na, lift), out, bow)
                pts = [p0, mid, p1]
            try:
                w = _twisted_wire(pts, na)
            except Exception:
                continue
            if all(geo.sound(x) for x in w.solids()) and all(_overlap(w, s) < 1e-3 for s in avoid):
                chosen = w
                break
        if chosen is None:
            raise RuntimeError(f"heads: safety wire {v} {i}-{j} cannot clear the cover")
        wires.append((i, j, chosen))
    return wires


# ---------------------------------------------------------------------------
# Spark plug, exhaust studs and nuts
# ---------------------------------------------------------------------------
def _plug_proto():
    """Period shielded aircraft plug; seat (gasket) face at z = 0, +z outward."""
    body = bd.revolve(_face_xz([
        (0.0, -15.0), (4.6, -15.0), (5.0, -14.6), (5.0, -12.7), (8.2, -12.7), (8.75, -12.1),
        (8.75, 0.0), (11.8, 0.0), (12.0, 0.2), (12.0, 1.4), (11.8, 1.6), (9.5, 1.6),
        (9.5, 12.0), (9.8, 12.0), (10.2, 12.8), (10.2, 24.0), (9.6, 24.6), (10.2, 25.2), (10.2, 29.5),
        (11.0, 30.0), (11.0, 32.0), (10.2, 32.5), (10.2, 35.5), (8.4, 36.2), (7.9, 37.0),
        (7.9, 53.2), (7.1, 54.0), (4.6, 54.0), (4.6, 44.0), (0.0, 44.0)]), axis=bd.Axis.Z)
    hexb = _wrench_head(22.2, 1.6, 11.0, chamfer_bottom=True, rotation=0.0)
    return _one(body.fuse(hexb))


def _stud_proto():
    return bd.revolve(_face_xz([(0.0, -12.0), (3.0, -12.0), (3.6, -11.4), (3.6, 25.4), (3.0, 26.0), (0.0, 26.0)]),
                      axis=bd.Axis.Z)


def _nut_proto():
    body = _wrench_head(13.0, 0.0, 6.5, chamfer_bottom=True, rotation=0.0)
    return _one(body.cut(bd.Pos(0, 0, -1) * bd.Cylinder(3.75, 9.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))))


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _proto_parts():
    """[(name, shape, colour, seat_point_or_None, cut_on_section)] for cylinder 1, name uses {k}."""
    out = [("head_{k}", build_head_proto(), P.CAST_ALU, None, True),
           ("chamber_lining_{k}", _chamber_lining(), P.CERAMIC, None, True)]
    bolt = _bolt_proto()
    for v in ("I", "E"):
        out.append((f"seat_{{k}}{v}", _seat_insert(v), P.BRONZE, None, True))
        out.append((f"guide_{{k}}{v}", _guide(v), P.BRONZE, None, True))
        cover = _cover(v)
        out.append((f"cover_{{k}}{v}", cover, P.MACHINED_ALU, None, True))
        frames = _bolt_frames(v)
        for n, (p, z, x) in enumerate(frames, start=1):
            out.append((f"cover_bolt_{{k}}{v}_{n}", geo.plane(p, z, x).location * bolt, P.FASTENER, p, False))
        bolts = [geo.plane(p, z, x).location * bolt for p, z, x in frames]
        for n_w, (i, j, w) in enumerate(_wires(v, frames, [cover] + bolts), start=1):
            seat_pt = frames[i][0] if geo.in_section(frames[i][0]) else frames[j][0]
            out.append((f"cover_wire_{{k}}{v}_{n_w}", w, P.SAFETY_WIRE, seat_pt, False))
    plug = _plug_proto()
    for k in ("F", "R"):
        out.append((f"plug_{{k}}{k}", geo.plane(PLUG_FACE[k], PLUG_AXIS[k], (1.0, 0.0, 0.0)).location * plug,
                    P.STEEL_POLISHED, PLUG_FACE[k], False))
    stud, nut = _stud_proto(), _nut_proto()
    c = EXHAUST_FLANGE["centre"]
    for n, h in enumerate(EXHAUST_FLANGE["studs_h"], start=1):
        seat_pt = (c[0], c[1], h)
        out.append((f"exhaust_stud_{{k}}_{n}", geo.plane(seat_pt, (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)).location * stud,
                    P.FASTENER, seat_pt, False))
        nut_pt = (c[0], EXHAUST_FLANGE["nut_seat_y"], h)
        out.append((f"exhaust_nut_{{k}}_{n}", geo.plane(nut_pt, (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)).location * nut,
                    P.FASTENER, nut_pt, False))
    return out


def _step_roundtrip_ok(shape, tol=0.5):
    """Export to STEP and read back: the bounding box must survive (a cut face
    has once come back from STEP as a metre-long runaway surface)."""
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        bd.export_step(shape, path)
        back = bd.import_step(path)
        a, b = shape.bounding_box(), back.bounding_box()
        return all(abs(getattr(getattr(a, m), c) - getattr(getattr(b, m), c)) <= tol
                   for m in ("min", "max") for c in "XYZ")
    finally:
        os.remove(path)


def _sane_piece(r, shape, allow_bigger=False):
    if r is None or not r.solids():
        return False
    bb0, bb = shape.bounding_box(), r.bounding_box()
    tol = 0.05
    return ((allow_bigger or r.volume <= shape.volume * (1 + 1e-6) + 1e-6) and r.volume > 0
            and bb.min.X >= bb0.min.X - tol and bb.max.X <= bb0.max.X + tol
            and bb.min.Y >= bb0.min.Y - tol and bb.max.Y <= bb0.max.Y + tol
            and bb.min.Z >= bb0.min.Z - tol and bb.max.Z <= bb0.max.Z + tol
            and all(geo.sound(sol) for sol in r.solids()) and _step_roundtrip_ok(r))


def _section_cut(shape, label):
    """Cylinder 1's museum section (rear half) with its red paint skin:
    (kept, skin|None). Both pieces must be no bigger than the part, lie inside
    its box, be sound and survive a STEP round trip, or the build stops."""
    bb0 = shape.bounding_box()
    if bb0.max.Y <= 0.0 or bb0.min.Y >= geo.SECTION_Y_MAX:
        return shape, None
    tries = [lambda: geo.cut_with_skin(shape, "section")]

    def slab_way():
        slab = bd.Pos(-400.0, 0.0, 300.0) * bd.Box(800.0, geo.SECTION_Y_MAX, 1000.0,
                                                   align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
        paint = bd.Pos(-400.0, 0.0, 300.0) * bd.Box(800.0, geo.SKIN_T, 1000.0,
                                                    align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
        return shape - slab, shape & paint
    tries.append(slab_way)
    for attempt in tries:
        try:
            kept, skin = attempt()
        except Exception:
            continue
        if kept is shape or not _sane_piece(kept, shape):
            continue
        if skin is not None and not _sane_piece(skin, shape):
            continue
        return kept, skin
    raise RuntimeError(f"{label}: section cut failed the volume/bbox/STEP sanity check")


def build():
    protos = _proto_parts()
    parts = []
    for k in range(1, S.N_CYL + 1):
        for name, shape, colour, seat_pt, cut in protos:
            label = "heads:" + name.format(k=k)
            if k == geo.SECTION_CYL:
                if seat_pt is not None and geo.in_section(seat_pt):
                    continue
                if cut:
                    shp, skin = _section_cut(shape, label)
                    if skin is not None:
                        sk = skin.solids()
                        skin = sk[0] if len(sk) == 1 else bd.Compound(list(sk))
                        parts.append(P.style(skin, "heads:section_skin_" + name.format(k=k), P.SECTION_RED))
                else:
                    shp = shape
                sols = shp.solids()
                if not sols:
                    continue
                # keep every real piece (a twisted wire keeps both strands);
                # drop only cut crumbs
                vmax = max(s.volume for s in sols)
                keep = [s for s in sols if s.volume >= 0.05 * vmax]
                if name.startswith("head_") and len(keep) > 1:
                    raise RuntimeError(f"{label}: the section cut split the casting")
                shp = keep[0] if len(keep) == 1 else bd.Compound(keep)
            else:
                shp = geo.on_cylinder(shape, k)
            parts.append(P.style(shp, label, colour))
    return parts
