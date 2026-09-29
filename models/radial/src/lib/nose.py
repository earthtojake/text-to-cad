"""Nose system: the nose case, its thrust-bearing housing and front cover, the
governor, and their hardware.

THE CASE (`nose:case`, one casting, satin silver-grey)
  * rear flange y -112..-124, r 262, mating the crankcase's front ring; 18 holes
    O10.5 on r 250 at in-plane 10 + 20 j for the crankcase's own studs + nuts
    (crankcase:nose_stud_* / nose_nut_*, nuts seated on y -124). The flange
    front face carries a machined band (`nose:flange_face`, y -124..-123.6).
  * cam section: a drafted dome (r ~200) over the cam ring, cavity r 176,
    y -112..-198; nine TWIN tappet-guide bosses (one per cylinder, I + E fused),
    each bored O34.1 along its tappet axis for the cam builder's bronze guide,
    counterbored O38.8 to the guide flange seat (s 215.5), and faced
    perpendicular to its pushrod rest axis at spec.PUSHROD_TUBE_START (16 mm)
    from the bottom ball: the pushrod tube's packing nut seats there (bright
    spot-face skins `nose:boss_face_<k>`).
  * cam hub: a sleeve r 120..124.7, y -198..-167.5 (the cam ring's bronze
    bushing, bore r 125, rides on it; 0.3 mm running clearance).
  * idler boss: r 16.5 about the cam idler axis (in-plane -30, r 100),
    y -198..-164, blind-bored O22.1 from y -192.5 for cam:idler_shaft.
  * diaphragm y -212..-198 (bore r 38 round the crank nose), reduction chamber
    r 140 over y -212..-305, outer housing r 160, governor pad at in-plane 30
    (machined face r 174), drain boss (dome) + breather boss (housing) at the
    bottom, joint flange at the front
    y -289..-305 (r 174) carrying 18 x M8 studs on r 160.
THRUST HOUSING (`nose:thrust_housing`): rear face y -305 (joint face r 140..174
  + the SUN ANCHOR face r 61.5..140 in one machined plane), web y -305..-320
  with bore O123 (sun spigot), flat front face y -320 (the reduction's sun
  support flange seats in front of it) and 12 x O8.4 through holes on r 85 at
  15 + 30 j for its bolts;
  ogive nose to r 110 ending y -392; steel liner (`nose:thrust_liner`) bore O160
  y -392..-360 = the thrust-bearing seat (shoulder face at y -360).
FRONT COVER (`nose:front_cover`) y -392..-408, seal bore O94, 18 x M6 bolts on
  r 97 wired in pairs.
GOVERNOR on the pad at in-plane 30: base, drafted body, cap, control shaft + arm.

MUSEUM CUT: the nose cutaway sector (in-plane -100..12, r > 60) as a true-arc
tool, applied to every static body here, minus what deliberately stays standing
in it: the idler boss + a 30 mm diaphragm arm carrying it; the flange ring
outside the crankcase window (r > 238, with nose-supplied flange nuts on the
crankcase studs there), so the line of sight reaches the rods; and, for
cylinders 1, 8, 9, the half-bosses cut on the planes through their tappet axes
(y -178 intake side, y -152 exhaust side) so each bronze guide sits whole in a
half-bore, each tied to the ring by one 10 mm radial rib on the cylinder axis. Other hardware seated in
the removed region is omitted.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo, kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("case_silver", "fastener", "gasket", "machined_alu", "safety_wire", "steel_machined")

# ---------------------------------------------------------------------------
# Numbers (mm, engine frame)
# ---------------------------------------------------------------------------
Y_REAR = S.CRANKCASE_Y[0]          # -112
FLANGE_R = 262.0
FLANGE_FACE_Y = -124.0
SKIN = 0.4
STUD_R, STUD_N, STUD_PHASE = 250.0, 18, 10.0      # crankcase's nose studs

SH = S.NOSE_SHIFT                 # the whole nose (not the rear ring) moved forward
RING_R0 = 238.0                    # rear ring: outside the crankcase window (r < 238)
SPOKE_ANGLES = geo.WINDOW_WEB_ANGLES   # spokes sit in front of the crankcase window webs
SPOKE_W, SPOKE_T = 20.0, 12.0 - SKIN   # front face flush with the ring's cast face
NECK_BORE_R = 45.0
CAM_REAR_Y = -238.0                # cam-section rear face (the neck runs to it)
CAM_REAR_IN_Y = -246.0             # rear wall inner face (idler big gear from -249.5)
# The case is TWO bolted castings split on the rear wall's inner face, so the front
# casting (cam dome + bosses, hub, diaphragm, reduction housing) withdraws forward and
# the cam ring then slides forward off... nothing: the hub leaves with the front casting.
SPLIT_Y = CAM_REAR_IN_Y            # case_rear: y > SPLIT_Y; gasket; case_front: y < SPLIT_Y - GASKET_T
GASKET_T = 0.5
LUG_ANGLES = [20.0 + 40.0 * j for j in range(9)]   # nine joint lugs on the cylinder midlines
LUG_R = (190.0, 211.0)             # inside the cutaway's retained shoulder arc (r 172..212)
LUG_Y = (-236.0, -256.0)
LUG_W = 20.0
LUG_STUD_R = 203.0

CAV_R = 176.0
CAV_FRONT_Y = -198.0 + SH
HUB_R = (120.0, 124.7)
HUB_END_Y = -167.5 + SH
DIA_FRONT_Y = -212.0 + SH
DIA_BORE_R = 46.0                  # clears the crank's bell-flange hub (r 44, y -366..-340) by 2
RED_CAV_R = 140.0
HOUSING_R = 160.0
JOINT_Y = -305.0 + SH
JOINT_FLANGE = (-289.0 + SH, 174.0)     # (rear face y, outer r)
JOINT_STUD_R = 160.0
TH_FLANGE_FRONT_Y = -317.0 + SH
WEB_FRONT_Y = -320.0 + SH
WEB_BORE_R = 61.5
NOSE_R = 110.0
NOSE_FRONT_Y = -392.0 + SH
SEAT_R = 80.0                      # thrust-bearing outer-race seat (liner bore)
LINER_OR = 86.0
SEAT_BACK_Y = -360.0 + SH
SUN_BOLT_R, SUN_BOLT_N, SUN_BOLT_PHASE = 85.0, 12, 15.0
COVER_T = 9.0
COVER_BOLT_R = 97.0

IDLER_BOSS_R = 16.5
IDLER_BOSS_Y = (-198.0 + SH, -164.0 + SH)
IDLER_BORE_R = 11.05

GUIDE_BORE_R = 17.05               # cam guide OD 34
GUIDE_CB_R = 19.4                  # guide flange r 19
GUIDE_SEAT_S = 215.5               # guide flange underside (cam.GUIDE_S[1] - GUIDE_FLANGE[1])
BOSS_R_TOP = 23.5
BOSS_S0 = 182.0

GOV_B = 0.0                        # governor pad in-plane angle: on top
GOV_Y = -260.0 + SH
GOV_PAD = (42.0, 56.0)             # axial x tangential
GOV_R0, GOV_R1 = 150.0, 174.0      # pad buried base / machined face

CUT_KEEP_ANGLE = S.CAM_IDLER_ANGLE

CS, MA, FA, SW, ST = P.CASE_SILVER, P.MACHINED_ALU, P.FASTENER, P.SAFETY_WIRE, P.STEEL_MACHINED
_ROT = S.ROT_AXIS


# ---------------------------------------------------------------------------
# Profile revolve with true arcs and splines (r, y) about the crank axis
# ---------------------------------------------------------------------------
def _V(p):
    return bd.Vector(p[0], p[1], 0.0)


def _revolve(start, segs, arc=360.0):
    """segs: ("L", p) | ("A", mid, p) | ("S", [pts..], p, t0, t1). Closed back to start."""
    edges, cur = [], start
    for s in segs:
        if s[0] == "L":
            edges.append(bd.Line(_V(cur), _V(s[1])))
            cur = s[1]
        elif s[0] == "A":
            edges.append(bd.ThreePointArc(_V(cur), _V(s[1]), _V(s[2])))
            cur = s[2]
        else:
            _, mids, end, t0, t1 = s
            edges.append(bd.Spline(*[_V(cur)] + [_V(m) for m in mids] + [_V(end)],
                                   tangents=[bd.Vector(*t0, 0), bd.Vector(*t1, 0)]))
            cur = end
    if abs(cur[0] - start[0]) > 1e-9 or abs(cur[1] - start[1]) > 1e-9:
        edges.append(bd.Line(_V(cur), _V(start)))
    face = bd.Face(bd.Wire(edges))
    return bd.revolve(face, axis=bd.Axis.Y, revolution_arc=arc)


def _fillet_pt(corner, d_in, d_out, r):
    """Arc (start, mid, end) rounding a corner of a polyline that arrives along
    d_in and leaves along d_out (unit axis vectors in (r, y))."""
    cx, cy = corner
    s = (cx - d_in[0] * r, cy - d_in[1] * r)
    e = (cx + d_out[0] * r, cy + d_out[1] * r)
    c = (s[0] + d_out[0] * r, s[1] + d_out[1] * r)
    m = ((s[0] + e[0]) / 2 - c[0], (s[1] + e[1]) / 2 - c[1])
    n = math.hypot(*m)
    mid = (c[0] + m[0] / n * r, c[1] + m[1] / n * r)
    return s, mid, e


# ---------------------------------------------------------------------------
# Main case
# ---------------------------------------------------------------------------
def _case_revolve():
    """Neck + cam section + reduction housing + joint flange, one revolved casting.
    The neck (bore r 45 round the crank nose) stands on the crankcase's front
    main-bearing housing at y -112, waists to r ~84 and flares into the cam
    section's rear face at y -238; the gap around it (r 115..238) is open so the
    crankcase window and the rod star read from a front three-quarter view."""
    segs = []
    y_r = Y_REAR
    start = (NECK_BORE_R + 1.0, y_r)
    segs.append(("L", (112.0, y_r)))                 # sharp: the spokes' rear faces run into it
    segs.append(("L", (112.0, y_r - 1.5)))
    segs.append(("S", [(104.0, -132.0), (89.0, -158.0), (84.5, -182.0), (88.0, -205.0), (101.0, -224.0)],
                 (124.0, CAM_REAR_Y), (0, -1), (1, 0)))
    s_, m, e = _fillet_pt((202.0, CAM_REAR_Y), (1, 0), (0, -1), 14.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    # the drafted dome over the cam ring, rolling down onto the reduction housing
    segs.append(("S", [(200.3, -158.0 + SH), (196.0, -182.0 + SH), (186.0, -203.0 + SH),
                       (171.5, -219.0 + SH), (162.5, -229.0 + SH)],
                 (HOUSING_R, -236.0 + SH), (0, -1), (0, -1)))
    jy, jr = JOINT_FLANGE
    s_, m, e = _fillet_pt((HOUSING_R, jy), (0, -1), (1, 0), 6.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    segs.append(("L", (jr - 1.5, jy)))
    segs.append(("A", _fillet_pt((jr, jy), (1, 0), (0, -1), 1.5)[1], (jr, jy - 1.5)))
    segs.append(("L", (jr, JOINT_Y + 1.5)))
    segs.append(("A", _fillet_pt((jr, JOINT_Y), (0, -1), (-1, 0), 1.5)[1], (jr - 1.5, JOINT_Y)))
    segs.append(("L", (RED_CAV_R + 1.0, JOINT_Y)))
    segs.append(("L", (RED_CAV_R, JOINT_Y + 1.0)))
    s_, m, e = _fillet_pt((RED_CAV_R, DIA_FRONT_Y), (0, 1), (-1, 0), 5.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    segs.append(("L", (DIA_BORE_R + 1.0, DIA_FRONT_Y)))
    segs.append(("L", (DIA_BORE_R, DIA_FRONT_Y + 1.0)))
    segs.append(("L", (DIA_BORE_R, CAV_FRONT_Y - 1.0)))
    segs.append(("L", (DIA_BORE_R + 1.0, CAV_FRONT_Y)))
    s_, m, e = _fillet_pt((HUB_R[0], CAV_FRONT_Y), (1, 0), (0, 1), 2.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    segs.append(("L", (HUB_R[0], HUB_END_Y - 1.0)))
    segs.append(("L", (HUB_R[0] + 1.0, HUB_END_Y)))
    segs.append(("L", (HUB_R[1] - 1.0, HUB_END_Y)))
    segs.append(("L", (HUB_R[1], HUB_END_Y - 1.0)))
    s_, m, e = _fillet_pt((HUB_R[1], CAV_FRONT_Y), (0, -1), (1, 0), 3.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    s_, m, e = _fillet_pt((CAV_R, CAV_FRONT_Y), (1, 0), (0, 1), 8.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    s_, m, e = _fillet_pt((CAV_R, CAM_REAR_IN_Y), (0, 1), (-1, 0), 6.0)
    segs.append(("L", s_))
    segs.append(("A", m, e))
    segs.append(("L", (NECK_BORE_R + 1.0, CAM_REAR_IN_Y)))
    segs.append(("L", (NECK_BORE_R, CAM_REAR_IN_Y + 1.0)))
    segs.append(("L", (NECK_BORE_R, y_r - 1.0)))
    return _revolve(start, segs)


def joint_lug(b):
    """One joint lug on the dome's rear shoulder at in-plane b (split later by the
    joint plane): a block rising out of the shoulder with a round outer end."""
    zc = LUG_R[1] - LUG_W / 2
    y0, y1 = LUG_Y[1], LUG_Y[0]
    block = bd.Pos(0, y0, 170.0) * bd.Box(LUG_W, y1 - y0, zc - 170.0,
                                          align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    end = geo.cyl_y(y0, y1, LUG_W, 0.0, zc)
    return geo.axis_rotation(_ROT, b) * (block + end)


def rear_ring():
    """Rear ring on the crankcase's outer front ring (r 238..262, y -112..-124),
    carrying the 18 crankcase studs; its cast face sits SKIN under the machined band."""
    fy = FLANGE_FACE_Y + SKIN
    return _revolve((RING_R0, Y_REAR), [
        ("L", (FLANGE_R - 1.5, Y_REAR)),
        ("A", _fillet_pt((FLANGE_R, Y_REAR), (1, 0), (0, -1), 1.5)[1], (FLANGE_R, Y_REAR - 1.5)),
        ("L", (FLANGE_R, fy + 1.5)),
        ("A", _fillet_pt((FLANGE_R, fy), (0, -1), (-1, 0), 1.5)[1], (FLANGE_R - 1.5, fy)),
        ("L", (RING_R0, fy))])


def spoke(b):
    """Slim spoke from the neck foot to the rear ring at in-plane b, rear face on
    the crankcase face (in front of its window web), front edges rounded."""
    L = RING_R0 + 10.0 - 100.0
    box = bd.Box(SPOKE_W, SPOKE_T, L, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.MIN))
    fr = [e for e in box.edges() if e.bounding_box().size.Z > L - 1e-6 and e.bounding_box().min.Y < -SPOKE_T + 1e-6]
    box, _ = C.safe_fillet(box, fr, 4.0)
    return geo.axis_rotation(_ROT, b) * bd.Pos(0, Y_REAR, 100.0) * box


def _flange_skin():
    y0, y1 = FLANGE_FACE_Y, FLANGE_FACE_Y + SKIN
    return _revolve((RING_R0 + 1.9, y0), [("L", (FLANGE_R - 1.9, y0)), ("L", (FLANGE_R - 1.5, y1)),
                                          ("L", (RING_R0 + 1.5, y1))])


# ---------------------------------------------------------------------------
# Tappet-guide bosses (authored for cylinder 1, placed by rotation)
# ---------------------------------------------------------------------------
FACE_DROP = 0.3   # machined boss face this far below the spec seat plane: the packing nut seats
                  # stand pushrods.tube_axis `gap` (~0.12) above it and the cam guides' tops sit
                  # 0.25 below the nut seats, so the face stays at/below the guide tops


def _boss_plane(v):
    """(point, normal) of boss v's machined face: square to the pushrod rest axis
    at spec.PUSHROD_TUBE_START from the bottom ball, less FACE_DROP."""
    B, T = kin.pushrod_bottom0(1, v), kin.pushrod_top0(1, v)
    d = kin._unit(kin._sub(T, B))
    Fp = kin._addv(B, d, S.PUSHROD_TUBE_START - FACE_DROP)
    return Fp, d


def _tappet_frame(v):
    u = kin.tappet_dir(1, v)
    o = (0.0, S.TAPPET_Y[v], 0.0)
    return o, u


def _half_below(Fp, d, size=400.0):
    """Half-space on the -d side of the plane through Fp (finite box)."""
    box = bd.Box(size, size, size, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
    return geo.plane(Fp, d).location * box


BOSS_C = 15.5        # stadium centres at t = +-15.5 (the tappet axes cross z ~ 215 there)
BOSS_Z0, BOSS_H, BOSS_DRAFT = 182.0, 60.0, 2.0


def _boss_prism():
    """Untrimmed twin boss for cylinder 1: a drafted stadium along the cylinder
    axis enclosing both tappet axes (intake at +t / y -178, exhaust -t / -152)."""
    pI = (BOSS_C, S.TAPPET_Y["I"])
    pE = (-BOSS_C, S.TAPPET_Y["E"])
    L = math.dist(pI, pE)
    ang = math.degrees(math.atan2(pE[1] - pI[1], pE[0] - pI[0]))
    mid = ((pI[0] + pE[0]) / 2, (pI[1] + pE[1]) / 2)
    pl = bd.Plane(origin=(0, 0, BOSS_Z0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    sk = bd.Pos(mid[0], mid[1]) * bd.Rot(0, 0, ang) * bd.SlotCenterToCenter(L, 2 * BOSS_R_TOP + 2.0)
    return bd.extrude(pl * sk, amount=BOSS_H, taper=BOSS_DRAFT)


def _below_both(prism, shift):
    for v in kin.VALVES:
        Fp, d = _boss_plane(v)
        prism = prism & _half_below(kin._addv(Fp, d, -shift), d)
    return prism


def twin_boss():
    """Cylinder-1 twin boss, its two tube-seat faces SKIN below their planes."""
    return _below_both(_boss_prism(), SKIN)


def _guide_bore_tool(v):
    o, u = _tappet_frame(v)
    a = (u[0] * 168.0, o[1], u[2] * 168.0)
    c = (u[0] * 260.0, o[1], u[2] * 260.0)
    return geo.cyl_along(a, c, 2 * GUIDE_BORE_R)


def boss_skin():
    """The bright spot faces of the twin boss (cylinder 1), SKIN thick, bored."""
    prism = _boss_prism()
    skin = _below_both(prism, 0.0) - _below_both(prism, SKIN)
    return skin - [_guide_bore_tool("I"), _guide_bore_tool("E")]


# ---------------------------------------------------------------------------
# Idler boss, governor pad
# ---------------------------------------------------------------------------
def _idler_axis_xz():
    a = kin.cam_idler_axis_point()
    return a[0], a[2]


def idler_boss():
    x, z = _idler_axis_xz()
    y0, y1 = IDLER_BOSS_Y
    return geo.cyl_y(y0 - 2.0, y1, 2 * IDLER_BOSS_R, x, z)


def _gov_frame(r):
    return S.inplane(GOV_B, r, GOV_Y), S.inplane(GOV_B)


def _gov_plane(r=GOV_R0):
    o, n = _gov_frame(r)
    return geo.plane(o, n, (0, -1, 0))               # local +X = forward (-Y)


def _gov_locate(shape, r=GOV_R0):
    return _gov_plane(r).location * shape


def governor_pad_full():
    prism = C.drafted_prism(bd.RectangleRounded(GOV_PAD[0], GOV_PAD[1], 9.0), GOV_R1 - GOV_R0, 3.0)
    return prism


GOV_STUDS = [(sx * 13.0, sy * 19.0) for sx in (-1, 1) for sy in (-1, 1)]


# ---------------------------------------------------------------------------
# Bottom fittings: oil drain plug on the dome, breather on the reduction housing
# ---------------------------------------------------------------------------
DRAIN = (180.0, -208.0 + SH, 168.0, 192.0)      # in-plane, y, boss base r, boss face r
BREATHER = (180.0, -262.0 + SH, 150.0, 168.0)


def _radial_boss(spec, rad):
    b, y, r0, r1 = spec
    return geo.cyl_along(S.inplane(b, r0, y), S.inplane(b, r1, y), 2 * rad)


def bottom_bosses():
    return [_radial_boss(DRAIN, 11.0), _radial_boss(BREATHER, 10.0)]


def drain_plug():
    """Hex drain plug seated on the drain boss face, drilled head."""
    b, y, _, r1 = DRAIN
    head = F._wrench_head(14.0, 0.0, 8.0, chamfer_bottom=True)
    collar = bd.Cylinder(9.5, 1.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    shank = bd.Pos(0, 0, -12.0) * bd.Cylinder(6.0, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    plug = (bd.Pos(0, 0, 1.5) * head) + [collar, shank]
    return geo.locate(plug, S.inplane(b, r1, y), S.inplane(b), (0, 1, 0))


def breather():
    """Breather: hex union on the boss, a short vent tube with a flared lip."""
    b, y, _, r1 = BREATHER
    al = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    hexu = F._wrench_head(16.0, 0.0, 9.0, chamfer_bottom=True)
    tube = bd.Pos(0, 0, 8.5) * bd.Cylinder(5.0, 22.0, align=al)
    lip = bd.Pos(0, 0, 30.0) * bd.Cone(5.0, 6.5, 3.0, align=al)
    bore = bd.Pos(0, 0, 2.0) * bd.Cylinder(3.5, 40.0, align=al)
    shank = bd.Pos(0, 0, -10.0) * bd.Cylinder(6.0, 10.0, align=al)
    part = (hexu + [tube, lip, shank]) - bore
    return geo.locate(part, S.inplane(b, r1, y), S.inplane(b), (0, 1, 0))


# ---------------------------------------------------------------------------
# Thrust housing, liner, cover
# ---------------------------------------------------------------------------
def thrust_housing():
    jr = JOINT_FLANGE[1]
    fy = TH_FLANGE_FRONT_Y
    segs = [
        ("L", (jr - 1.5, JOINT_Y)),
        ("A", (jr - 1.5 + 1.5 * math.sqrt(0.5), JOINT_Y - 1.5 + 1.5 * math.sqrt(0.5)), (jr, JOINT_Y - 1.5)),
        ("L", (jr, fy + 1.5)),
        ("A", (jr - 1.5 + 1.5 * math.sqrt(0.5), fy + 1.5 - 1.5 * math.sqrt(0.5)), (jr - 1.5, fy)),
        ("L", (152.0, fy)),
        ("A", _fillet_pt((147.0, fy), (-1, 0), (0, -1), 5.0)[1], (147.0, fy - 5.0)),
        ("S", [(141.0, -334.0 + SH), (129.0, -347.0 + SH), (117.5, -359.0 + SH)], (NOSE_R, -376.0 + SH), (0, -1), (0, -1)),
        ("L", (NOSE_R, NOSE_FRONT_Y + 2.0)),
        ("A", (NOSE_R - 2 + 2 * math.sqrt(0.5), NOSE_FRONT_Y + 2 - 2 * math.sqrt(0.5)), (NOSE_R - 2.0, NOSE_FRONT_Y)),
        ("L", (LINER_OR + 0.8, NOSE_FRONT_Y)),
        ("L", (LINER_OR, NOSE_FRONT_Y + 0.8)),
        ("L", (LINER_OR, SEAT_BACK_Y)),
        ("L", (76.0, SEAT_BACK_Y)),
        ("L", (76.0, -352.0 + SH)),
        ("L", (95.0, -352.0 + SH)),
        ("S", [(106.0, -342.0 + SH), (117.0, -331.0 + SH)], (125.0, WEB_FRONT_Y), (0.55, 0.835), (0.9, 0.44)),
        ("L", (WEB_BORE_R + 1.0, WEB_FRONT_Y)),
        ("L", (WEB_BORE_R, WEB_FRONT_Y + 1.0)),
        ("L", (WEB_BORE_R, JOINT_Y - 1.0)),
    ]
    return _revolve((WEB_BORE_R + 1.0, JOINT_Y), segs)


def thrust_liner():
    y0, y1 = NOSE_FRONT_Y, SEAT_BACK_Y
    return _revolve((SEAT_R + 0.6, y0), [("L", (LINER_OR, y0)), ("L", (LINER_OR, y1)),
                                        ("L", (SEAT_R, y1)), ("L", (SEAT_R, y0 + 0.6))])


def front_cover():
    y0 = NOSE_FRONT_Y
    y1 = y0 - COVER_T
    yb = y1 - 7.0
    ro = NOSE_R - 3.0
    segs = [
        ("L", (ro, y0)),
        ("L", (ro, y1 + 1.5)),
        ("A", (ro - 1.5 + 1.5 * math.sqrt(0.5), y1 + 1.5 - 1.5 * math.sqrt(0.5)), (ro - 1.5, y1)),
        ("L", (66.0, y1)),
        ("A", _fillet_pt((62.0, y1), (-1, 0), (0, -1), 4.0)[1], (62.0, y1 - 4.0)),
        ("L", (62.0, yb + 1.2)),
        ("L", (60.8, yb)),
        ("L", (48.2, yb)),
        ("L", (47.0, yb + 1.2)),
        ("L", (47.0, y0)),
    ]
    return _revolve((47.0, y0), segs)


# ---------------------------------------------------------------------------
# Museum cut
# ---------------------------------------------------------------------------
def _sector(b0, b1, r0, r1, y0, y1):
    ring = _revolve((r0, y0), [("L", (r1, y0)), ("L", (r1, y1)), ("L", (r0, y1))], arc=b1 - b0)
    # revolve covers in-plane [-90 - arc, -90]; rotate to [b0, b1]
    return geo.axis_rotation(_ROT, b1 + 90.0) * ring


def keep_island(g=0.0):
    x, z = _idler_axis_xz()
    y0, y1 = DIA_FRONT_Y - 3.0, IDLER_BOSS_Y[1] + 1.0 + g
    boss = geo.cyl_y(y0, y1, 2 * (IDLER_BOSS_R + 1.1 + g), x, z)
    arm = bd.Box(30.0 + 2 * g, CAV_FRONT_Y + 2.0 + g - y0, 100.0 - 30.0,
                 align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    arm = geo.axis_rotation(_ROT, CUT_KEEP_ANGLE) * bd.Pos(0, y0, 30.0) * arm
    return boss + arm


KEEP_RING_R = 238.0         # flange ring left standing in the cut (the crankcase window is r < 238)
RIB_HALF_W = 5.0            # slim radial rib tying each retained half-boss to that ring


def cut_cylinders():
    """Cylinders whose tappets lie in the nose cutaway (1, 8, 9)."""
    return [k for k in range(1, S.N_CYL + 1)
            if any(removed(kin.pushrod_bottom0(k, v)) for v in kin.VALVES)]


def half_boss_keep(g=0.0):
    """Cylinder-1 keep volume: the twin boss (and the dome segment under its
    footprint) behind the planes through each tappet axis (y = -178 on the
    intake side t > 0, y = -152 on the exhaust side), so each bronze guide sits
    whole in a half-bore, its front half in the open."""
    pI = (BOSS_C, S.TAPPET_Y["I"])
    pE = (-BOSS_C, S.TAPPET_Y["E"])
    L = math.dist(pI, pE)
    ang = math.degrees(math.atan2(pE[1] - pI[1], pE[0] - pI[0]))
    mid = ((pI[0] + pE[0]) / 2, (pI[1] + pE[1]) / 2)
    pl = bd.Plane(origin=(0, 0, 172.0 - g), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    sk = bd.Pos(mid[0], mid[1]) * bd.Rot(0, 0, ang) * bd.SlotCenterToCenter(L, 2 * BOSS_R_TOP + 16.0 + 2 * g)
    prism = bd.extrude(pl * sk, amount=100.0)
    al = (bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN)
    ex = bd.Pos(0, S.TAPPET_Y["E"] - g, 150.0) * bd.Box(200.0, 80.0, 150.0, align=al)
    it = bd.Pos(50.0 - g, S.TAPPET_Y["I"] - g, 150.0) * bd.Box(100.0, 80.0, 150.0, align=al)
    return prism & (ex + it)


def rib_keep(g=0.0):
    """Cylinder-1 keep volume of the radial rib: a 10 mm slice of the casting on
    the cylinder axis (dome wall + fillet + flange) from the half-boss back to the
    flange ring. It keeps only metal that is there, so it reads as a spoke cut
    from the casting, between (never under) the two packing nuts."""
    return bd.Pos(0, -136.0 + SH - g, 172.0 - g) * bd.Box(2 * (RIB_HALF_W + g), 30.0, 100.0,
                                             align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))


def museum_cutter():
    """The nose cutaway sector (true arcs) minus what stays standing in it: the
    idler boss + its arm, the flange ring outside the crankcase window (r > 238),
    and for the cut cylinders the half-bosses carrying the tappet guides, each
    tied to that ring by one slim radial rib."""
    return _sector_raw() - _keep(0.0)


CUT_Y = (-900.0, CAM_REAR_Y + 2.0)   # the cut opens the cam section's rear wall too
CUT_R0 = geo.NOSE_CUT_R_MIN - 0.1


def _sector_raw():
    b0, b1 = geo.NOSE_CUT_SECTOR
    return _sector(b0, b1, CUT_R0, 450.0, *CUT_Y)


NECK_KEEP_R = 126.0                 # the neck (and its flare into the rear wall) is never cut
ARC_KEEP_R = (172.0, 212.0)         # arc of the dome's rear shoulder left standing in the cut:
ARC_KEEP_Y = -270.0                 # it carries the three half-bosses to the uncut case


def _keep(g):
    hb = half_boss_keep(g) + rib_keep(g)
    neck = _revolve((0.0, CAM_REAR_IN_Y - 4.0 - g),
                    [("L", (NECK_KEEP_R + g, CAM_REAR_IN_Y - 4.0 - g)), ("L", (NECK_KEEP_R + g, Y_REAR + 5.0)),
                     ("L", (0.0, Y_REAR + 5.0))])
    arc = _revolve((ARC_KEEP_R[0] - g, ARC_KEEP_Y - g),
                   [("L", (ARC_KEEP_R[1] + g, ARC_KEEP_Y - g)), ("L", (ARC_KEEP_R[1] + g, Y_REAR + 5.0)),
                    ("L", (ARC_KEEP_R[0] - g, Y_REAR + 5.0))])
    return keep_island(g) + [neck, arc] + [geo.on_cylinder(hb, k) for k in cut_cylinders()]


def section_band():
    """The geo.SKIN_T layer just inside the cutter against every cut face (the
    cutter minus its erosion; eroding 'sector minus keep' = eroded sector minus
    the keep grown by SKIN_T, each keep volume being grown parametrically)."""
    t = geo.SKIN_T
    b0, b1 = geo.NOSE_CUT_SECTOR
    core = _sector(b0, b1, CUT_R0 + t, 450.0, CUT_Y[0], CUT_Y[1] - t)
    big = bd.Box(2000.0, 2000.0, 2000.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for b, sgn in ((b0, 1.0), (b1, -1.0)):
        n = (-sgn * math.cos(math.radians(b)), 0.0, -sgn * math.sin(math.radians(b)))
        core = core & (geo.plane((n[0] * t, 0.0, n[2] * t), n).location * big)
    return museum_cutter() - (core - _keep(t))


NOSE_CUT = False    # the nose is closed


def removed(p) -> bool:
    return NOSE_CUT and geo.in_nose_cut(p)


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def _fast(shape, label, color=FA):
    return P.style(shape, label, color)


def _ring_points(r, n, phase, y):
    return [(i, 360.0 * i / n + phase, S.inplane(360.0 * i / n + phase, r, y)) for i in range(n)]


def _wire_between(p, q, sag_dir, sag=3.0, d=0.8):
    mid = tuple((a + b) / 2 + sag * s for a, b, s in zip(p, q, sag_dir))
    path = bd.Spline(bd.Vector(*p), bd.Vector(*mid), bd.Vector(*q))
    t0 = path % 0.0
    prof = bd.Plane(origin=path @ 0.0, z_dir=t0) * bd.Circle(d / 2.0)
    return bd.sweep(prof, path=path)


def hardware():
    out = []
    # joint studs + washers + nuts (case flange -> thrust-housing flange)
    stud = F.stud(8.0, (JOINT_Y - TH_FLANGE_FRONT_Y) + 1.6 + 6.5 + 1.8, 12.0)
    wash, nut = F.washer(8.0), F.hex_nut(8.0)
    for i, b, p in _ring_points(JOINT_STUD_R, 18, 10.0, JOINT_Y):
        if removed(p):
            continue
        rad = S.inplane(b)
        out.append(_fast(F.place(stud, p, (0, -1, 0), rad), f"nose:joint_stud_{i + 1}"))
        pw = (p[0], TH_FLANGE_FRONT_Y, p[2])
        out.append(_fast(F.place(wash, pw, (0, -1, 0), rad), f"nose:joint_washer_{i + 1}"))
        pn = (p[0], TH_FLANGE_FRONT_Y - 1.6, p[2])
        out.append(_fast(F.place(nut, pn, (0, -1, 0), rad), f"nose:joint_nut_{i + 1}"))
    # case joint (rear casting <- front casting): nine studs on the shoulder lugs
    lstud = F.stud(8.0, (SPLIT_Y - LUG_Y[1]) + 1.6 + 6.5 + 1.8, 7.0)
    for n, b in enumerate(LUG_ANGLES):
        rad = S.inplane(b)
        q = S.inplane(b, LUG_STUD_R, SPLIT_Y)
        out.append(_fast(F.place(lstud, q, (0, -1, 0), rad), f"nose:case_joint_stud_{n + 1}"))
        qw = S.inplane(b, LUG_STUD_R, LUG_Y[1])
        out.append(_fast(F.place(wash, qw, (0, -1, 0), rad), f"nose:case_joint_washer_{n + 1}"))
        qn = S.inplane(b, LUG_STUD_R, LUG_Y[1] - 1.6)
        out.append(_fast(F.place(nut, qn, (0, -1, 0), rad), f"nose:case_joint_nut_{n + 1}"))
    # front-cover bolts, wired in pairs
    yc = NOSE_FRONT_Y - COVER_T
    bolt = F.hex_flange_bolt(6.0, COVER_T + 8.0)
    heads, bolts = {}, {}
    for i, b, p in _ring_points(COVER_BOLT_R, 18, 10.0, yc):
        if removed(p):
            continue
        bolts[i] = F.place(bolt, p, (0, -1, 0), S.inplane(b))
        heads[i] = b
    for i in range(0, 18, 2):
        j = i + 1
        if i in heads and j in heads:
            yw = yc - 3.6
            pa = S.inplane(heads[i] + 1.9, COVER_BOLT_R - 1.0, yw)
            pb = S.inplane(heads[j] - 1.9, COVER_BOLT_R - 1.0, yw)
            mid_b = (heads[i] + heads[j]) / 2
            sag = S.inplane(mid_b, -1.0)          # toward the centre
            out.append(_fast(_wire_between(pa, pb, sag, 4.0), f"nose:cover_wire_{i // 2 + 1}", SW))
            # drill both heads' wire holes along the wire's own path
            drill = _wire_between(pa, pb, sag, 4.0, d=1.0)
            bolts[i], bolts[j] = bolts[i] - drill, bolts[j] - drill
    for i in sorted(bolts):
        out.append(_fast(bolts[i], f"nose:cover_bolt_{i + 1}"))
    # governor studs + nuts
    gstud = F.stud(6.0, 8.0 + 5.0 + 1.5, 10.0)
    gnut = F.hex_nut(6.0)
    for n, (ax, tg) in enumerate(GOV_STUDS):
        c = _gov_plane(GOV_R1).from_local_coords((ax, tg, 0.0))
        p = (c.X, c.Y, c.Z)
        nrm = S.inplane(GOV_B)
        out.append(_fast(F.place(gstud, p, nrm), f"nose:governor_stud_{n + 1}"))
        pn = tuple(a + 8.0 * b for a, b in zip(p, nrm))
        out.append(_fast(F.place(gnut, pn, nrm, (0, 1, 0)), f"nose:governor_nut_{n + 1}"))
    return out


# ---------------------------------------------------------------------------
# Governor (constant-speed prop governor, unbranded)
# ---------------------------------------------------------------------------
def governor():
    """Prop governor (unbranded): drafted base on four M6 studs, slim drafted
    body, clamp band, cap and dome; control shaft boss forward with its arm."""
    al = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    base = C.drafted_prism(bd.RectangleRounded(GOV_PAD[0] - 4.0, GOV_PAD[1] - 4.0, 8.0), 8.0, 4.0)
    body = bd.Pos(0, 0, 7.0) * bd.Cone(16.0, 14.5, 40.0, align=al)
    band = bd.Pos(0, 0, 45.0) * bd.Cylinder(18.0, 5.0, align=al)
    cap = bd.Pos(0, 0, 49.0) * bd.Cone(16.0, 12.5, 11.0, align=al)
    dome = (bd.Pos(0, 0, 58.0) * bd.Sphere(12.8)) & (bd.Pos(0, 0, 59.0) * bd.Box(40, 40, 30, align=al))
    shaft_boss = bd.Pos(0, 0, 30.0) * bd.Rot(0, 90, 0) * bd.Cylinder(7.0, 25.0, align=al)
    body_all = base + [body, band, cap, dome, shaft_boss]
    body_all, _ = C.fillet_all(body_all, 1.0, min_r=0.4)
    body_all = body_all - [bd.Pos(sx, sy, -1.0) * bd.Cylinder(3.3, 12.0, align=al) for sx, sy in GOV_STUDS]
    arm = bd.extrude(bd.Plane.YZ * bd.SlotCenterToCenter(26.0, 11.0, rotation=90), amount=4.0)
    arm = bd.Pos(25.0, 0, 30.0 + 13.0) * arm
    hub = bd.Pos(25.0, 0, 30.0) * bd.Rot(0, 90, 0) * bd.Cylinder(8.0, 6.0, align=al)
    return body_all, arm + hub


# ---------------------------------------------------------------------------
def build() -> list:
    parts = []
    # CLOSED nose (coordinator, gauntlet round 2): no cutaway; the crankcase window
    # is seen through the gap round the neck. museum_cutter()/section_band() are kept
    # but unused.
    cutter = band = None

    # ---- case: revolve + bosses + pad, root fillets, bores, cut
    case = _case_revolve()
    twin = twin_boss()
    keep_k = list(range(1, S.N_CYL + 1))
    bosses = [geo.on_cylinder(twin, k) for k in keep_k]
    pad = _gov_locate(governor_pad_full() & bd.Box(200, 200, (GOV_R1 - GOV_R0) - SKIN,
                                                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    rev = case
    case = C.fuse_all([case] + bosses + [idler_boss(), pad] + bottom_bosses())
    case = _root_fillets(case, rev)
    ring = rear_ring()
    spokes = [spoke(b) for b in SPOKE_ANGLES]
    case = C.fuse_all([case, ring] + spokes + [joint_lug(b) for b in LUG_ANGLES])
    case = _spoke_fillets(case, [rev, ring])
    # lug root fillets are left out: on the full casting OCC ran >25 min without converging

    tools = []
    for k in keep_k:
        for v in kin.VALVES:
            tools.append(geo.on_cylinder(_guide_bore_tool(v), k))
    x, z = _idler_axis_xz()
    tools.append(geo.cyl_y(S.CAM_RING_Y[0] - 0.5, IDLER_BOSS_Y[1] + 1.0, 2 * IDLER_BORE_R, x, z))   # blind to the shaft's front end
    # the idler nut ends 2.8 mm short of the rear wall's inner face: a spot-faced pocket clears it
    tools.append(geo.cyl_y(CAM_REAR_IN_Y - 1.0, CAM_REAR_IN_Y + 3.0, 34.0, x, z))
    stud_holes = [geo.cyl_y(Y_REAR - 20.0, Y_REAR + 1.0, 10.5, p[0], p[2])
                  for i, b, p in _ring_points(STUD_R, STUD_N, STUD_PHASE, Y_REAR)]
    tools += stud_holes
    for sx, sy in GOV_STUDS:
        tools.append(_gov_locate(bd.Pos(sx, sy, GOV_R1 - GOV_R0 - 16.0) * bd.Cylinder(
            3.4, 20.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))))
    # spot-face each twin boss where its faces run out into the dome's rear shoulder
    # (0.02 below the boss faces: never coplanar with them); cut in a second pass
    prism = _boss_prism()
    face_tool = prism - _below_both(prism, SKIN + 0.02)
    face_tools = [geo.on_cylinder(face_tool, k) for k in keep_k]
    # holes for the hardware that screws into the case
    xz = lambda q: (q[0], q[2])
    # joint studs: ONE revolved tool per lug (tapped in the rear lug, clear through the
    # front lug, then a r 9.5 spot-face pocket for washer + nut where the dome's
    # shoulder rises under them; 9.5 < the lug's half-width 10: never tangent)
    lug_tool = geo.revolve_y([(0.0, SPLIT_Y + 8.0), (3.8, SPLIT_Y + 8.0), (3.8, SPLIT_Y), (4.3, SPLIT_Y),
                              (4.3, LUG_Y[1]), (9.5, LUG_Y[1]), (9.5, LUG_Y[1] - 22.0), (0.0, LUG_Y[1] - 22.0)])
    for b in LUG_ANGLES:
        q = S.inplane(b, LUG_STUD_R, 0.0)
        tools.append(bd.Pos(q[0], 0.0, q[2]) * lug_tool)
    tools += [geo.cyl_y(JOINT_Y - 1.0, JOINT_Y + 13.0, 7.6, *xz(p))
              for i, b, p in _ring_points(JOINT_STUD_R, 18, 10.0, JOINT_Y)]
    for spec_, depth in ((DRAIN, 12.0), (BREATHER, 10.0)):
        bb_, yb, _, rf = spec_
        tools.append(geo.cyl_along(S.inplane(bb_, rf + 1.0, yb), S.inplane(bb_, rf - depth - 1.0, yb), 12.2))
    case = C.cut_all(case, tools)
    # (no spot-face cut into the casting: where a boss face runs out into the dome's
    # shoulder the cast shoulder stays, and the bright face skin stops at it -- the
    # spot-face cut left near-tangent faces against the root fillets)
    big = 2000.0
    al = (bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER)
    rear = case & (bd.Pos(0, SPLIT_Y, 0) * bd.Box(big, big, big, align=al))
    gasket = case & (bd.Pos(0, SPLIT_Y - GASKET_T, 0) * bd.Box(big, GASKET_T, big, align=al))
    front = case & (bd.Pos(0, SPLIT_Y - GASKET_T - big, 0) * bd.Box(big, big, big, align=al))
    parts += _sectioned(rear, "case_rear", CS, cutter, band)
    parts += _sectioned(gasket, "joint_gasket", P.GASKET, cutter, band, face=False)
    parts += _sectioned(front, "case_front", CS, cutter, band)

    # ---- machined skins
    fs = C.cut_all(_flange_skin(), stud_holes)
    parts += _sectioned(fs, "flange_face", MA, cutter, band)
    skin = boss_skin()
    for k in keep_k:
        sk = geo.on_cylinder(skin, k) - case
        sols = [x for x in sk.solids() if x.volume > 1.0]
        sk = sols[0] if len(sols) == 1 else bd.Compound(children=sols)
        if k in cut_cylinders():
            parts += _sectioned(sk, f"boss_face_{k}", MA, cutter, band)
        else:
            parts.append(P.style(sk, f"nose:boss_face_{k}", MA))
    gp = _gov_locate(governor_pad_full() & bd.Pos(0, 0, GOV_R1 - GOV_R0 - SKIN) * bd.Box(
        200, 200, SKIN, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    gp = gp - [_gov_locate(bd.Pos(sx, sy, GOV_R1 - GOV_R0 - 5) * bd.Cylinder(
        3.4, 10.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))) for sx, sy in GOV_STUDS]
    parts.append(P.style(gp, "nose:governor_pad", MA))

    # ---- thrust housing, liner, cover
    th = thrust_housing()
    xz = lambda q: (q[0], q[2])
    th = C.cut_all(th, [geo.cyl_y(WEB_FRONT_Y - 1.0, JOINT_Y + 1.0, 8.4, *xz(p))
                        for i, b, p in _ring_points(SUN_BOLT_R, SUN_BOLT_N, SUN_BOLT_PHASE, JOINT_Y)]
                   + [geo.cyl_y(TH_FLANGE_FRONT_Y - 1.0, JOINT_Y + 1.0, 8.6, *xz(p))
                      for i, b, p in _ring_points(JOINT_STUD_R, 18, 10.0, JOINT_Y)]
                   + [geo.cyl_y(NOSE_FRONT_Y - 1.0, NOSE_FRONT_Y + 9.0, 5.6, *xz(p))
                      for i, b, p in _ring_points(COVER_BOLT_R, 18, 10.0, NOSE_FRONT_Y)])
    parts += _sectioned(th, "thrust_housing", CS, cutter, band)
    parts += _sectioned(thrust_liner(), "thrust_liner", ST, cutter, band)
    cov = C.cut_all(front_cover(), [geo.cyl_y(NOSE_FRONT_Y - COVER_T - 1.0, NOSE_FRONT_Y + 1.0, 6.6, *xz(p))
                                    for i, b, p in _ring_points(COVER_BOLT_R, 18, 10.0, NOSE_FRONT_Y)])
    parts += _sectioned(cov, "front_cover", CS, cutter, band)

    # ---- governor
    gbody, garm = governor()
    parts.append(P.style(_gov_locate(gbody, GOV_R1), "nose:governor_body", CS))
    parts.append(P.style(_gov_locate(garm, GOV_R1), "nose:governor_arm", MA))

    parts.append(P.style(drain_plug(), "nose:drain_plug", FA))
    parts.append(P.style(breather(), "nose:breather", ST))
    parts += hardware()
    # the crankcase omits its nose-flange nuts inside the cutaway (geo.in_nose_cut);
    # the flange collar stands there, so the nose supplies those nuts
    fnut = F.flange_nut(10.0)
    for i, b, p in _ring_points(STUD_R, STUD_N, STUD_PHASE, FLANGE_FACE_Y):
        if geo.in_nose_cut(p):
            parts.append(_fast(F.place(fnut, p, (0, -1, 0), S.inplane(b)), f"nose:flange_nut_{i + 1}"))
    return parts


def _sectioned(shape, name, color, cutter, band, face=True):
    """[kept part, machined cut-face skin] for one body cut by the nose cutaway."""
    if cutter is None:
        return [P.style(shape, f"nose:{name}", color)]
    out = [P.style(geo.cut(shape, cutter), f"nose:{name}", color)]
    if not face:
        return out
    skin = shape & band
    sols = [x for x in skin.solids() if x.volume > 1e-3]
    for i, sk in enumerate(sols):
        tag = "" if len(sols) == 1 else f"_{i + 1}"
        out.append(P.style(sk, f"nose:cut_face_{name}{tag}", P.MACHINED_ALU))   # bright sawn/machined cut
    return out


def _lug_fillets(case, rev):
    """Root fillets where the nine joint lugs rise out of the dome's shoulder."""
    sh = bd.Shell(rev.faces())
    cand = []
    for e in case.edges():
        c = e.bounding_box().center()
        r = math.hypot(c.X, c.Z)
        if not (LUG_Y[1] - 1 < c.Y < LUG_Y[0] + 1 and 175.0 < r < LUG_R[1] + 1) or e.length < 2.0:
            continue
        bc = math.degrees(math.atan2(-c.X, c.Z))
        if min(abs(((bc - lb) + 180) % 360 - 180) for lb in LUG_ANGLES) * math.pi / 180 * r > LUG_W / 2 + 3:
            continue
        if e.geom_type == bd.GeomType.CIRCLE and math.hypot(e.arc_center.X, e.arc_center.Z) < 1e-3:
            continue
        if all(sh.distance_to(e @ t) < 1e-3 for t in (0.15, 0.5, 0.85)):
            cand.append(e)
    bop = C.BOP_CHECK
    C.BOP_CHECK = False
    try:
        res, got = C.safe_fillet(case, cand, 3.0, min_r=1.0)
    finally:
        C.BOP_CHECK = bop
    print(f"[nose] lug roots: {len(cand)} edges -> r {got}")
    return res if got is not None else case


def _spoke_fillets(case, srcs):
    """Root fillets where the spokes meet the neck and the rear ring."""
    shells = [bd.Shell(x.faces()) for x in srcs]
    cand = []
    for e in case.edges():
        c = e.bounding_box().center()
        if c.Y < Y_REAR - SPOKE_T - 2.0 or c.Y > Y_REAR - 1.0 or e.length < 4.0:
            continue
        r = math.hypot(c.X, c.Z)
        if not (95.0 < r < 245.0):
            continue
        bb = e.bounding_box()
        if bb.size.Z < 1e-6 and abs(bb.min.Z) < 1e-6 and bb.min.X > 0:
            continue                               # revolve seam
        bc = math.degrees(math.atan2(-c.X, c.Z))
        if min(abs(r * math.sin(math.radians(bc - sb))) for sb in SPOKE_ANGLES
               if math.cos(math.radians(bc - sb)) > 0) > SPOKE_W / 2 + 8.0:
            continue                               # not at a spoke
        if any(all(sh.distance_to(e @ t) < 1e-3 for t in (0.15, 0.5, 0.85)) for sh in shells) and not (
                e.geom_type == bd.GeomType.CIRCLE and math.hypot(e.arc_center.X, e.arc_center.Z) < 1e-3):
            cand.append(e)
    bop = C.BOP_CHECK
    C.BOP_CHECK = False
    try:
        res, got = C.safe_fillet(case, cand, 5.0, min_r=1.5)
    finally:
        C.BOP_CHECK = bop
    print(f"[nose] spoke roots: {len(cand)} edges -> r {got}")
    return res if got is not None else case


def _root_fillets(case, shell_src):
    """Fillet every edge where a fused boss/pad meets the revolved casting
    (edges lying ON the revolve's surface that the revolve itself did not have)."""
    shellf = bd.Shell(shell_src.faces())

    def root(e):
        bb = e.bounding_box()
        if e.geom_type == bd.GeomType.CIRCLE:
            c = e.arc_center
            if math.hypot(c.X, c.Z) < 1e-3:
                return False                       # revolve circles about Y
        if bb.size.Z < 1e-6 and abs(bb.min.Z) < 1e-6 and bb.min.X > 0:
            return False                           # revolve seam
        return all(shellf.distance_to(e @ t) < 1e-3 for t in (0.15, 0.5, 0.85))

    ix, iz = _idler_axis_xz()

    def near_idler(e):
        c = e.bounding_box().center()
        return math.hypot(c.X - ix, c.Z - iz) < 25.0 and c.Y > -205.0 + SH

    def near_bottom(e, which=None):
        c = e.bounding_box().center()
        for sp in ((DRAIN, BREATHER) if which is None else (which,)):
            q = S.inplane(sp[0], sp[3] - 8.0, sp[1])
            if math.dist((c.X, c.Y, c.Z), q) < 24.0:
                return True
        return False

    bop = C.BOP_CHECK
    C.BOP_CHECK = False
    try:
        cand = [e for e in case.edges() if root(e) and not near_idler(e) and not near_bottom(e)]
        res, got = C.safe_fillet(case, cand, 4.0, min_r=1.5)
        print(f"[nose] root fillet: {len(cand)} edges -> r {got}")
        case = res if got is not None else case
        for spec_ in (DRAIN, BREATHER):
            cand = [e for e in case.edges() if root(e) and near_bottom(e, spec_)]
            res, got = C.safe_fillet(case, cand, 3.0, min_r=1.0)
            print(f"[nose] bottom boss root: {len(cand)} edges -> r {got}")
            case = res if got is not None else case
        cand = [e for e in case.edges() if root(e) and near_idler(e)]
        res, got = C.safe_fillet(case, cand, 2.5, min_r=1.0)
        print(f"[nose] idler boss root: {len(cand)} edges -> r {got}")
        case = res if got is not None else case
    finally:
        C.BOP_CHECK = bop
    return case
