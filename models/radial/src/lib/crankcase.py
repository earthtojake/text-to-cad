"""Crankcase: the split, forged-aluminium power-section case.

Two halves split on the cylinder-row plane y = 0 (a 0.5 mm parting gap reads
as the joint line), satin silver-grey enamel. The form is a drum (r 262,
y -112..112) carrying nine machined cylinder pads (bosses R 98 along each
cylinder axis, faced at h 282, bore O162 through), blended into the drum by
cast root fillets so that between the pads the case reads as a nine-lobed,
forged form. Between every pair of cylinders a through-bolt boss (axis along
Y at r 272) carries the bolt that clamps the halves.

Interior: a revolved cavity (r 200, |y| <= 72) plus the nine barrel bores
from h 100 outward; main-bearing housings for the crankshaft builder's
bearings (OD 140): front y -100..-72 in a separate housing ring carried by
the three window webs, rear y 72..100 in the rear wall, both with a
retaining lip.

Museum cuts: the front half carries geo.window_cutter() (annulus r 70..238
opened for y < -60, three webs). The case is not touched by the cylinder-1
section (that is its rear half, beyond r 300).

INTERFACES
  * Hold-down studs O9.5 on PCD 170 clocked 15 + 30 j deg from +t toward +y
    (the barrel builder's convention); tips at h 301.0 (barrels: <= 301.5 so
    the castellated-nut safety wire clears them).
  * Nose flange: the window leaves only the ring r 238..262 of the front face
    standing, so the nose-case studs are on r 250 (not 228): 18 x M10 at
    10 + 20 j deg in-plane; nuts assume a 12 mm nose-case flange (seat y -124),
    studs and nuts omitted in the nose-cut sector.
  * Blower flange: 18 x M10 studs on r 245 at 10 + 20 j deg; nuts assume a
    12 mm blower flange (seat y +124).
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("case_silver", "fastener", "machined_alu", "safety_wire", "section_red", "steel_machined")

# ---------------------------------------------------------------------------
# Numbers (mm)
# ---------------------------------------------------------------------------
Y_FACE = S.CRANKCASE_Y[1]           # 112
R_DRUM = S.CRANKCASE_R_BETWEEN      # 262
R_EDGE = 4.0                        # drum front/rear edge round
GAP = 0.25                          # half the parting gap
R_PAD = 98.0                        # pad boss radius (barrel flange OD 188)
H_PAD = S.H_PAD                     # 282
SKIN_T = 0.5                        # machined spot-face skin
H_PAD_BODY = H_PAD - SKIN_T
H_PAD_ROOT = 200.0
R_CASE_BORE = 81.0                  # O162
H_BORE0 = 100.0
BORE_CH = 2.5                       # pad-mouth chamfer
R_CAV = 200.0
Y_CAV = 72.0
R_BRG = 70.0                        # bearing OD 140
R_LIP = 62.0
R_TB = 272.0                        # through-bolt boss axis radius
R_TB_BOSS = 15.0
Y_TB = 72.0                         # boss half length
Y_TB_EYE = 54.0                     # rear end of the boss under a lifting eye
TB_D = 10.0
MIDLINES = [20.0 + 40.0 * j for j in range(9)]
EYE_MIDLINES = (60.0, 300.0)        # lifting eyes on the upper flanks (clear of the cyl-1 rear section)
R_EYE_BOSS = 18.0
Y_EYE_BOSS = 90.0
R_EYE_SEAT = 290.0
PLUG_MIDLINES_REAR = (140.0, 180.0, 220.0)   # drain + oil-scavenge ports
PLUG_MIDLINES_FRONT = (180.0,)
Y_PLUG = 99.0
R_PLUG_BOSS = 11.0
R_PLUG_SEAT = 276.0
FRONT_FLANGE_R = 250.0
REAR_FLANGE_R = 245.0
FLANGE_STUDS = 18
FLANGE_PHASE = 10.0
MATE_FLANGE_T = 12.0
STUD_D = 9.5
STUD_PHASES = [15.0 + 30.0 * j for j in range(S.HOLD_DOWN_STUDS)]
STUD_TIP_H = 301.0
WIRE_D = 0.8
R_M10_STUD = F.minor_diameter(10.0) / 2.0 - 0.05   # flange studs: nut-minor radius (runs in the nut bore)
HOLE_CLR = 0.15                                    # tapped-hole root clearance
R_TB_SHANK = (TB_D - 0.6495 * F.pitch(TB_D)) / 2.0  # fasteners' simplified shank radius
STUD_IN = 14.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _arc_pts(cx, cy, r, a0, a1, n=8):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _rev_z(points):
    """Solid of revolution about +Z from a closed (r, z) polygon."""
    face = bd.make_face(bd.Polyline(*[(r, 0.0, z) for r, z in points], close=True).edges())
    return bd.revolve(face, axis=bd.Axis.Z, revolution_arc=360.0)


def _radial_cyl(b_deg, r0, r1, rad, y):
    """Cylinder of radius `rad` along the radial at in-plane angle b, radii r0..r1, station y."""
    return geo.cyl_along(S.inplane(b_deg, r0, y), S.inplane(b_deg, r1, y), 2 * rad)


def _one(shape):
    sols = shape.solids()
    if len(sols) == 1:
        return sols[0]
    return max(sols, key=lambda s: s.volume)


def _style(shape, label, color):
    return P.style(shape, label, color)


# ---------------------------------------------------------------------------
# The cast body
# ---------------------------------------------------------------------------
def _drum():
    e = R_EDGE
    prof = [(0.0, -Y_FACE), (R_DRUM - e, -Y_FACE)]
    prof += _arc_pts(R_DRUM - e, -Y_FACE + e, e, -90, 0)[1:-1]
    prof += [(R_DRUM, -Y_FACE + e), (R_DRUM, Y_FACE - e)]
    prof += _arc_pts(R_DRUM - e, Y_FACE - e, e, 0, 90)[1:-1]
    prof += [(R_DRUM - e, Y_FACE), (0.0, Y_FACE)]
    return geo.revolve_y(prof)


def _pad_boss_proto():
    return bd.Pos(0, 0, H_PAD_ROOT) * bd.Cylinder(
        R_PAD, H_PAD_BODY - H_PAD_ROOT, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))


def _tb_span(b):
    return (-Y_TB, Y_TB_EYE if b in EYE_MIDLINES else Y_TB)


def _outer_body():
    parts = [_drum()]
    pad = _pad_boss_proto()
    parts += [geo.on_cylinder(pad, k) for k in range(1, S.N_CYL + 1)]
    for b in MIDLINES:
        x, _, z = S.inplane(b, R_TB)
        y0, y1 = _tb_span(b)
        parts.append(geo.cyl_y(y0, y1, 2 * R_TB_BOSS, x, z))
    for b in EYE_MIDLINES:
        parts.append(_radial_cyl(b, 240.0, R_EYE_SEAT, R_EYE_BOSS, Y_EYE_BOSS))
    for b in PLUG_MIDLINES_REAR:
        parts.append(_radial_cyl(b, 245.0, R_PLUG_SEAT, R_PLUG_BOSS, Y_PLUG))
    for b in PLUG_MIDLINES_FRONT:
        parts.append(_radial_cyl(b, 245.0, R_PLUG_SEAT, R_PLUG_BOSS, -Y_PLUG))
    body = parts[0].fuse(*parts[1:]).clean()
    body = _one(body)
    # cast root blends: every intersection curve (boss/drum, pad/pad, boss/pad)
    def keep(e):
        gt = e.geom_type.name if hasattr(e.geom_type, "name") else str(e.geom_type)
        if gt in ("LINE", "CIRCLE"):
            return False
        bb = e.bounding_box()
        return abs(bb.min.Y) < Y_FACE - 2 and abs(bb.max.Y) < Y_FACE - 2
    edges = [e for e in body.edges() if keep(e)]
    body, got = C.safe_fillet(body, edges, 7.0, min_r=2.0)
    if got is None:
        body, got = C.fillet_all(body, 6.0, exclude=lambda e: not keep(e), min_r=1.5)
    _INFO["root_fillet"] = got
    # soften the through-bolt boss and port-boss end rims (small, cast)
    return body


def _interior_tools():
    prof = [(0.0, -Y_FACE - 1), (R_BRG, -Y_FACE - 1), (R_BRG, -Y_CAV)]
    rc = 10.0
    prof += [(R_CAV - rc, -Y_CAV)] + _arc_pts(R_CAV - rc, -Y_CAV + rc, rc, -90, 0)[1:-1]
    prof += [(R_CAV, -Y_CAV + rc), (R_CAV, Y_CAV - rc)]
    prof += _arc_pts(R_CAV - rc, Y_CAV - rc, rc, 0, 90)[1:-1]
    prof += [(R_CAV - rc, Y_CAV), (R_BRG, Y_CAV), (R_BRG, 100.0), (R_LIP, 100.0),
             (R_LIP, Y_FACE + 1), (0.0, Y_FACE + 1)]
    cavity = geo.revolve_y(prof)
    # barrel bore O162 from h 100 (the barrel skirt reaches down to h 205), with
    # a 45 deg lead-in chamfer at the pad mouth
    bore = _rev_z([(0.0, H_BORE0), (R_CASE_BORE, H_BORE0), (R_CASE_BORE, H_PAD - BORE_CH - SKIN_T),
                   (R_CASE_BORE + BORE_CH, H_PAD - SKIN_T), (R_CASE_BORE + BORE_CH, 500.0), (0.0, 500.0)])
    bores = [geo.on_cylinder(bore, k) for k in range(1, S.N_CYL + 1)]
    inner = cavity.fuse(*bores).clean()
    holes = []
    for b in MIDLINES:
        x, _, z = S.inplane(b, R_TB)
        y0, y1 = _tb_span(b)
        holes.append(geo.cyl_y(y0 - 1, y1 + 1, 10.5, x, z))
    return [inner] + holes


def _front_housing():
    """Front main-bearing housing ring (bearing y -100..-72), carried by the webs."""
    return geo.revolve_y([(R_LIP, -Y_FACE), (91.0, -Y_FACE), (92.0, -Y_FACE + 1.0), (92.0, -73.0),
                          (89.0, -70.0), (R_BRG, -70.0), (R_BRG, -100.0), (R_LIP, -100.0)])


WEB_W = 18.0          # slimmer than geo.WINDOW_WEB_W (26): the cut stays a superset of geo's


def _window_cutter(t: float = 0.0):
    """geo.window_cutter() rebuilt with true circular arcs (geo's are 3 deg
    polyline facets) and slimmer webs: a strict superset of geo's region.
    `t` erodes it (for the red paint band on the cut faces)."""
    r0, r1 = geo.WINDOW_R[0] - 0.2 + t, geo.WINDOW_R[1] + 0.2 - t
    ring = geo.revolve_y([(r0, -400.0), (r1, -400.0), (r1, geo.WINDOW_Y_MAX - t), (r0, geo.WINDOW_Y_MAX - t)])
    webs = []
    for b in geo.WINDOW_WEB_ANGLES:
        web = bd.Box(WEB_W + 2 * t, 400.0, geo.WINDOW_R[1] + 20,
                     align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.MIN))
        webs.append(geo.axis_rotation(S.ROT_AXIS, b) * bd.Pos(0, geo.WINDOW_Y_MAX + 1, 0) * web)
    return ring - webs


def _pad_stud_points():
    """(k, j, t, y) of every hold-down stud (all 108; callers filter)."""
    r = S.HOLD_DOWN_PCD / 2.0
    for k in range(1, S.N_CYL + 1):
        for j, a in enumerate(STUD_PHASES, start=1):
            yield k, j, r * math.cos(math.radians(a)), r * math.sin(math.radians(a))


def _pad_stud_hole(t, y):
    """Cylinder-1-frame tapped hole for the stud at (t, y)."""
    return bd.Pos(t, y, H_PAD - STUD_IN - 0.5) * bd.Cylinder(
        STUD_D / 2.0 + HOLE_CLR, STUD_IN + 1.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))


def _hole_tools():
    """Every tapped/drilled hole in the case (none overlaps another)."""
    tools = []
    for k, j, t, y in _pad_stud_points():
        tools.append(geo.on_cylinder(_pad_stud_hole(t, y), k))
    for i in range(FLANGE_STUDS):
        b = FLANGE_PHASE + 360.0 * i / FLANGE_STUDS
        x, _, z = S.inplane(b, FRONT_FLANGE_R)
        tools.append(geo.cyl_y(-Y_FACE - 1.0, -Y_FACE + STUD_IN + 0.5, 2 * (R_M10_STUD + HOLE_CLR), x, z))
        x, _, z = S.inplane(b, REAR_FLANGE_R)
        tools.append(geo.cyl_y(Y_FACE - STUD_IN - 0.5, Y_FACE + 1.0, 2 * (R_M10_STUD + HOLE_CLR), x, z))
    for b in MIDLINES:
        # spot faces clearing the root blends round the through-bolt head and nut
        x, _, z = S.inplane(b, R_TB)
        y0, y1 = _tb_span(b)
        tools.append(geo.cyl_y(y0 - 12.0, y0, 23.5, x, z))
        tools.append(geo.cyl_y(y1, y1 + 12.0, 23.5, x, z))
    for b in EYE_MIDLINES:
        tools.append(_radial_cyl(b, R_EYE_SEAT - 10.0, R_EYE_SEAT + 1.0, 5.25, Y_EYE_BOSS + 10.0))
    for b, s_ in _port_list():
        tools.append(_radial_cyl(b, R_PLUG_SEAT - 12.0, R_PLUG_SEAT + 1.0, 6.2, s_ * Y_PLUG))
    return tools


def _port_list():
    return [(b, 1.0) for b in PLUG_MIDLINES_REAR] + [(b, -1.0) for b in PLUG_MIDLINES_FRONT]


_INFO: dict = {}
_CACHE: dict = {}


def halves():
    if "halves" in _CACHE:
        return _CACHE["halves"]
    import time
    t0 = time.time()
    body = _outer_body()
    _INFO["t_outer"] = round(time.time() - t0)
    body = C.cut_all(body, _interior_tools())
    _INFO["t_cut"] = round(time.time() - t0)
    big = 1200.0
    front_box = bd.Pos(0, -GAP, 0) * bd.Box(big, 400.0, big, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.CENTER))
    rear_box = bd.Pos(0, GAP, 0) * bd.Box(big, 400.0, big, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
    front = _one(body & front_box)
    rear = _one(body & rear_box)
    # museum cuts on the front half, then the bearing housing the webs carry
    # red paint skin: the SKIN_T layer of the uncut half just inside the removed
    # region, against every cut face (the bearing housing is added after the cut)
    band = _window_cutter() - _window_cutter(geo.SKIN_T)
    skin = (front & band) - _front_housing()
    front = _one(front - _window_cutter())
    front = _one(front.fuse(_front_housing()).clean())
    tools = _hole_tools()
    front = _one(C.cut_all(front, [t for t in tools if t.bounding_box().max.Y < 0]))
    rear = _one(C.cut_all(rear, [t for t in tools if t.bounding_box().min.Y > 0]))
    _INFO["t_halves"] = round(time.time() - t0)
    _CACHE["halves"] = (front, rear)
    _CACHE["skin"] = skin
    return front, rear


# ---------------------------------------------------------------------------
# Machined skins (pad spot faces, flange faces)
# ---------------------------------------------------------------------------
def _pad_skin_proto():
    ri = R_CASE_BORE + BORE_CH
    return _rev_z([(ri, H_PAD_BODY), (R_PAD, H_PAD_BODY), (R_PAD, H_PAD - 0.25),
                   (R_PAD - 0.25, H_PAD), (ri + 0.25, H_PAD), (ri, H_PAD - 0.25)])


def _skins():
    out = []
    proto = _pad_skin_proto()
    proto = C.cut_all(proto, [_pad_stud_hole(t, y) for k, j, t, y in _pad_stud_points() if k == 1])
    fbox = bd.Pos(0, -GAP, 0) * bd.Box(1200, 300, 1200, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.CENTER))
    rbox = bd.Pos(0, GAP, 0) * bd.Box(1200, 300, 1200, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
    pf, pr = _one(proto & fbox), _one(proto & rbox)
    for k in range(1, S.N_CYL + 1):
        out.append(_style(geo.on_cylinder(pf, k), f"crankcase:pad_face_front_{k}", P.MACHINED_ALU))
        out.append(_style(geo.on_cylinder(pr, k), f"crankcase:pad_face_rear_{k}", P.MACHINED_ALU))
    return out


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def _fast(shape, label):
    return _style(shape, label, P.FASTENER)


def _pad_studs():
    out = []
    length_out = STUD_TIP_H - H_PAD
    # stepped stud: full O9.5 through the barrel flange, thread relieved to the
    # nut's minor diameter above the washer so the barrel builder's castellated
    # nut runs on it without interference
    r_full = STUD_D / 2.0
    r_thr = F.minor_diameter(STUD_D) / 2.0 - 0.05
    h_step = S.H_FLANGE_TOP - H_PAD + 0.6
    proto = _rev_z([(0.0, -STUD_IN), (r_full - 0.6, -STUD_IN), (r_full, -STUD_IN + 0.6), (r_full, h_step),
                    (r_thr, h_step + 0.6), (r_thr, length_out - 0.5), (r_thr - 0.5, length_out),
                    (0.0, length_out)])
    for k, j, t, y in _pad_stud_points():
        out.append(_fast(geo.on_cylinder(bd.Pos(t, y, H_PAD) * proto, k), f"crankcase:stud_{k}_{j:02d}"))
    return out


def _flange_hardware():
    out = []
    lo = MATE_FLANGE_T + 13.0
    r = R_M10_STUD
    stud = _rev_z([(0.0, -STUD_IN), (r - 0.6, -STUD_IN), (r, -STUD_IN + 0.6), (r, lo - 0.6),
                   (r - 0.6, lo), (0.0, lo)])
    nut = F.flange_nut(10.0)
    for i in range(FLANGE_STUDS):
        b = FLANGE_PHASE + 360.0 * i / FLANGE_STUDS
        # nose (front) flange
        seat = S.inplane(b, FRONT_FLANGE_R, -Y_FACE)
        nseat = S.inplane(b, FRONT_FLANGE_R, -Y_FACE - MATE_FLANGE_T)
        if not geo.in_nose_cut(nseat):
            radial = S.inplane(b)
            out.append(_fast(F.place(stud, seat, (0, -1, 0), radial), f"crankcase:nose_stud_{i + 1}"))
            out.append(_fast(F.place(nut, nseat, (0, -1, 0), radial), f"crankcase:nose_nut_{i + 1}"))
        # blower (rear) flange
        seat = S.inplane(b, REAR_FLANGE_R, Y_FACE)
        radial = S.inplane(b)
        out.append(_fast(F.place(stud, seat, (0, 1, 0), radial), f"crankcase:blower_stud_{i + 1}"))
        nseat = S.inplane(b, REAR_FLANGE_R, Y_FACE + MATE_FLANGE_T)
        out.append(_fast(F.place(nut, nseat, (0, 1, 0), radial), f"crankcase:blower_nut_{i + 1}"))
    return out


def _through_bolts():
    out = []
    tb_nut = _one(F.flange_nut(TB_D) - bd.Pos(0, 0, -1) * bd.Cylinder(
        R_TB_SHANK + 0.1, 30.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    for n, b in enumerate(MIDLINES, start=1):
        y0, y1 = _tb_span(b)
        radial = S.inplane(b)
        head = S.inplane(b, R_TB, y0)
        tail = S.inplane(b, R_TB, y1)
        length = (y1 - y0) + 12.0
        bolt = F.place(F.hex_flange_bolt(TB_D, length), head, (0, -1, 0), radial)
        nut = F.place(tb_nut, tail, (0, 1, 0), radial)
        out.append(_fast(bolt, f"crankcase:through_bolt_{n}"))
        out.append(_fast(nut, f"crankcase:through_nut_{n}"))
    return out


def _lifting_eyes():
    out = []
    eye = F.lifting_eye()
    bolt = F.hex_flange_bolt(10.0, 16.0)
    for n, b in enumerate(EYE_MIDLINES, start=1):
        radial = S.inplane(b)
        hole = S.inplane(b, R_EYE_SEAT, Y_EYE_BOSS + 10.0)       # foot centre on the boss, strap leans forward
        out.append(_style(F.place(eye, hole, radial, (0, -1, 0)), f"crankcase:lifting_eye_{n}", P.STEEL_MACHINED))
        seat = S.inplane(b, R_EYE_SEAT + 10.0, Y_EYE_BOSS + 10.0)
        out.append(_fast(F.place(bolt, seat, radial, (0, -1, 0)), f"crankcase:lifting_eye_bolt_{n}"))
    return out


def _wire(points):
    path = bd.Spline(*[bd.Vector(*p) for p in points])
    t0 = path.tangent_at(0.0)
    prof = bd.Plane(origin=path.position_at(0.0), z_dir=t0) * bd.Circle(WIRE_D / 2.0)
    return _one(bd.sweep(prof, path=path, is_frenet=False))


def _ports(tb_parts):
    out = []
    plug = F.hex_flange_bolt(12.0, 10.0)
    ports = [(b, 1.0) for b in PLUG_MIDLINES_REAR] + [(b, -1.0) for b in PLUG_MIDLINES_FRONT]
    for b, s in ports:
        radial = S.inplane(b)
        name = ("drain" if b == 180.0 else f"scavenge_{1 if b < 180 else 2}") + ("_rear" if s > 0 else "_front")
        plug_p = F.place(plug, S.inplane(b, R_PLUG_SEAT, s * Y_PLUG), radial, (0, 1, 0))
        out.append(_fast(plug_p, f"crankcase:{name}_bolt"))
        # safety wire: plug head -> the through-bolt nut/head beside it
        ys = s * Y_PLUG
        yb = s * (Y_TB + 5.0)
        pts = [S.inplane(b, R_PLUG_SEAT + 6.0, ys - s * 6.0),
               S.inplane(b, R_PLUG_SEAT + 8.0, ys - s * 11.0),
               S.inplane(b, R_TB + 11.0, (ys + yb) / 2.0 - s * 4.0),
               S.inplane(b, R_TB + 6.5, yb)]
        n_tb = MIDLINES.index(b) + 1
        anchor = tb_parts[f"crankcase:through_{'nut' if s > 0 else 'bolt'}_{n_tb}"]
        wire = _one(_wire(pts) - [plug_p, anchor])       # ends ON the plug and the nut/head
        out.append(_style(wire, f"crankcase:{name}_wire", P.SAFETY_WIRE))
    return out


# ---------------------------------------------------------------------------
def build() -> list:
    front, rear = halves()
    parts = [_style(front, "crankcase:front_half", P.CASE_SILVER),
             _style(rear, "crankcase:rear_half", P.CASE_SILVER)]
    parts.append(_style(_CACHE["skin"], "crankcase:section_skin_front_half", P.SECTION_RED))
    parts += _skins()
    parts += _pad_studs()
    parts += _flange_hardware()
    parts += _through_bolts()
    parts += _lifting_eyes()
    parts += _ports({p.label: p for p in parts if p.label.startswith("crankcase:through_")})
    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    print(f"{len(ps)} leaves in {time.time() - t0:.0f}s; info {_INFO}")
    bad = [p.label for p in ps if not geo.sound(p)]
    print("unsound:", bad)
