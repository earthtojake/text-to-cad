"""W16 induction — intercoolers, plenums, throttle bodies, charge pipes, fuel rails.

AIRFLOW (the path this module builds):
    compressor outlet (Ø55 stub, |y| 435, z 80)
      -> stepped hose + two T-bolt clamps
      -> Ø60 mandrel-bent charge pipe: the FRONT turbo's turns aft off its stub
         and runs the length of the engine LOW along the cover flank (|y| 435,
         z 208), outboard of the cam cover and clear over the exhaust log
      -> Y-merge onto the REAR turbo's short riser at x -222, behind the
         museum section, where ONE Ø68 trunk climbs
      -> V-band joint (machined flange, cast inlet neck, banded clamp)
      -> REAR intercooler end tank, outboard face
      -> air-to-liquid core, flowing FORWARD along X
      -> FRONT end tank -> Ø82 outlet straight down through its floor
      -> DOWNDRAUGHT throttle body (Ø82 butterfly) standing on the plenum's
         front deck -> composite plenum log -> 8 CAST runner throats per bank
      -> the head's intake pads and inner ports.

MATERIALS.  The manifold is deliberately three materials, split on real joints:
CAST throats and intercooler lid, MACHINED flange plate / sealing land / window
rim / V-band flanges, COMPOSITE plenum log and the lid's spine panel.

WATER (the second circuit, and the reason the top face is not symmetric).  An
air-to-liquid core has a coolant side, and it enters one end and leaves the
other: cold in LOW at the REAR of each core, hot out HIGH at the FRONT, both on
the core frame's own outboard wall, each a cast boss + machined stub + red -AN
nut.  The circuit has ONE pressure cap, at its high point, so bank 2 alone
carries the cast degas tower (its cap clears the lid crest by 13 mm and stands
18 mm outboard of the lid edge); bank 1 alone carries the coolant temperature
sender on its cold inlet.  The two cast lids carry DIFFERENT casting numbers,
because a left and a right lid are two part numbers and never one part
mirrored.  On bank 1 the front (hot) port sits inside the museum section and is
cut away with it — that is the section working, not the banks disagreeing.

RADIUS FAMILIES.  Cast corners turn on LID_R (20 mm, a radius a pattern-maker
can pull); machined pockets, spotfaces and window rims turn on LID_MACH_R
(4-6 mm, an end-mill radius); the end tanks keep their own 16 mm cast section.
The lid's skirt is relieved 1.6 mm just above the machined land, so the split
line throws a shadow instead of the two parts sharing one flush wall.

The throttle is a downdraught because of the timing case: nothing may occupy
x > 306 below z 400, and a Ø96 throttle barrel laid along the plenum's front
face at x 282 sweeps out to x 330 the moment its axis is not parallel to X.
So the plenum's roof steps DOWN over its last 75 mm (a lofted transition at
x 186..206) to a flat deck at z 362, and the throttle stands on that deck
under the front end tank, its whole envelope inside x 206..302.

Geometry is authored for BANK 1 (+Y) and mirrored about the XZ plane for bank 2,
which is what guarantees the top-down view reads as designed symmetry.  Bank-1
STATICS (plenum, runners, flange, fuel rail, injectors, intercooler) go through
`geo.sectioned`, and so are the bank-1 charge pipes (they cross the void); throttle bodies stay intact.

Bank coordinates: m = toward the engine centre in the deck plane, h = up the
bank centreline.  y = 0.7071 (h - m), z = 0.7071 (h + m) for bank 1.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import fasteners as F, geo, palette as P, spec as S
from lib import castings as C
from lib.castings import fuse_all, cut_all
from lib.geo import sound as is_sound

# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------

PX0, PX1 = S.PLENUM_X                       # -280, 280
WALL = 4.5                                  # plenum shell wall
END_CAP = 6.0

# Plenum cross-section, bank 1, engine (y, z), CCW.  Bounded by |y| >= 20,
# z >= 292, z <= 400 and by the runner corridor: the outboard wall stands
# ~45 mm clear (perpendicular) of the head's inner face plane (z = y + 183.85).
PLENUM_PTS = [
    (40.0, 312.0), (75.0, 308.0), (100.0, 330.0), (110.0, 360.0),
    (105.0, 388.0), (85.0, 400.0), (40.0, 398.0), (20.0, 380.0), (20.0, 330.0),
]
PLENUM_R = 9.0                              # moulded corner radius
# The same section with its roof taken off at z 362: the plenum's front deck,
# the flat the downdraught throttle stands on.  SAME point count as PLENUM_PTS
# so the transition between them lofts without twisting.
# It also has to be WIDER than the log: a Ø82 mouth plus a 4.5 wall needs 91 mm
# of clear section, and the log's roof only gives 66.  Flaring out to |y| 124 as
# it drops stays inboard of the head face (m 168 at the corner, face at 130) and
# 7 mm under the fuel rail.
PLENUM_LOW_PTS = [
    (40.0, 312.0), (75.0, 308.0), (104.0, 322.0), (122.0, 340.0),
    (124.0, 362.0), (80.0, 362.0), (40.0, 362.0), (20.0, 362.0), (20.0, 330.0),
]
LOFT_X = (186.0, 206.0)                     # roof step: full section -> front deck
DECK_Z = 362.0
RIB_X = [-240.0, -180.0, -120.0, -60.0, 0.0, 60.0, 120.0]
RIB_T = 7.0                                 # rib width along X
RIB_OUT = 2.2                               # rib proud of the shell

THROTTLE_XY = (254.0, 70.0)                 # throttle bore axis (x, |y|), vertical
PLENUM_MOUTH_D = 82.0                       # S.THROTTLE_D, straight through the deck
PAD = (100.0, 100.0, 12.0)                  # throttle pad on the deck: x, y, thickness
PAD_R = 10.0                                # pad plan radius: DELIBERATELY tighter than
                                            # the old 18, so the pad's corners stand
                                            # outside the throttle flange's instead of
                                            # hiding behind them
PAD_TOP = DECK_Z + 4.0                      # 366, the throttle flange's seating plane
GASKET_T = 1.5                              # the joint is a real sandwich: cast deck
PAD_FACE = PAD_TOP - GASKET_T               # face (364.5), gasket, machined flange
TB_GASKET = (104.0, 102.0, 12.0)            # gasket plan: x, y, corner r — 2 mm PROUD
                                            # of the flange all round, which is the only
                                            # way a bolted joint reads from straight up
# Two cast gussets under the pad's forward overhang.  The pad cantilevers 24 mm
# past the plenum's front end cap (x 280) to reach the throttle at x 254; before
# these it hung on nothing, which is exactly what "resolves into nowhere" means.
GUSSET_Y = (45.0, 95.0)                     # |y| centres
GUSSET_T = 9.0                              # thickness across y
GUSSET_X = (280.0, 299.0)                   # x span, well inside the x <= 306 limit
GUSSET_Z = 336.0                            # bottom of the web, on the front face
THROTTLE_BOLT_R = 58.0                      # outside the Ø96 barrel, so the bolt
                                            # heads stand clear of it, not inside it

# Head-face interfaces.  heads.py machines two landings on the inner face:
# the per-cylinder intake pad (h 276..312, 66 wide, proud to m = 132, with the
# two Ø21 port exits at h 294, x = cylinder +/- 19) and the plenum rail
# (h 328..346, FLUSH with the face at m = 130) with M6 taps at h = 337 on a
# 55 mm pitch about the head's mid-station x = 3.
PLATE_M = (130.0, 138.0)                    # seats DIRECTLY on the head face (m 130)
PLATE_H = (328.0, 346.0)
PLATE_X = (-284.0, 290.0)
PLATE_BOLT_H = 337.0
PLATE_BOLT_PITCH = 55.0
PLATE_BOLT_X0 = 3.0                         # head mid-station: the taps' datum
BOSS_FACE_M = S.INTAKE_EXIT_M + 2.0         # 132, the intake pad's proud face
PORT_H = S.INTAKE_EXIT_H                    # 294: the head's intake ports are voids
                                            # at h 286..302, x = cylinder +/- 19
BOSS_W, BOSS_HH = 64.0, 30.0                # stadium on the intake pad (x, h)
RUNNER_D = 34.0
RUNNER_BORE = 26.0
RUNNER_M_IN = 192.0                         # runner start, inside the plenum
RUNNER_M_LOFT = 152.0                       # circle -> stadium transition
# The manifold is TWO materials and parts on one plane: outboard of m = SPLIT_M
# the CAST throats that flare onto the head's intake pads, inboard of it the
# COMPOSITE log.  The plane cannot go higher than 142: the Ø32 injector boss
# stands almost square to m, so its barrel reaches DOWN to m 145.7 whatever its
# length, and a split above that shaves a lens off every one of the sixteen
# bosses into the cast group (measured: 8 spurious 20 x 15 x 11 mm solids per
# bank).  At 142 the boss, the shell (lowest point m 154.15, the front deck's
# outboard edge) and the ribs all stay whole on the composite side, and the
# cast part is the flared throat mouth itself.
SPLIT_M = 142.0


def bp(bank: int, x: float, m: float, h: float):
    """Point from bank coordinates (the only frame this module authors in)."""
    return S.bank_point(bank, x, m, h)


def yz(bank: int, pts):
    """Mirror a bank-1 (y, z) point list onto `bank`."""
    return [(y, z) for y, z in pts] if bank == 1 else [(-y, z) for y, z in pts]


def m_dir(bank: int):
    return S.bank_m(bank)


def in_dir(bank: int):
    """Runner flow direction: from the plenum toward the head's inner face."""
    v = S.bank_m(bank)
    return (-v[0], -v[1], -v[2])


# ---------------------------------------------------------------------------
# 2D helpers
# ---------------------------------------------------------------------------

def _ccw(pts):
    a = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
            for i in range(len(pts)))
    return list(pts) if a > 0 else list(reversed(pts))


def offset_poly(pts, t: float):
    """Mitre-offset a CLOSED polygon by `t` (positive = outward)."""
    pts = _ccw(pts)
    n = len(pts)
    segs = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = dy / L * t, -dx / L * t          # outward for CCW
        segs.append(((a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny)))
    out = []
    for i in range(n):
        (p0, p1_), (q0, q1_) = segs[i - 1], segs[i]
        d1 = (p1_[0] - p0[0], p1_[1] - p0[1])
        d2 = (q1_[0] - q0[0], q1_[1] - q0[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(q0)
            continue
        s = ((q0[0] - p0[0]) * d2[1] - (q0[1] - p0[1]) * d2[0]) / den
        out.append((p0[0] + s * d1[0], p0[1] + s * d1[1]))
    return out


def _fillet2d(face, r: float):
    for rr in (r, r * 0.6, r * 0.35):
        try:
            return bd.fillet(face.vertices(), radius=rr)
        except Exception:
            continue
    return face


def pface(pts, x: float, r: float = 0.0):
    """A closed (y, z) polygon as a face on the station-x plane, corners rounded."""
    face = bd.make_face(bd.Polyline(*[(y, z) for y, z in _ccw(pts)], close=True).edges())
    if r > 0:
        face = _fillet2d(face, r)
    return geo.yz_plane(x) * face


def prism(pts, x0: float, x1: float, r: float = 0.0):
    """Extrude a closed (y, z) polygon between stations x0 < x1, corners rounded."""
    return bd.extrude(pface(pts, x0, r), amount=x1 - x0)


def stepped(hi, lo, r: float, x0: float, x1: float):
    """Full section from x0 to LOFT_X[0], a lofted roof step, then `lo` to x1."""
    return fuse_all([
        bd.extrude(pface(hi, x0, r), amount=LOFT_X[0] - x0),
        bd.loft([pface(hi, LOFT_X[0], r), pface(lo, LOFT_X[1], r)]),
        bd.extrude(pface(lo, LOFT_X[1], r), amount=x1 - LOFT_X[1]),
    ])


# ---------------------------------------------------------------------------
# 1. Plenums — a composite log per bank in the valley, split at m = SPLIT_M
#    from the eight CAST runner throats that land on the head's intake pads
# ---------------------------------------------------------------------------

def _runner_solids(bank: int, x: float):
    """(outer, bore) for one cylinder's runner: Ø34 tube -> stadium boss."""
    d = in_dir(bank)
    a = bp(bank, x, RUNNER_M_IN, PORT_H)
    b = bp(bank, x, RUNNER_M_LOFT, PORT_H)
    face = bp(bank, x, BOSS_FACE_M, PORT_H)
    tube = geo.cyl_along(a, b, RUNNER_D)
    boss = bd.loft([geo.plane(b, d, (1.0, 0.0, 0.0)) * bd.Circle(RUNNER_D / 2.0),
                    geo.plane(face, d, (1.0, 0.0, 0.0))
                    * bd.RectangleRounded(BOSS_W, BOSS_HH, BOSS_HH / 2.0 - 0.5)])
    bores = [geo.cyl_along(bp(bank, x, 202.0, PORT_H), bp(bank, x, 138.0, PORT_H),
                           RUNNER_BORE)]
    for s in (-1.0, 1.0):
        xx = x + s * S.VALVE_X_HALF
        bores.append(geo.cyl_along(bp(bank, xx, 146.0, PORT_H),
                                   bp(bank, xx, 126.0, PORT_H),
                                   S.INTAKE_HEAD_D - 10.0))
    return fuse_all([tube, boss]), fuse_all(bores)


def throttle_axis(bank: int):
    """(x, y) of the vertical throttle bore for `bank`."""
    return THROTTLE_XY[0], _sy(bank) * THROTTLE_XY[1]


def build_plenum(bank: int, sectioned: bool = True):
    pts = yz(bank, PLENUM_PTS)
    low = yz(bank, PLENUM_LOW_PTS)
    shell = stepped(pts, low, PLENUM_R, PX0, PX1)
    cavity = stepped(offset_poly(pts, -WALL), offset_poly(low, -WALL),
                     max(PLENUM_R - WALL, 3.0), PX0 + END_CAP, PX1 - END_CAP)
    ribs = [prism(offset_poly(pts, RIB_OUT), x - RIB_T / 2.0, x + RIB_T / 2.0,
                  PLENUM_R + RIB_OUT) for x in RIB_X]
    tx, ty = throttle_axis(bank)
    pad = bd.extrude(bd.Plane.XY.offset(PAD_FACE - PAD[2])
                     * (bd.Pos(tx, ty) * bd.RectangleRounded(PAD[0], PAD[1], PAD_R)),
                     amount=PAD[2])
    # webs under the pad's forward overhang, back onto the plenum's front face
    gussets = []
    prof = [(GUSSET_X[0], GUSSET_Z), (GUSSET_X[1], PAD_FACE - PAD[2]),
            (GUSSET_X[0], PAD_FACE - PAD[2])]
    web = bd.extrude(bd.Plane.XZ * bd.make_face(bd.Polyline(*prof, close=True).edges()),
                     amount=GUSSET_T / 2.0, both=True)
    for gy in GUSSET_Y:
        gussets.append(web.moved(bd.Location((0.0, _sy(bank) * gy, 0.0))))
    adds, cuts = [shell, pad] + ribs + gussets, [cavity]
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        o, b = _runner_solids(bank, c.x)
        boss, bore = injector_boss_bore(bank, c.x)
        adds += [o, boss]
        cuts += [b, bore]
    # throttle mouth straight down through the deck, plus its 4 tapped holes
    cuts.append(geo.cyl_along((tx, ty, PAD_TOP + 4.0), (tx, ty, DECK_Z - 40.0),
                              PLENUM_MOUTH_D))
    for p in throttle_bolt_points(bank):
        cuts.append(geo.cyl_along((p[0], p[1], PAD_TOP + 4.0),
                                  (p[0], p[1], PAD_TOP - 22.0), 8.2))
    body = cut_all(fuse_all(adds), cuts)

    # One planar parting at m = SPLIT_M splits the finished manifold into the
    # composite log and eight CAST runner throats, so each runner is a part in
    # its own right, in its own material, visibly landing on the head's intake
    # pad instead of being one black mass with the plenum.
    proto = bd.Box(2400.0, 2400.0, 2400.0,
                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    seat = bp(bank, 0.0, SPLIT_M, 0.0)
    inboard = S.bank_m(bank)
    log_side = geo.locate(proto, seat, inboard)                      # m >= SPLIT_M
    throat_side = geo.locate(proto, seat, tuple(-v for v in inboard))  # m <= SPLIT_M

    out = []
    log = geo.sectioned(cut_all(body, [throat_side]), bank, sectioned)
    if log.solids():
        out.append(P.style(log, f"intake_plenum:{bank}", P.CARBON))
    throats = geo.sectioned(cut_all(body, [log_side]), bank, sectioned)
    cyls = [c for c in S.CYLINDERS if c.bank == bank]
    used = set()
    for solid in sorted(throats.solids(), key=lambda t: _bx(t)[0]):
        b = _bx(solid)
        cx = (b[0] + b[3]) / 2.0
        c = min(cyls, key=lambda c: abs(c.x - cx))
        tag, k = str(c.number), 2
        while tag in used:                  # never let a stray split fragment
            tag, k = f"{c.number}_{k}", k + 1   # collide with a runner's label
        used.add(tag)
        out.append(P.style(solid, f"intake_runner:{tag}", P.CAST))
    return out


def _plate_pts(bank: int):
    m0, m1 = PLATE_M
    h0, h1 = PLATE_H
    return [bp(bank, 0.0, m, h)[1:]
            for m, h in ((m0, h0), (m1, h0), (m1, h1), (m0, h1))]


def plate_bolt_xs():
    return [PLATE_BOLT_X0 + PLATE_BOLT_PITCH * (k - 5) for k in range(11)]


def build_flange_plate(bank: int, sectioned: bool = True, cap=None):
    plate = prism(_plate_pts(bank), *PLATE_X, r=2.0)
    cuts = []
    for x in plate_bolt_xs():
        cuts.append(geo.cyl_along(bp(bank, x, PLATE_M[0] - 2.0, PLATE_BOLT_H),
                                  bp(bank, x, PLATE_M[1] + 2.0, PLATE_BOLT_H), 6.6))
    plate = geo.sectioned(cut_all(plate, cuts), bank, sectioned)
    out = []
    if plate.solids():
        out.append(P.style(plate, f"plenum_flange:{bank}", P.MACHINED))
    # 8 mm shank = exactly the plate thickness: the bolt fills its clearance
    # hole and stops at the head face instead of fouling the head's M6 tap.
    cap = cap if cap is not None else F.socket_cap_bolt(6.0, 8.0)
    for i, x in enumerate(plate_bolt_xs()):
        seat = bp(bank, x, PLATE_M[1], PLATE_BOLT_H)
        if geo.in_section_void(seat, bank, sectioned):
            continue
        b = F.place(cap, seat, S.bank_m(bank), (1.0, 0.0, 0.0))
        out.append(P.style(b, f"plenum_flange_bolt:{bank}_{i + 1}", P.TITANIUM))
    return out
# ---------------------------------------------------------------------------
# 2. Throttle bodies (hardware — never sectioned)
#
# AIRFLOW: front end tank -> Ø82 hole in its floor -> DOWNDRAUGHT throttle ->
# plenum.  A compact drive-by-wire body: 42 mm between flange faces, butterfly
# on a Ø10 shaft across the bore, motor/gear pod cast onto the outboard side.
# Vertical is the only attitude that keeps a Ø96 barrel inside x <= 306.
# ---------------------------------------------------------------------------

TB_OD = 96.0
TB_SQ = 96.0                          # lower flange, square on the plenum pad — 4 mm
TB_SQ_R = 10.0                        # UNDER the pad (100) and 8 under the gasket
                                      # (104), so from straight up the joint reads as
                                      # three stacked plan outlines, not one slab
TB_FLANGE_Z = (PAD_TOP, PAD_TOP + 9.0)        # 366 .. 375, on the plenum's pad
TB_BARREL_Z = (PAD_TOP + 9.0, PAD_TOP + 27.0)  # 375 .. 393
TB_TOP_Z = (PAD_TOP + 27.0, PAD_TOP + 38.0)    # 393 .. 404, up to the tank floor
TB_TOP = (92.0, 100.0, 20.0)          # top flange: x, y, corner r — NOT round:
                                      # its bolts must clear the Ø96 barrel (r 48)
                                      # and x <= 306 caps a round flange at Ø104
TB_TOP_BOLT = (40.0, 43.0)            # bolt offsets from the axis, |x| and |y|
TB_SPIGOT = (404.0, 409.0, 86.0)      # (z0, z1, od) into the tank floor's Ø88 bore
TB_SPIGOT_CLEAR = 88.0
TB_SHAFT_D = 10.0
TB_BUTTERFLY_Z = 384.0
# Motor/gear pod: it has to thread between the plenum's throttle pad below
# (|y| <= 114, top z 366) and the fuel rail outboard (nearest corner |y| 131).
POD_Y = 116.0                         # motor/gear pod centre, |y|
POD = (44.0, 24.0, 28.0)              # x, y, z
POD_Z = 390.0                         # above the injector bosses (they top out at 374)


def throttle_bolt_points(bank: int):
    """The 4 bolts holding the throttle down to the plenum's deck pad."""
    tx, ty = throttle_axis(bank)
    r = THROTTLE_BOLT_R / math.sqrt(2.0)
    return [(tx + sx * r, ty + sy * r, TB_FLANGE_Z[1])
            for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]


def throttle_top_bolt_points(bank: int):
    """The 4 bolts holding the throttle up to the front end tank's floor."""
    tx, ty = throttle_axis(bank)
    return [(tx + sx * TB_TOP_BOLT[0], ty + _sy(bank) * sy * TB_TOP_BOLT[1], TB_TOP_Z[0])
            for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]


def throttle_mouth(bank: int):
    """Centre of the Ø82 hole the front end tank drops through its floor."""
    tx, ty = throttle_axis(bank)
    return (tx, ty, TB_SPIGOT[1])


def build_throttle(bank: int):
    s = _sy(bank)
    tx, ty = throttle_axis(bank)
    d = S.THROTTLE_D

    def cyl(z0, z1, dia):
        return geo.cyl_along((tx, ty, z0), (tx, ty, z1), dia)

    flange = bd.extrude(bd.Plane.XY.offset(TB_FLANGE_Z[0])
                        * (bd.Pos(tx, ty) * bd.RectangleRounded(TB_SQ, TB_SQ, TB_SQ_R)),
                        amount=TB_FLANGE_Z[1] - TB_FLANGE_Z[0])
    barrel = cyl(*TB_BARREL_Z, dia=TB_OD)
    top = bd.extrude(bd.Plane.XY.offset(TB_TOP_Z[0])
                     * (bd.Pos(tx, ty) * bd.RectangleRounded(*TB_TOP)),
                     amount=TB_TOP_Z[1] - TB_TOP_Z[0])
    spigot = cyl(TB_SPIGOT[0], TB_SPIGOT[1], TB_SPIGOT[2])
    pod = bd.Box(*POD).moved(bd.Location((tx, s * POD_Y, POD_Z)))
    # loom plug on the pod's REAR face: forward and outboard are both taken by
    # the top flange's bolt heads
    pod = fuse_all([pod, geo.cyl_along((tx - POD[0] / 2.0 + 2.0, s * POD_Y, POD_Z - 5.0),
                                       (tx - POD[0] / 2.0 - 12.0, s * POD_Y, POD_Z - 5.0),
                                       14.0)])
    cuts = [cyl(TB_FLANGE_Z[0] - 6.0, TB_SPIGOT[1] + 4.0, d),
            # cross-drilling for the butterfly shaft, both journals
            geo.cyl_along((tx, s * 8.0, TB_BUTTERFLY_Z), (tx, s * 124.0, TB_BUTTERFLY_Z),
                          TB_SHAFT_D + 1.2)]
    for p in throttle_bolt_points(bank):
        cuts.append(geo.cyl_along((p[0], p[1], TB_FLANGE_Z[0] - 2.0),
                                  (p[0], p[1], TB_FLANGE_Z[1] + 2.0), 8.6))
    for p in throttle_top_bolt_points(bank):
        cuts.append(geo.cyl_along((p[0], p[1], TB_TOP_Z[0] - 2.0),
                                  (p[0], p[1], TB_TOP_Z[1] + 2.0), 6.6))
    body = cut_all(fuse_all([flange, barrel, top, spigot, pod]), cuts)
    out = [P.style(body, f"throttle_body:{bank}", P.MACHINED)]

    # The joint itself: a gasket sandwiched between the plenum's cast deck face
    # (PAD_FACE) and the machined flange, standing 2 mm proud of the flange all
    # round so the plan view shows a bolted joint instead of a butt.
    gask = bd.extrude(bd.Plane.XY.offset(PAD_FACE)
                      * (bd.Pos(tx, ty) * bd.RectangleRounded(*TB_GASKET)),
                      amount=GASKET_T)
    gcuts = [cyl(PAD_FACE - 2.0, PAD_TOP + 2.0, d)]
    gcuts += [geo.cyl_along((p[0], p[1], PAD_FACE - 2.0), (p[0], p[1], PAD_TOP + 2.0), 8.6)
              for p in throttle_bolt_points(bank)]
    out.append(P.style(cut_all(gask, gcuts), f"throttle_gasket:{bank}", P.GASKET))

    shaft = geo.cyl_along((tx, s * 14.0, TB_BUTTERFLY_Z),
                          (tx, s * (POD_Y + 4.0), TB_BUTTERFLY_Z), TB_SHAFT_D)
    out.append(P.style(shaft, f"throttle_shaft:{bank}", P.MACHINED_STEEL))
    t = math.radians(14.0)                      # cracked open, not shut
    a = (math.sin(t), 0.0, math.cos(t))
    plate = geo.cyl_along((tx - 1.6 * a[0], ty, TB_BUTTERFLY_Z - 1.6 * a[2]),
                          (tx + 1.6 * a[0], ty, TB_BUTTERFLY_Z + 1.6 * a[2]), d - 1.4)
    out.append(P.style(cut_all(plate, [shaft]), f"throttle_plate:{bank}",
                       P.MACHINED_STEEL))

    cap8 = F.socket_cap_bolt(8.0, 14.0)
    for i, p in enumerate(throttle_bolt_points(bank)):
        out.append(P.style(F.place(cap8, p, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
                           f"throttle_bolt:{bank}_{i + 1}", P.TITANIUM))
    cap6 = F.socket_cap_bolt(6.0, 12.0)
    for i, p in enumerate(throttle_top_bolt_points(bank)):
        out.append(P.style(F.place(cap6, p, (0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
                           f"throttle_top_bolt:{bank}_{i + 1}", P.TITANIUM))
    return out


# ---------------------------------------------------------------------------
# 3. Intercoolers — one air-to-liquid core per bank, sitting over the plenums
# ---------------------------------------------------------------------------

IC_CORE_X = S.INTERCOOLER_X                  # (-250, 250)
IC_Y = S.INTERCOOLER_Y                       # (18, 200)
IC_Z = (406.0, 514.0)
IC_FRAME_T = 5.0
FIN_T = 1.4
FIN_PITCH = 7.0
FIN_MAX = 68
FIN_Z = (417.5, 512.0)                       # crest 2 mm under the lid's floor, so
                                             # the fin tops catch light through the
                                             # windows instead of sitting in shadow
TANK_X = (250.0, 298.0)                      # |x| band of the REAR (inlet) tank
TANK_FRONT_X1 = 336.0                        # the FRONT (outlet) tank overhangs the
                                             # throttle it drops into at x 254
TANK_Y = (14.0, 200.0)
TANK_CAP = 12.0                              # lofted cast end cap
TANK_WALL = 6.0
# --- the cast top cover ----------------------------------------------------
# Not a plate: a SAND-CAST lid, and the largest single surface in the top-down
# view, so it carries the whole cast vocabulary.  Section through it, inboard
# to outboard, at z:
#   514.0  seating plane on the core frame / end-tank tops
#   517.5  crest of the MACHINED sealing land — a bright 14 mm ring, 5 mm of it
#          left proud of the casting all round: the machined split line
#   522.0  the cast flange bands (the bolt bosses stand on those) and the flat
#          window frame outboard of the crown
#   526.0  crest of the cast bolt bosses
#   530.0  crest of the CROWNED deck: one barrel arc, R 87.3 in section, drawn
#          with two longitudinal ribs and a composite spine panel on it
# The core is read through ONE window per side, not a grille of small holes,
# and every screw stands on a cast boss over the joint face — no dot grid on
# open deck.
LID_X = (-(TANK_X[1] + TANK_CAP), TANK_FRONT_X1 + TANK_CAP)   # (-310, 348)
LID_Y = (12.0, 202.0)
LID_Z0 = IC_Z[1]                             # 514: seats on the frame/tank tops
# TWO radius families, and they are deliberately far apart so the eye can tell a
# sand casting from a milled face at plan-view distance: everything CAST on this
# assembly turns a corner on LID_R (20 mm, a radius a pattern-maker can pull),
# everything MACHINED on LID_MACH_R (4-6 mm, an end-mill radius).  The end tanks
# keep their own 16 mm cast section radius; the lid is bigger than the tank it
# sits on, which is how the two parts read as two parts from above.
LID_R = 20.0                                 # plan radius, outer corners (CAST family)
LID_MACH_R = 4.0                             # inner corners of every machined pocket
LAND_W = 14.0                                # machined sealing land, all round
LAND_T = 3.5                                 # 514 -> 517.5
LID_INSET = 5.0                              # the casting sits 5 mm inside the
                                             # land, so the joint reads as a rim
LID_BASE_Z = LID_Z0 + LAND_T                 # 517.5
LID_FLAT_Z = LID_BASE_Z + 4.5                # 522.0
LID_CROWN_Y = (39.0, 112.0)                  # |y| band of the crowned deck
LID_CROWN_H = 8.0                            # crown height over the flat
LID_RIB_Y = (47.0, 104.0)                    # longitudinal ribs, ON the crown
LID_RIB_W = 11.0
LID_RIB_H = 4.5
LID_RIB_DRAFT = 1.2                          # per side, over the rib height
LID_PANEL_Y = (61.0, 90.0)                   # composite spine panel on the crest
LID_PANEL_X = (-190.0, 270.0)
LID_PANEL_T = 3.5
LID_PANEL_BOLT_X = [-150.0, -20.0, 110.0, 240.0]
LID_WINDOW_Y = (124.0, 170.0)                # the ONE window per side
LID_WINDOW_X = (-232.0, 238.0)               # over the fins (they end at 234.5)
LID_RIM_W = 6.0                              # bright machined rim round it
LID_RIM_T = 0.9
LID_BOLT_Y = (28.0, 187.0)                   # the two flange bands
LID_BOLT_X0 = -285.0
LID_BOLT_PITCH = 74.0                        # the runner pitch
LID_BOLT_N = 9
LID_BOSS_D = 18.0                            # a boss, not a dot: Ø18 base, drafted to
LID_BOSS_H = 5.5                             # Ø16, standing 5.5 proud of the band, with
LID_BOLT_D = 6.0                             # a root fillet where it meets the casting
LID_SPOT_D = 11.5                            # machined spotface on the boss crest: the
LID_SPOT_T = 1.2                             # bright ring that separates head from cast
# Cross ribs: the two longitudinal ribs alone are two parallel lines, which from
# straight up is a stripe, not a casting.  Eight cross ribs on the half-pitch
# between the bolt stations turn them into a grid.  Where the composite spine
# panel covers the crest the rib runs as two stubs either side of it, which is
# what a real casting does under a bolted-on cover.
LID_XRIB_X = [-248.0, -174.0, -100.0, -26.0, 48.0, 122.0, 196.0, 270.0]
LID_XRIB_W = 8.0                             # width along X
LID_XRIB_H = 3.6                             # proud of the crown (under the 4.5 ribs)
LID_XRIB_GAP = 1.0                           # clearance either side of the spine panel
# Relieved step along the split line: the cast skirt is undercut 1.6 mm over a
# 2.6 mm band just above the machined land, so the joint throws a shadow line
# instead of the land and the casting sharing one flush wall.
LID_RELIEF_T = 1.6
LID_PAD = (36.0, 24.0, -270.0)               # cast-in ID pad: w, h, x
# Casting number, as raised bars on that pad — and DIFFERENT per bank, because a
# left and a right cast lid are two part numbers, never one part mirrored.
LID_CAST_NO = {1: (5.0, 2.4, 3.6, 2.4, 5.0), 2: (3.6, 5.0, 2.4, 5.0, 2.4)}
LID_CAST_NO_T = 1.4                          # bar height above the pad
LID_CAST_NO_H = 13.0                         # bar length across the pad (y)
# The crown is one circular arc through (LID_CROWN_Y[0], LID_FLAT_Z), its crest
# LID_CROWN_H higher, and (LID_CROWN_Y[1], LID_FLAT_Z).
LID_CROWN_YC = (LID_CROWN_Y[0] + LID_CROWN_Y[1]) / 2.0
LID_CROWN_R = ((((LID_CROWN_Y[1] - LID_CROWN_Y[0]) / 2.0) ** 2 + LID_CROWN_H ** 2)
               / (2.0 * LID_CROWN_H))
LID_CROWN_ZC = LID_FLAT_Z + LID_CROWN_H - LID_CROWN_R
# Charge-air inlet: a CAST neck on the rear tank's outboard face that ends in a
# V-band flange, so the trunk lands on a joint instead of stopping in mid air.
INLET_D = 68.0                               # = TRUNK_D, the bore through it
INLET_WALL = 7.0
INLET_X = -290.0                             # REAR tank, outboard face
INLET_Z = 462.0
VBAND_Y = (224.0, 232.0)                     # |y| of the neck flange; 232 = joint
VBAND_FLANGE_D = 100.0
# --- the coolant circuit ---------------------------------------------------
# An air-to-liquid core is a heat exchanger with TWO circuits, and the water
# side has to enter one end and leave the other or it is decoration.  Cold in
# LOW at the REAR of the core, hot out HIGH at the FRONT: both on the core's own
# outboard face (the end tanks are the AIR side and carry no water), each a cast
# boss on the frame wall, a short machined stub and a red -AN nut.  On bank 1
# the front (outlet) port is inside the museum section and is cut away with the
# rest of it — that is the section doing its job, not the banks disagreeing.
COOLANT_Y = IC_Y[1]                          # 200: the core frame's outboard face
COOLANT_BOSS_D = 34.0
COOLANT_BOSS_L = 12.0                        # cast boss, proud of the frame wall
COOLANT_STUB_D = 26.0
COOLANT_STUB_L = 18.0
COOLANT_BORE = 18.0
COOLANT_IN = (-196.0, 432.0)                 # (x, z) cold in, rear and low
COOLANT_OUT = (196.0, 492.0)                 # (x, z) hot out, front and high
# The one filler.  A cooling circuit has ONE pressure cap, at its high point, so
# it goes on ONE bank: a cast degas tower standing off bank 2's core just aft of
# the hot outlet, its cap 14 mm over the lid crest and 18 mm outboard of the lid
# edge, where it is unmissable from straight up.  Bank 1 does not get one, and
# that asymmetry is the point.
FILLER_BANK = 2
FILLER_X = 168.0
FILLER_Y = 220.0                             # riser axis, |y| (lid edge is 202)
FILLER_FOOT_Z = 486.0                        # horizontal Ø40 cast foot into the frame
FILLER_FOOT_D = 40.0
FILLER_RISER = (498.0, 526.0, 30.0)          # z0, z1, od
FILLER_NECK = (526.0, 534.0, 48.0)
FILLER_CAP = (534.0, 543.0, 58.0)
# The coolant temperature sender, on the OTHER bank, on the cold inlet where a
# sender belongs.  Bank 1 only: the pair of them is what stops the two tops
# reading as one part duplicated.
SENSOR_BANK = 1
SENSOR_SEAT = (-166.0, 200.0, 452.0)         # x, |y|, z on the frame's outboard face
SENSOR_DIR = (0.0, 0.87, 0.50)               # outboard and up (mirrored by bank)
SENSOR_BOSS_D = 22.0


def _sy(bank: int) -> float:
    return 1.0 if bank == 1 else -1.0


def _rect_yz(bank: int, y0: float, y1: float, z0: float, z1: float, r: float):
    s = _sy(bank)
    return bd.Pos(s * (y0 + y1) / 2.0, (z0 + z1) / 2.0) \
        * bd.RectangleRounded(y1 - y0, z1 - z0, r)


def build_intercooler(bank: int, sectioned: bool = True):
    s = _sy(bank)
    out = []
    # --- core frame: a rectangular tube the fins live inside ----------------
    outer = bd.extrude(geo.yz_plane(IC_CORE_X[0])
                       * _rect_yz(bank, IC_Y[0], IC_Y[1], IC_Z[0] + 6.0, IC_Z[1], 6.0),
                       amount=IC_CORE_X[1] - IC_CORE_X[0])
    inner = bd.extrude(geo.yz_plane(IC_CORE_X[0] + IC_FRAME_T)
                       * _rect_yz(bank, IC_Y[0] + IC_FRAME_T, IC_Y[1] - IC_FRAME_T,
                                  IC_Z[0] + 6.0 + IC_FRAME_T, IC_Z[1] + 16.0, 3.0),
                       amount=IC_CORE_X[1] - IC_CORE_X[0] - 2 * IC_FRAME_T)
    frame = geo.sectioned(outer - inner, bank, sectioned)
    if frame.solids():
        out.append(P.style(frame, f"intercooler_frame:{bank}", P.CAST))

    # --- finned core: ONE prototype plate, placed many times ----------------
    yc = s * (IC_Y[0] + IC_Y[1]) / 2.0
    zc = (FIN_Z[0] + FIN_Z[1]) / 2.0
    fin = bd.Box(FIN_T, IC_Y[1] - IC_Y[0] - 2 * IC_FRAME_T - 1.0,
                 FIN_Z[1] - FIN_Z[0])
    span = (FIN_MAX - 1) * FIN_PITCH
    for i in range(FIN_MAX):
        x = -span / 2.0 + i * FIN_PITCH
        if sectioned and bank == S.SECTION_BANK and x + FIN_T > S.SECTION_X:
            continue
        out.append(P.style(fin.moved(bd.Location((x, yc, zc))),
                           f"intercooler_fin:{bank}_{i + 1:02d}", P.INTERCOOLER_CORE))

    # --- cast end tanks -----------------------------------------------------
    for pos, sx in (("front", 1.0), ("rear", -1.0)):
        x_far = TANK_FRONT_X1 if pos == "front" else TANK_X[1]
        x0, x1 = sx * TANK_X[0], sx * x_far
        lo, hi = min(x0, x1), max(x0, x1)
        sec = _rect_yz(bank, TANK_Y[0], TANK_Y[1], IC_Z[0], IC_Z[1], 16.0)
        body = bd.extrude(geo.yz_plane(lo) * sec, amount=hi - lo)
        cap_far = sx * (x_far + TANK_CAP)
        body = fuse_all([body, bd.loft([geo.yz_plane(x1) * sec,
                                        geo.yz_plane(cap_far)
                                        * _rect_yz(bank, TANK_Y[0] + 16.0, TANK_Y[1] - 16.0,
                                                   IC_Z[0] + 14.0, IC_Z[1] - 14.0, 10.0)])])
        cav = _rect_yz(bank, TANK_Y[0] + TANK_WALL, TANK_Y[1] - TANK_WALL,
                       IC_Z[0] + TANK_WALL, IC_Z[1] - TANK_WALL, 10.0)
        void = bd.extrude(geo.yz_plane(min(lo, sx * (x_far + 2.0)))
                          * cav, amount=abs(x1 - x0) + TANK_CAP - 4.0)
        if pos == "front":
            # The outlet: straight down through the floor into the throttle.
            # It runs INTO the cavity, so it goes in as a SECOND, separate cut —
            # cut_all drops overlapping tools rather than cutting with them.
            mx, my, _mz = throttle_mouth(bank)
            body = cut_all(body, [void])
            void = geo.cyl_along((mx, my, IC_Z[0] - 8.0), (mx, my, IC_Z[0] + 30.0),
                                 TB_SPIGOT_CLEAR)
        tank = geo.sectioned(cut_all(body, [void]), bank, sectioned)
        if tank.solids():
            out.append(P.style(tank, f"intercooler_tank:{bank}_{pos}", P.CAST))
    return out


def _an_fitting(d: float = 12.0):
    """A -AN style fitting authored at the origin, +Z = outward along the port."""
    base = bd.Cylinder(d * 1.05, 6.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    hexn = bd.extrude(bd.Plane.XY.offset(6.0) * bd.RegularPolygon(d * 1.15, 6), amount=11.0)
    nut = bd.extrude(bd.Plane.XY.offset(17.0) * bd.RegularPolygon(d * 1.02, 6), amount=9.0)
    tip = bd.Cone(d * 0.72, d * 0.58, 8.0,
                  align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, 26.0)))
    bore = bd.Cylinder(d * 0.42, 40.0,
                       align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, -1.0)))
    return fuse_all([base, hexn]) - bore, fuse_all([nut, tip]) - bore


def lid_bolt_points(bank: int):
    """M6 seats on the cast lid: two rows on the perimeter flange bands, on the
    runner pitch, every one on a cast boss standing over the machined joint
    face.  Nothing is screwed into open deck — that is what made the old
    pattern read as sprinkled dots."""
    s = _sy(bank)
    z = LID_FLAT_Z + LID_BOSS_H
    return [(LID_BOLT_X0 + i * LID_BOLT_PITCH, s * y, z)
            for i in range(LID_BOLT_N) for y in LID_BOLT_Y]


def _crown_z(y: float, off: float = 0.0) -> float:
    """Height of the lid's crown arc at |y|; `off` offsets it CONCENTRICALLY,
    which is how the composite panel gets a constant-thickness curved shell."""
    r = LID_CROWN_R + off
    d = abs(y) - LID_CROWN_YC
    return LID_CROWN_ZC + math.sqrt(max(r * r - d * d, 0.0))


def _bx(shape):
    """World AABB without tessellating (`bounding_box()` meshes AND mutates)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape.wrapped, box, False)
    return box.Get()


def _lid_rect(bank: int, x0: float, x1: float, y0: float, y1: float,
              r: float, z: float):
    """A rounded rectangle in the plane z, spanning x0..x1 and |y| y0..y1."""
    s = _sy(bank)
    return bd.Plane.XY.offset(z) * (bd.Pos((x0 + x1) / 2.0, s * (y0 + y1) / 2.0)
                                    * bd.RectangleRounded(x1 - x0, y1 - y0, r))


def _lid_section(bank: int):
    """The cast lid's YZ section as ordered segments: ('L', p0, p1) for a line,
    ('A', p0, pmid, p1) for an arc.

    Inboard flange band -> crowned deck (ONE arc, two longitudinal ribs
    standing on it) -> flat window frame -> outboard flange band.  Every corner
    is rounded in 2D, which is what gives the ribs and the crown their casting
    radii without a single 3D fillet on a 650 mm casting.
    """
    s = _sy(bank)

    def p(y, z):
        return (s * y, z)

    y0, y1 = LID_Y[0] + LID_INSET, LID_Y[1] - LID_INSET
    c0, c1 = LID_CROWN_Y
    segs = [("L", p(y0, LID_BASE_Z), p(y1, LID_BASE_Z)),
            ("L", p(y1, LID_BASE_Z), p(y1, LID_FLAT_Z)),
            ("L", p(y1, LID_FLAT_Z), p(c1, _crown_z(c1)))]
    y = c1
    for yr in sorted(LID_RIB_Y, reverse=True):
        a, b = yr + LID_RIB_W / 2.0, yr - LID_RIB_W / 2.0
        crest = _crown_z(yr) + LID_RIB_H
        segs += [("A", p(y, _crown_z(y)), p((y + a) / 2.0, _crown_z((y + a) / 2.0)),
                  p(a, _crown_z(a))),
                 ("L", p(a, _crown_z(a)), p(a - LID_RIB_DRAFT, crest)),
                 ("L", p(a - LID_RIB_DRAFT, crest), p(b + LID_RIB_DRAFT, crest)),
                 ("L", p(b + LID_RIB_DRAFT, crest), p(b, _crown_z(b)))]
        y = b
    segs += [("A", p(y, _crown_z(y)), p((y + c0) / 2.0, _crown_z((y + c0) / 2.0)),
              p(c0, _crown_z(c0))),
             ("L", p(c0, _crown_z(c0)), p(y0, LID_FLAT_Z)),
             ("L", p(y0, LID_FLAT_Z), p(y0, LID_BASE_Z))]
    return segs


def _seg_edges(segs):
    edges = []
    for seg in segs:
        if seg[0] == "L":
            edges += bd.Polyline(seg[1], seg[2]).edges()
        else:
            edges += bd.ThreePointArc(seg[1], seg[2], seg[3]).edges()
    return edges


def _lid_face(bank: int, x: float, r: float = 2.0):
    face = bd.make_face(_seg_edges(_lid_section(bank)))
    if r > 0:
        face = _fillet2d(face, r)
    return geo.yz_plane(x) * face


def _crown_band(bank: int, y0: float, y1: float, off1: float, x0: float, x1: float):
    """A constant-thickness band lying ON the crown between |y| y0..y1, `off1`
    proud of it, run from station x0 to x1 — the cross ribs are built the same
    way the composite spine panel is, so they sit on the arc instead of cutting
    through it."""
    s = _sy(bank)

    def pp(y, off=0.0):
        return (s * y, _crown_z(y, off))

    ym = (y0 + y1) / 2.0
    face = bd.make_face(_seg_edges(
        [("A", pp(y0), pp(ym), pp(y1)),
         ("L", pp(y1), pp(y1, off1)),
         ("A", pp(y1, off1), pp(ym, off1), pp(y0, off1)),
         ("L", pp(y0, off1), pp(y0))]))
    return bd.extrude(geo.yz_plane(x0) * _fillet2d(face, 0.8), amount=x1 - x0)


def _lid_cross_ribs(bank: int):
    """One rib per station, split around the spine panel where it covers the
    crest (the panel spans LID_PANEL_X only, so the end ribs run full width)."""
    y0, y1 = LID_RIB_Y
    p0, p1 = LID_PANEL_Y[0] - LID_XRIB_GAP, LID_PANEL_Y[1] + LID_XRIB_GAP
    ribs = []
    for x in LID_XRIB_X:
        a, b = x - LID_XRIB_W / 2.0, x + LID_XRIB_W / 2.0
        if LID_PANEL_X[0] - LID_XRIB_W < x < LID_PANEL_X[1] + LID_XRIB_W:
            spans = ((y0, p0), (p1, y1))
        else:
            spans = ((y0, y1),)
        for s0, s1 in spans:
            ribs.append(_crown_band(bank, s0, s1, LID_XRIB_H, a, b))
    return ribs


def build_intercooler_lid(bank: int, sectioned: bool = True):
    """The cast top cover — a crowned, ribbed sand casting, not a plate.

    A barrel-crowned deck (R 87 in section) carrying two longitudinal ribs and
    a black composite spine panel, a bright MACHINED sealing land showing 5 mm
    proud all round (the split line), a cast boss under every one of the 18
    screws on the two flange bands, and ONE window per side over the core with
    a machined rim.
    """
    s = _sy(bank)
    out = []
    bx = (LID_X[0] + LID_INSET, LID_X[1] - LID_INSET)      # cast footprint
    by = (LID_Y[0] + LID_INSET, LID_Y[1] - LID_INSET)
    wx, wy, w = LID_WINDOW_X, LID_WINDOW_Y, LID_RIM_W

    # --- bright leaf: the machined split line + the window's rim ------------
    bright = [cut_all(
        bd.extrude(_lid_rect(bank, LID_X[0], LID_X[1], LID_Y[0], LID_Y[1],
                             LID_R, LID_Z0), LAND_T),
        [bd.extrude(_lid_rect(bank, LID_X[0] + LAND_W, LID_X[1] - LAND_W,
                              LID_Y[0] + LAND_W, LID_Y[1] - LAND_W, LID_MACH_R,
                              LID_Z0 - 1.0), LAND_T + 2.0)]),
        cut_all(
        bd.extrude(_lid_rect(bank, wx[0] - w, wx[1] + w, wy[0] - w, wy[1] + w,
                             LID_MACH_R + 2.0, LID_FLAT_Z), LID_RIM_T),
        [bd.extrude(_lid_rect(bank, wx[0], wx[1], wy[0], wy[1], 10.0,
                              LID_FLAT_Z - 1.0), LID_RIM_T + 2.0)])]
    land = geo.sectioned(bd.Compound(bright), bank, sectioned)
    if land.solids():
        out.append(P.style(land, f"intercooler_lid_land:{bank}", P.MACHINED))

    # --- cast body: the crowned section run along X, plan corners rounded ---
    body = bd.extrude(_lid_face(bank, bx[0]), amount=bx[1] - bx[0])
    plan = bd.extrude(_lid_rect(bank, bx[0], bx[1], by[0], by[1],
                                LID_R - LID_INSET, LID_Z0), 60.0)
    body = cut_all(body, [bd.extrude(
        _lid_rect(bank, bx[0] - 40.0, bx[1] + 40.0, by[0] - 40.0, by[1] + 40.0,
                  6.0, LID_Z0), 60.0) - plan])
    # The two cast end faces are left with a crisp perimeter ON PURPOSE: a
    # fillet round that whole ribbed loop is accepted by OCC (is_sound passes)
    # and yet bulges the casting 4 mm proud of its own crown — measured, see
    # tmp/ind_sec2.log.  Every other edge on this part is radiused in 2D.

    # --- cast boss under every bolt + the cross-rib grid on the crown -------
    boss = C.boss(LID_BOSS_D, LID_BOSS_H, draft_deg=10.0, fillet_r=1.2)
    seats = [p for p in lid_bolt_points(bank)
             if not geo.in_section_void(p, bank, sectioned)]
    body = fuse_all([body]
                    + [boss.moved(bd.Location((p[0], p[1], LID_FLAT_Z)))
                       for p in seats]
                    + _lid_cross_ribs(bank))
    body, _ = C.safe_fillet(body, C.edges_at(body, z=LID_FLAT_Z, kind="CIRCLE"),
                            1.5, min_r=0.5)

    # --- window, bolt holes + spotfaces, and the relieved split-line step ---
    cuts = [bd.extrude(_lid_rect(bank, wx[0], wx[1], wy[0], wy[1], LID_MACH_R + 2.0,
                                 LID_Z0 - 2.0), 40.0)]
    cuts += [geo.cyl_along((p[0], p[1], LID_Z0 - 2.0), (p[0], p[1], p[2] + 2.0),
                           LID_BOLT_D + 0.6) for p in seats]
    cuts += [geo.cyl_along((p[0], p[1], p[2] - LID_SPOT_T), (p[0], p[1], p[2] + 2.0),
                           LID_SPOT_D) for p in seats]
    t = LID_RELIEF_T
    cuts.append(bd.extrude(_lid_rect(bank, bx[0] - 40.0, bx[1] + 40.0,
                                     by[0] - 40.0, by[1] + 40.0, 6.0,
                                     LID_BASE_Z + 1.0), 2.6)
                - bd.extrude(_lid_rect(bank, bx[0] + t, bx[1] - t, by[0] + t,
                                       by[1] - t, LID_R - LID_INSET - t,
                                       LID_BASE_Z - 1.0), 8.0))
    body = geo.sectioned(cut_all(body, cuts), bank, sectioned)
    if body.solids():
        out.append(P.style(body, f"intercooler_lid:{bank}", P.CAST))

    # --- composite spine panel, a constant-thickness shell on the crest -----
    py0, py1, t = LID_PANEL_Y[0], LID_PANEL_Y[1], LID_PANEL_T
    ym = (py0 + py1) / 2.0

    def pp(y, off=0.0):
        return (s * y, _crown_z(y, off))

    panel = bd.extrude(geo.yz_plane(LID_PANEL_X[0]) * _fillet2d(bd.make_face(
        _seg_edges([("A", pp(py0), pp(ym), pp(py1)),
                    ("L", pp(py1), pp(py1, t)),
                    ("A", pp(py1, t), pp(ym, t), pp(py0, t)),
                    ("L", pp(py0, t), pp(py0))])), 1.0),
        amount=LID_PANEL_X[1] - LID_PANEL_X[0])
    panel, _ = C.fillet_all(panel, 1.2, min_r=0.4)
    pbolts = [(x, s * LID_CROWN_YC, _crown_z(LID_CROWN_YC, t))
              for x in LID_PANEL_BOLT_X]
    panel = cut_all(panel, [geo.cyl_along((p[0], p[1], p[2] + 4.0),
                                          (p[0], p[1], p[2] - 12.0), 5.6)
                            for p in pbolts])
    panel = geo.sectioned(panel, bank, sectioned)
    if panel.solids():
        out.append(P.style(panel, f"intercooler_lid_panel:{bank}", P.COMPOSITE))
    cap5 = F.socket_cap_bolt(5.0, t)
    for i, p in enumerate(pbolts):
        if geo.in_section_void(p, bank, sectioned):
            continue
        out.append(P.style(F.place(cap5, p, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
                           f"intercooler_lid_panel_bolt:{bank}_{i + 1}", P.TITANIUM))

    # --- cast-in ID pad, carrying THIS bank's casting number ---------------
    pw, ph, pxp = LID_PAD
    pad = F.place(F.id_pad(pw, ph, 2.0), (pxp, s * 148.0, LID_FLAT_Z),
                  (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    bars = LID_CAST_NO[bank]
    x0 = pxp - (len(bars) - 1) * 7.0 / 2.0
    pad = fuse_all([pad] + [
        bd.Box(w, LID_CAST_NO_H, LID_CAST_NO_T,
               align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
                   bd.Location((x0 + i * 7.0, s * 148.0, LID_FLAT_Z + 2.0)))
        for i, w in enumerate(bars)])
    pad = geo.sectioned(pad, bank, sectioned)
    if pad.solids():
        out.append(P.style(pad, f"intercooler_lid_pad:{bank}", P.MACHINED))

    # 7.5 mm of shank from the SPOTFACE floor: down through the 4.5 mm flange
    # band, stopping 1 mm inside it, so no screw pokes through into the core.
    cap = F.socket_cap_bolt(LID_BOLT_D, 7.5)
    for i, p in enumerate(seats):
        out.append(P.style(
            F.place(cap, (p[0], p[1], p[2] - LID_SPOT_T), (0.0, 0.0, 1.0),
                    (1.0, 0.0, 0.0)),
            f"intercooler_lid_bolt:{bank}_{i + 1:02d}", P.TITANIUM))
    return out


def build_intercooler_furniture(bank: int, sectioned: bool = True):
    """The water side of the air-to-liquid core — a cross-flow circuit, cold in
    low at the rear and hot out high at the front — plus the one pressure cap
    (bank 2) and the one temperature sender (bank 1), and the cast charge-air
    inlet neck that the charge trunk's V-band clamps onto."""
    s = _sy(bank)
    out = []
    body_proto, nut_proto = _an_fitting(12.0)
    for tag, (px, pz) in (("in", COOLANT_IN), ("out", COOLANT_OUT)):
        p = (px, s * COOLANT_Y, pz)
        y_boss = s * (COOLANT_Y + COOLANT_BOSS_L)
        y_stub = s * (COOLANT_Y + COOLANT_BOSS_L + COOLANT_STUB_L)
        ax = (0.0, s, 0.0)
        port = fuse_all([geo.cyl_along(p, (px, y_boss, pz), COOLANT_BOSS_D),
                         geo.cyl_along((px, y_boss, pz), (px, y_stub, pz),
                                       COOLANT_STUB_D)])
        port = cut_all(port, [geo.cyl_along((px, s * (COOLANT_Y - 2.0), pz),
                                            (px, y_stub + s * 2.0, pz),
                                            COOLANT_BORE)])
        port = geo.sectioned(port, bank, sectioned)
        if port.solids():
            out.append(P.style(port, f"intercooler_coolant_boss:{bank}_{tag}",
                               P.CAST))
        crown = (px, y_stub, pz)
        if not geo.in_section_void(crown, bank, sectioned):
            out.append(P.style(F.place(body_proto, crown, ax, (0.0, 0.0, 1.0)),
                               f"coolant_fitting:{bank}_{tag}", P.MACHINED))
            out.append(P.style(F.place(nut_proto, crown, ax, (0.0, 0.0, 1.0)),
                               f"coolant_fitting_nut:{bank}_{tag}", P.RED_ANODISE))

    # --- the one pressure cap, bank 2 only ---------------------------------
    if bank == FILLER_BANK:
        fy = s * FILLER_Y
        z0, z1, od = FILLER_RISER
        tower = fuse_all([
            geo.cyl_along((FILLER_X, s * COOLANT_Y, FILLER_FOOT_Z),
                          (FILLER_X, fy, FILLER_FOOT_Z), FILLER_FOOT_D),
            geo.cyl_along((FILLER_X, fy, z0), (FILLER_X, fy, z1), od)])
        tower = cut_all(tower, [geo.cyl_along((FILLER_X, fy, z1 + 2.0),
                                              (FILLER_X, fy, FILLER_FOOT_Z), 15.0)])
        out.append(P.style(tower, f"coolant_filler_tower:{bank}", P.CAST))
        n0, n1, nd = FILLER_NECK
        neck = geo.cyl_along((FILLER_X, fy, n0), (FILLER_X, fy, n1), nd)
        neck = neck - geo.cyl_along((FILLER_X, fy, n0 - 2.0), (FILLER_X, fy, n1 + 2.0),
                                    nd - 12.0)
        out.append(P.style(neck, f"coolant_filler_neck:{bank}", P.MACHINED))
        c0, c1, cd = FILLER_CAP
        cap = fuse_all([geo.cyl_along((FILLER_X, fy, c0), (FILLER_X, fy, c0 + 6.0), cd),
                        geo.cyl_along((FILLER_X, fy, c0 + 6.0), (FILLER_X, fy, c1),
                                      cd - 16.0)])
        out.append(P.style(cap, f"coolant_pressure_cap:{bank}", P.RED_ANODISE))

    # --- the one temperature sender, bank 1 only ---------------------------
    if bank == SENSOR_BANK:
        seat = (SENSOR_SEAT[0], s * SENSOR_SEAT[1], SENSOR_SEAT[2])
        d = (SENSOR_DIR[0], s * SENSOR_DIR[1], SENSOR_DIR[2])
        tip = tuple(seat[i] + d[i] * 14.0 for i in range(3))
        if not geo.in_section_void(seat, bank, sectioned):
            out.append(P.style(geo.cyl_along(seat, tip, SENSOR_BOSS_D),
                               f"coolant_sensor_boss:{bank}", P.CAST))
            out.append(P.style(
                fuse_all([F.place(F.hex_nut(12.0), tip, d, (1.0, 0.0, 0.0)),
                          geo.cyl_along(tip, tuple(seat[i] + d[i] * 26.0
                                                   for i in range(3)), 13.0)]),
                f"coolant_sensor:{bank}", P.MACHINED_STEEL))
            out.append(P.style(
                F.place(bd.Box(14.0, 12.0, 16.0),
                        tuple(seat[i] + d[i] * 30.0 for i in range(3)),
                        d, (1.0, 0.0, 0.0)),
                f"coolant_sensor_plug:{bank}", P.COMPOSITE))

    # Cast charge-air inlet neck: it starts FLUSH with the tank's outboard face
    # (a neck sunk into the wall would interpenetrate the tank leaf) and ends in
    # the V-band flange the trunk lands on.
    a = (INLET_X, s * TANK_Y[1], INLET_Z)
    b = (INLET_X, s * VBAND_Y[0], INLET_Z)
    c = (INLET_X, s * VBAND_Y[1], INLET_Z)
    neck = fuse_all([geo.cyl_along(a, b, INLET_D + 2 * INLET_WALL),
                     geo.cyl_along(b, c, VBAND_FLANGE_D)])
    neck = cut_all(neck, [geo.cyl_along(
        (INLET_X, s * (TANK_Y[1] - 4.0), INLET_Z),
        (INLET_X, s * (VBAND_Y[1] + 4.0), INLET_Z), INLET_D)])
    out.append(P.style(neck, f"intercooler_inlet_neck:{bank}", P.CAST))
    return out


# ---------------------------------------------------------------------------
# 4. Charge pipes — compressor outlets -> Y -> rear intercooler tank (hardware)
# ---------------------------------------------------------------------------

PIPE_D = 60.0
PIPE_WALL = 2.2
TRUNK_D = 68.0
PIPE_BEND_R = 1.6 * PIPE_D
TRUNK_BEND_R = 1.6 * TRUNK_D

# spec.turbo(...)['compressor_outlet'] = (+/-192 | -222, s*435, 80), facing +Z,
# on a Ø55 stub.
#
# ROUTING.  The museum section opens bank 1 for x > 121, so ANY pipe standing
# up across that face hides the internals the display exists to show.  Both
# banks therefore use the same layout, mirrored: the FRONT turbo's pipe leaves
# its stub, turns aft immediately and runs the length of the engine along the
# cover flank at |y| 435 / z 208 — outboard of the cam cover (its outer corner
# is at |y| 363, z 182), outboard of the exhaust log and its heat-shield lid
# (|y| 355..391, z to 168.7), and 18 mm over the log's turbine neck, which is
# the tallest thing in the |y| 400..470 corridor at z 160.  It meets the REAR
# turbo's short riser at x -222, and ONE trunk climbs from there to the rear
# intercooler tank.  So the only riser on either bank stands 340 mm behind the
# section plane.
FLANK_Y = 435.0
FLANK_Z = 208.0
OUTLET_D = 55.0                              # turbos.C_OUT_D, the stub the coupler grips
FRONT_OUTLET = (192.0, 435.0, 80.0)
REAR_OUTLET = (-222.0, 435.0, 80.0)
JOINT_Z = 84.0                               # pipe end, 4 mm off the stub face
MERGE = (-222.0, FLANK_Y, 268.0)

FRONT_BRANCH = [(192.0, FLANK_Y, JOINT_Z), (192.0, FLANK_Y, FLANK_Z),
                (-152.0, FLANK_Y, FLANK_Z), MERGE]
REAR_BRANCH = [(-222.0, FLANK_Y, JOINT_Z), MERGE]
TRUNK = [MERGE, (-248.0, 432.0, 384.0), (-276.0, 392.0, 440.0),
         (-290.0, 320.0, INLET_Z), (INLET_X, VBAND_Y[1], INLET_Z)]
# One straight hose coupler mid-run; the intercooler end is a V-band joint.
COUPLERS = [((30.0, FLANK_Y, FLANK_Z), (1.0, 0.0, 0.0), PIPE_D)]
COUPLER_LEN = 48.0
# The trunk's 200 mm unsupported climb is the one length of pipe on the engine
# that really was held up by nothing.  A saddle clamp on the straight, a rod and
# a bolted foot on the core frame's outboard wall tie it down.  Routed at
# x -238.5, which is 51.5 mm off the V-band's axis: outside the Ø116 band and
# outside the Ø82 inlet neck, for every z the strut passes through.
STAY_SEAT_T = 0.65                           # along MERGE -> TRUNK[1]
STAY_ROD_D = 14.0
STAY_FOOT = (-238.0, 200.0, 424.0)           # x, |y|, z on the core frame
STAY_FOOT_BOX = (28.0, 6.0, 22.0)

# The turbo joint is not straight and not a plain reducer.  turbos.py lofts the
# discharge neck so the stub's centre walks OUTBOARD as it drops (16 mm over
# 42 mm) and puts a rolled Ø61 bead on it 7 mm under the face, so a vertical
# Ø55 sleeve cuts straight through both.  The hose follows the stub's own
# centreline and steps: snug on the plain stub, stretched over the bead, snug
# again on the Ø60 pipe.
# Measured off turbos.build(): the stub section's centre walks from |y| 435.6
# at z 124.5 to 445.7 at z 106, and the bead is Ø62 about (437.7, 118).
TURBO_LEAN = 0.575
JOINT_Y0, JOINT_Z0 = 435.6, 79.5
JOINT_LEAN_SEG = ((59.0, 69.0, 70.0, 60.0),      # (z0, z1, od, id) snug on the stub
                  (68.0, 82.0, 78.0, 68.0))      # stretched over the Ø62 bead
JOINT_TOP = (80.5, 107.0, 73.0, 63.0)             # vertical, over the Ø60 pipe
JOINT_CLAMP = ((63.0, 70.0, False), (97.0, 73.0, True))


def _stub_point(bank: int, x: float, z: float):
    """A point on the compressor stub's leaning centreline at height z."""
    return (x, _sy(bank) * (JOINT_Y0 + (JOINT_Z0 - z) * TURBO_LEAN), z)


def _sweep_shell(pts, od: float, wall: float, radius: float):
    path = None
    for r in (radius, radius * 0.8, radius * 0.62, radius * 0.45):
        try:
            path = bd.FilletPolyline(*[bd.Vector(*p) for p in pts], radius=r)
            break
        except Exception:
            continue
    if path is None:
        path = bd.Polyline(*[bd.Vector(*p) for p in pts])
    t0 = tuple(pts[1][i] - pts[0][i] for i in range(3))
    pl = geo.plane(pts[0], t0)
    return (bd.sweep(pl * bd.Circle(od / 2.0), path, is_frenet=True),
            bd.sweep(pl * bd.Circle(od / 2.0 - wall), path, is_frenet=True))


def _tube(p0, p1, od: float, idm: float):
    v = tuple(p1[i] - p0[i] for i in range(3))
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    e = tuple(c / n * 2.0 for c in v)
    a = tuple(p0[i] - e[i] for i in range(3))
    b = tuple(p1[i] + e[i] for i in range(3))
    return geo.cyl_along(p0, p1, od) - geo.cyl_along(a, b, idm)


def build_charge_pipes(bank: int):
    s = _sy(bank)

    def f(p):
        return (p[0], s * p[1], p[2])

    outs, ins = [], []
    for pts, d, r in ((FRONT_BRANCH, PIPE_D, PIPE_BEND_R),
                      (REAR_BRANCH, PIPE_D, PIPE_BEND_R),
                      (TRUNK, TRUNK_D, TRUNK_BEND_R)):
        o, i = _sweep_shell([f(p) for p in pts], d, PIPE_WALL, r)
        outs.append(o)
        ins.append(i)
    pipe = fuse_all(outs) - fuse_all(ins)
    out = [P.style(pipe, f"charge_pipe:{bank}", P.ALUMINIUM_TUBE)]

    def _clamp(seat, axis, od, tag, perp=None):
        """A T-bolt clamp: a band round the hose plus its trunnion block."""
        n = math.sqrt(sum(v * v for v in axis)) or 1.0
        u = tuple(v / n for v in axis)
        q0 = tuple(seat[i] - u[i] * 4.5 for i in range(3))
        q1 = tuple(seat[i] + u[i] * 4.5 for i in range(3))
        ring = _tube(q0, q1, od + 6.5, od + 1.5)
        if perp is None:
            perp = (0.0, 0.0, 1.0) if abs(u[2]) < 0.7 else (1.0, 0.0, 0.0)
        pn = math.sqrt(sum(v * v for v in perp)) or 1.0
        perp = tuple(v / pn for v in perp)
        blk = tuple(seat[i] + perp[i] * (od / 2.0 + 6.0) for i in range(3))
        out.append(P.style(fuse_all([ring, F.place(bd.Box(9.0, 13.0, 15.0), blk, perp, u)]),
                           tag, P.MACHINED_STEEL))

    # the two turbo joints: stepped hoses on the leaning compressor stubs
    lean = (0.0, -s * TURBO_LEAN, 1.0)
    up_out = (0.0, s * 1.0, TURBO_LEAN)            # outboard, square to the lean
    for n, x in ((1, FRONT_OUTLET[0]), (2, REAR_OUTLET[0])):
        # the leaning sections are trimmed flat top and bottom: a tilted Ø78 end
        # face otherwise dips 17 mm and clips the volute below it
        lean_body = cut_all(
            fuse_all([_tube(_stub_point(bank, x, z0), _stub_point(bank, x, z1), od, idm)
                      for z0, z1, od, idm in JOINT_LEAN_SEG]),
            [bd.Box(400.0, 400.0, 400.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
                        bd.Location((x, s * 440.0, JOINT_LEAN_SEG[0][0]))),
             bd.Box(400.0, 400.0, 400.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
                        bd.Location((x, s * 440.0, JOINT_LEAN_SEG[1][1])))])
        top = _tube((x, s * 435.0, JOINT_TOP[0]), (x, s * 435.0, JOINT_TOP[1]),
                    JOINT_TOP[2], JOINT_TOP[3])
        out.append(P.style(fuse_all([lean_body, top]),
                           f"charge_coupler:{bank}_{n}", P.HOSE))
        for k, (cz, od, vertical) in enumerate(JOINT_CLAMP):
            seat = (x, s * 435.0, cz) if vertical else _stub_point(bank, x, cz)
            _clamp(seat, (0.0, 0.0, 1.0) if vertical else lean, od,
                   f"charge_clamp:{bank}_{n}{'ab'[k]}",
                   None if vertical else up_out)

    # the straight one: mid-run along the cover flank
    for n, (c, ax, d) in enumerate(COUPLERS, start=3):
        cc, a = f(c), (ax[0], s * ax[1], ax[2])
        half = COUPLER_LEN / 2.0

        def at(t, cc=cc, a=a):
            return tuple(cc[i] + a[i] * t for i in range(3))

        out.append(P.style(_tube(at(-half), at(half), d + 12.0, d + 3.0),
                           f"charge_coupler:{bank}_{n}", P.HOSE))
        for k, t in enumerate((-half + 9.0, half - 9.0)):
            _clamp(at(t), a, d + 12.0, f"charge_clamp:{bank}_{n}{'ab'[k]}")

    # The trunk's climb, anchored: saddle -> rod -> bolted foot on the core.
    a0, a1 = f(MERGE), f(TRUNK[1])
    seat = tuple(a0[i] + STAY_SEAT_T * (a1[i] - a0[i]) for i in range(3))
    u = tuple(a1[i] - a0[i] for i in range(3))
    un = math.sqrt(sum(v * v for v in u))
    u = tuple(v / un for v in u)
    foot = (STAY_FOOT[0], s * STAY_FOOT[1], STAY_FOOT[2])
    v = tuple(foot[i] - seat[i] for i in range(3))
    vn = math.sqrt(sum(c * c for c in v))
    v = tuple(c / vn for c in v)
    rod0 = tuple(seat[i] + v[i] * (TRUNK_D / 2.0 + 6.0) for i in range(3))
    plate = F.place(bd.Box(*STAY_FOOT_BOX),
                    (foot[0], s * (STAY_FOOT[1] + STAY_FOOT_BOX[1] / 2.0), foot[2]),
                    (0.0, s, 0.0), (1.0, 0.0, 0.0))
    stay = fuse_all([
        _tube(tuple(seat[i] - u[i] * 8.0 for i in range(3)),
              tuple(seat[i] + u[i] * 8.0 for i in range(3)),
              TRUNK_D + 14.0, TRUNK_D + 0.8),
        geo.cyl_along(rod0, foot, STAY_ROD_D), plate])
    out.append(P.style(stay, f"charge_pipe_stay:{bank}", P.MACHINED_STEEL))
    out.append(P.style(
        F.place(F.hex_flange_bolt(8.0, 18.0),
                (foot[0], s * (STAY_FOOT[1] + STAY_FOOT_BOX[1]), foot[2]),
                (0.0, s, 0.0), (1.0, 0.0, 0.0)),
        f"charge_pipe_stay_bolt:{bank}", P.MACHINED_STEEL))

    # The intercooler end is a REAL joint, not a tube stopping in mid air: a
    # machined flange welded on the trunk, butted to the cast inlet neck's
    # flange, held by a V-band clamp with its T-bolt trunnion on top.
    jy = VBAND_Y[1]
    out.append(P.style(
        _tube((INLET_X, s * jy, INLET_Z), (INLET_X, s * (jy + 8.0), INLET_Z),
              VBAND_FLANGE_D, TRUNK_D),
        f"charge_vband_flange:{bank}", P.MACHINED))
    band = _tube((INLET_X, s * (jy - 9.0), INLET_Z),
                 (INLET_X, s * (jy + 15.0), INLET_Z),
                 VBAND_FLANGE_D + 16.0, VBAND_FLANGE_D + 1.0)
    lug_z = INLET_Z + VBAND_FLANGE_D / 2.0 + 9.0
    lug = F.place(bd.Box(13.0, 17.0, 22.0), (INLET_X, s * (jy + 3.0), lug_z),
                  (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    out.append(P.style(fuse_all([band, lug]), f"charge_vband_clamp:{bank}",
                       P.MACHINED_STEEL))
    out.append(P.style(
        F.place(F.hex_flange_bolt(8.0, 22.0),
                (INLET_X + 7.0, s * (jy + 3.0), lug_z), (1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0)),
        f"charge_vband_bolt:{bank}", P.MACHINED_STEEL))
    return out


# ---------------------------------------------------------------------------
# 5. Fuel rails + injectors (bank-1 statics)
#
# spec.FUEL_RAIL_M/H = (156, 360): outboard of the head's inner face (m 130),
# on the shoulder above the runners, with the injectors angled down and inboard
# into the runner just behind its port flange.
# ---------------------------------------------------------------------------

RAIL_M, RAIL_H = 156.0, 360.0
RAIL_W, RAIL_T = 18.0, 16.0                  # section across m, across h
RAIL_X = (-282.0, 284.0)     # past cylinder 8/16 at |x| 269, and no further:
                                             # covers' breather line crosses at x -292
FEED_X = 232.0                               # -AN feed, standing UP off the rail:
                                             # a +X spigot on the front end would reach
                                             # x 318, inside the chain zone, and an
                                             # inboard one would foul the plenum shoulder
DAMPER_X = (-262.0, -282.0)                  # pulse damper + domed end cap, no fatter
DAMPER_D = 22.0                              # than the rail: Ø38 came within 5 mm of
                                             # the cam cover and swallowed injector 16
# The only stations that clear every injector on BOTH banks (they are staggered
# 20 mm) by more than shank + bracket, and stay off the plenum's front deck.
BRACKET_X = [148.0, 74.0, -74.0, -148.0]
BRACKET_T = 12.0
INJ_A = (154.0, 360.0)                       # injector axis, (m, h) at the rail
INJ_B = (170.0, 296.0)                       # (m, h) inside the runner
INJ_D, INJ_TIP_D, INJ_BOSS_D = 22.0, 13.0, 32.0


def _inj(bank: int, x: float, t: float):
    m = INJ_A[0] + t * (INJ_B[0] - INJ_A[0])
    h = INJ_A[1] + t * (INJ_B[1] - INJ_A[1])
    return bp(bank, x, m, h)


def injector_boss_bore(bank: int, x: float):
    """(boss, bore) fused into / cut from the plenum runner at station x."""
    # starts at t 0.45, not 0.32: any earlier and the boss tops out above z 366
    # and fouls the downdraught throttle's flange at the front of the plenum.
    boss = geo.cyl_along(_inj(bank, x, 0.45), _inj(bank, x, 0.92), INJ_BOSS_D)
    bore = geo.cyl_along(_inj(bank, x, -0.12), _inj(bank, x, 1.12), INJ_D + 0.4)
    return boss, bore


def _rail_pts(bank: int):
    m0, m1 = RAIL_M - RAIL_W / 2.0, RAIL_M + RAIL_W / 2.0
    h0, h1 = RAIL_H - RAIL_T / 2.0, RAIL_H + RAIL_T / 2.0
    return [bp(bank, 0.0, m, h)[1:]
            for m, h in ((m0, h0), (m1, h0), (m1, h1), (m0, h1))]


def build_fuel(bank: int, sectioned: bool = True):
    out = []
    rail = prism(_rail_pts(bank), *RAIL_X, r=2.5)
    dax0 = bp(bank, DAMPER_X[0], RAIL_M, RAIL_H)
    dax1 = bp(bank, DAMPER_X[1], RAIL_M, RAIL_H)
    damper = geo.cyl_along(dax0, dax1, DAMPER_D)
    damper = fuse_all([damper, bd.Sphere(DAMPER_D / 2.0).moved(bd.Location(dax1))])
    bores = [geo.cyl_along(bp(bank, RAIL_X[0] - 46.0, RAIL_M, RAIL_H),
                           bp(bank, RAIL_X[1] + 8.0, RAIL_M, RAIL_H), 11.0),
             geo.cyl_along(bp(bank, FEED_X, RAIL_M, RAIL_H),
                           bp(bank, FEED_X, RAIL_M, RAIL_H + 20.0), 11.0)]
    for c in S.CYLINDERS:
        if c.bank == bank:
            bores.append(geo.cyl_along(_inj(bank, c.x, -0.30), _inj(bank, c.x, 0.22),
                                       INJ_D + 0.4))
    rail = cut_all(fuse_all([rail, damper]), bores)
    rail = geo.sectioned(rail, bank, sectioned)
    if rail.solids():
        out.append(P.style(rail, f"fuel_rail:{bank}", P.MACHINED))

    # -AN feed spigot standing off the rail's top face, clear of the brackets
    seat = bp(bank, FEED_X, RAIL_M, RAIL_H + RAIL_T / 2.0)
    if not geo.in_section_void(seat, bank, sectioned):
        body_proto, nut_proto = _an_fitting(11.0)
        ax = S.bank_up(bank)
        out.append(P.style(F.place(body_proto, seat, ax, (1.0, 0.0, 0.0)),
                           f"fuel_rail_fitting:{bank}", P.MACHINED))
        out.append(P.style(F.place(nut_proto, seat, ax, (1.0, 0.0, 0.0)),
                           f"fuel_rail_fitting_nut:{bank}", P.RED_ANODISE))

    # stand-offs down to the head-face flange plate
    foot = [bp(bank, 0.0, m, h)[1:]
            for m, h in ((144.0, 329.0), (158.0, 329.0), (158.0, 345.0), (144.0, 345.0))]
    arm = [bp(bank, 0.0, m, h)[1:]
           for m, h in ((150.0, 340.0), (168.0, 340.0), (168.0, 352.0), (150.0, 352.0))]
    cap = F.socket_cap_bolt(6.0, 16.0)
    for i, x in enumerate(BRACKET_X):
        seat = bp(bank, x, 158.0, 337.0)
        if geo.in_section_void(seat, bank, sectioned):
            continue
        br = fuse_all([prism(foot, x - BRACKET_T / 2.0, x + BRACKET_T / 2.0, 2.0),
                       prism(arm, x - BRACKET_T / 2.0, x + BRACKET_T / 2.0, 2.0)])
        br = cut_all(br, [geo.cyl_along(bp(bank, x, 140.0, 337.0),
                                        bp(bank, x, 162.0, 337.0), 6.6)])
        out.append(P.style(br, f"fuel_rail_bracket:{bank}_{i + 1}", P.MACHINED))
        out.append(P.style(F.place(cap, seat, S.bank_m(bank), (1.0, 0.0, 0.0)),
                           f"fuel_rail_bracket_bolt:{bank}_{i + 1}", P.TITANIUM))

    # injectors
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        p0, p1 = _inj(bank, c.x, 0.10), _inj(bank, c.x, 0.82)
        p2 = _inj(bank, c.x, 1.02)
        if geo.in_section_void(p0, bank, sectioned):
            continue
        body = fuse_all([geo.cyl_along(p0, p1, INJ_D),
                         geo.cyl_along(p1, p2, INJ_TIP_D),
                         geo.cyl_along(_inj(bank, c.x, 0.16), _inj(bank, c.x, 0.30),
                                       INJ_D + 5.0)])
        conn = bd.Box(13.0, 11.0, 15.0)
        cseat = _inj(bank, c.x, 0.28)
        conn = F.place(conn, (cseat[0] + 14.0, cseat[1], cseat[2]), (1.0, 0.0, 0.0),
                       (0.0, 0.0, 1.0))
        out.append(P.style(body, f"injector:{c.number}", P.MACHINED_STEEL))
        out.append(P.style(conn, f"injector_connector:{c.number}", P.COMPOSITE))
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build(sectioned: bool = True):
    parts = []
    cap6 = F.socket_cap_bolt(6.0, 8.0)
    for bank in (1, 2):
        parts += build_plenum(bank, sectioned)
        parts += build_flange_plate(bank, sectioned, cap6)
        parts += build_intercooler(bank, sectioned)
        parts += build_intercooler_lid(bank, sectioned)
        parts += build_intercooler_furniture(bank, sectioned)
        parts += build_throttle(bank)
        for part in build_charge_pipes(bank):
            # bank-1 charge pipes cross the museum void in front of the section:
            # cut them like every other bank-1 static (the compressor they came
            # from is cut too), dropping pieces that vanish entirely
            if sectioned and bank == S.SECTION_BANK:
                cut = geo.sectioned(part, bank, True)
                if not cut.solids() or cut.volume < 1.0:
                    continue
                cut.label, cut.color = part.label, part.color
                if getattr(part, "cad_material", None) is not None:
                    cut.cad_material = dict(part.cad_material)
                part = cut
            parts.append(part)
        parts += build_fuel(bank, sectioned)
    bad = [p.label for p in parts if not is_sound(p)]
    if bad:
        raise AssertionError(f"induction: unsound solids {bad}")
    labels = [p.label for p in parts]
    assert len(set(labels)) == len(labels), "induction: duplicate labels"
    return parts


if __name__ == "__main__":
    import time
    t = time.time()
    ps = build(True)
    bb = [p.bounding_box() for p in ps]
    print(f"{len(ps)} solids in {time.time() - t:.1f} s")
    print("x", round(min(b.min.X for b in bb), 1), round(max(b.max.X for b in bb), 1),
          "y", round(min(b.min.Y for b in bb), 1), round(max(b.max.Y for b in bb), 1),
          "z", round(min(b.min.Z for b in bb), 1), round(max(b.max.Z for b in bb), 1))
