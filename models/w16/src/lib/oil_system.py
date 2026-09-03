"""Dry-sump oil system (engine frame): pan, windage tray, pump stack, filter, lines.

Layout
  PAN         cast shallow dry-sump pan bolted to the block rail. Its machined
              rail face sits at SUMP_RAIL_Z - GASKET_T so the 3 mm gasket fills
              the joint and the pan itself stays entirely below SUMP_RAIL_Z.
              Two scavenge pockets (front/rear) hang below the floor on the
              bank-2 half and carry two -AN outlets each.
  TRAY        formed-steel windage tray / scraper inside the crankcase. Its
              trough is an arc of radius TRAY_ARC_R about the crank axis, so
              every point of it is outside COUNTERWEIGHT_R + 6 and below z=-20.
  PUMP        five-section machined scavenge/pressure stack on the bank-2 skirt
              at spec.OIL_PUMP_CENTRE, four through-studs, cast bracket, HTD
              belt drive off the crank nose.
  FILTER      cast housing + cooler adapter + spin-on canister on the bank-1
              skirt, axis along +Y.
  LINES       four braided scavenge hoses (pan -> pump) and one pressure hose
              (pump -> filter), constant-radius bends, P-clipped to the pan.

Nothing here lies in the museum-section void (everything is below z = -10), so
`sectioned` changes no geometry; it is accepted for interface symmetry.

Self-test:  cd src && ../../../.venv/bin/python -m lib.oil_system
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C, fasteners as F, geo, palette as P, spec as S
from lib import block as _blk

# ---------------------------------------------------------------------------
# Shared numbers
# ---------------------------------------------------------------------------

GASKET_T = 3.0
PAN_TOP_Z = S.SUMP_RAIL_Z - GASKET_T          # -98: pan rail face
PAN_FLANGE_T = 12.0                           # flange thickness
PAN_FLANGE_W = 14.0                           # flange width in plan
PAN_BODY_TOP_Z = PAN_TOP_Z - PAN_FLANGE_T     # -110
PAN_BOT_Z = PAN_TOP_Z - S.SUMP_DEPTH          # -153
PAN_X0, PAN_X1 = -314.0, 302.0
PAN_Y_HALF = 165.0
PAN_R = 26.0
PAN_DRAFT = 3.0
PAN_WALL = 6.0
BOLT_PITCH = 60.0

POCKET_X = {"front": 205.0, "rear": -215.0}
POCKET_Y = -86.0
POCKET_W, POCKET_H = 120.0, 92.0              # x, y in plan
POCKET_DROP = 22.0
POCKET_R = 16.0

# pan -AN scavenge outlets on the -Y wall
OUTLET_Z = -120.0
OUTLET_X = [235.0, 175.0, -185.0, -245.0]

# windage tray
TRAY_T = 3.0
TRAY_ARC_R = 90.0                             # > COUNTERWEIGHT_R + 6
TRAY_ARC_Y = 78.0                             # arc runs out to |y| = 78
TRAY_FLANGE_Y = 146.0
TRAY_FLANGE_Z = -65.5
TRAY_X0, TRAY_X1 = -300.0, 290.0
TRAY_BOLT_Y = 146.0
# The tray no longer bolts to the crankcase wall (its flange bedded into the
# skirt); TRAY_BOLT_X stays as the interface block.py reads, now empty so the
# block drills no orphan tappings for it.
TRAY_BOLT_X = []
# Tabs bolt to the SIDE of each main cap instead. Main 1 runs in the block's
# front wall and has no separate cap, so the capped stations are MAIN_X[1:].
TRAY_CAP_X = list(S.MAIN_X[1:])
TRAY_CAP_Y = 58.0          # main-cap side face (bottom_end: cap_w = 116)
TRAY_CAP_Z = -34.0         # above the cap's r4 bottom-edge fillet
TRAY_TAB_W = 16.0          # along X: inside the cap's own 20 mm slab

# pump stack
PUMP_C = S.OIL_PUMP_CENTRE                    # (250, -240, -40)
PUMP_X0 = PUMP_C[0] - S.OIL_PUMP_LEN / 2.0    # 180
PUMP_X1 = PUMP_C[0] + S.OIL_PUMP_LEN / 2.0    # 320
PUMP_SEC = S.OIL_PUMP_LEN / 5.0               # 28
PUMP_W, PUMP_H = 62.0, 70.0                   # y, z of a section
PUMP_SEC_R = 14.0
PUMP_BOT_Z = PUMP_C[2] - PUMP_H / 2.0         # -75
PUMP_TOP_Z = PUMP_C[2] + PUMP_H / 2.0         # -5
PUMP_IN_Y = PUMP_C[1] + PUMP_W / 2.0          # -209 (inboard face)
PUMP_OUT_Y = PUMP_C[1] - PUMP_W / 2.0         # -271

# belt drive
BELT_X0, BELT_X1 = 392.0, 412.0
PULLEY_X0, PULLEY_X1 = 390.0, 414.0
PUMP_PULLEY_D = 90.0
CRANK_PULLEY_D = 72.0
CRANK_HUB_D = 46.0
BELT_T = 2.0

# filter
FILTER_X = -120.0                             # aft of the section plane and of the bank-1 engine mount (x +/-46); was 200, in front of the opened crankcase
FILTER_Z = -48.0
FILTER_CAN_D = 95.0
FILTER_CAN_Y = (228.0, 322.0)                # shorter spin-on: the turbos now sit 45 lower and their housings reach |y| 343

HOSE_D = 14.0

# block skirt outer face, taken from block.section_outline(): the straight run
# from (|y|=165, z=-95) up to the jacket corner near (|y|=198.7, z=21.9).
SKIRT_Y0, SKIRT_Z0 = 165.0, -95.0
SKIRT_SLOPE = 0.28815                          # d|y| / dz


def skirt_y(z: float) -> float:
    """|y| of the block skirt face at height z."""
    return SKIRT_Y0 + SKIRT_SLOPE * (z - SKIRT_Z0)


def skirt_normal(bank: int):
    """Outward unit normal of the skirt face (points out and slightly down)."""
    s = math.hypot(1.0, SKIRT_SLOPE)
    ny, nz = 1.0 / s, -SKIRT_SLOPE / s
    return (0.0, S.sign_of_bank(bank) * ny, nz)


def skirt_slope_dir(bank: int):
    """Unit vector up the skirt face (toward the deck)."""
    s = math.hypot(1.0, SKIRT_SLOPE)
    return (0.0, S.sign_of_bank(bank) * SKIRT_SLOPE / s, 1.0 / s)


def skirt_point(bank: int, x: float, z: float):
    return (x, S.sign_of_bank(bank) * skirt_y(z), z)


_BLOCK_TRIM = {}


def block_trim(sectioned: bool = True):
    """Everything of the block that our skirt castings could bed into.

    NOT `block.build_block()`: subtracting that 100k-face casting from a thin
    bracket is pathological for OCC (it ran for tens of minutes here). This is
    the same geometry where it matters, assembled from the block's own
    envelope and its own proud lower-skirt features, so the positions cannot
    drift: the section prism, the bulkhead ribs, the rail rib, the cross-bolt
    bosses and the parting bead. Cheap solids, exact placement.
    """
    key = bool(sectioned)
    if key in _BLOCK_TRIM:
        return _BLOCK_TRIM[key]
    envelope = geo.prism_yz(_blk.section_outline(), S.BLOCK_REAR_X, S.BLOCK_FRONT_X)
    pieces = [envelope]
    pieces += _blk._bulkhead_ribs()
    pieces += _blk._rail_rib()
    pieces += _blk._cross_bosses()
    # parting bead: a 1.4 mm band 0.6 proud of the skirt at PARTING_Z
    d1, c1, _b = _blk._corners()
    up = _blk._unit2((c1[0] - d1[0], c1[1] - d1[1]))
    t = (_blk.PARTING_Z - d1[1]) / up[1]
    q0 = (d1[0] + (t - 0.7) * up[0], d1[1] + (t - 0.7) * up[1])
    q1 = (d1[0] + (t + 0.7) * up[0], d1[1] + (t + 0.7) * up[1])
    bead = _blk._band(q0, q1, _blk.SKIRT_SLOPE_N, 6.0, 0.6)
    pieces += [_blk._prism(bead, S.BLOCK_REAR_X, S.BLOCK_FRONT_X, sy) for sy in (1, -1)]
    trim = C.fuse_all(pieces)
    _BLOCK_TRIM[key] = trim
    return trim


def _skirt_halfspace(bank: int, z_ref: float = -45.0):
    """A big box filling the inboard side of the skirt plane, used to trim
    anything cast onto the skirt back to the block face."""
    p = skirt_point(bank, 0.0, z_ref)
    box = bd.Box(900.0, 900.0, 900.0,
                 align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
    return geo.locate(box, p, skirt_normal(bank), (1, 0, 0))


# ---------------------------------------------------------------------------
# Small shared shape helpers
# ---------------------------------------------------------------------------

def _hex_prism(af: float, h: float, rotation: float = 0.0):
    """Hex bar across-flats `af`, base at z=0, `h` tall, +Z up."""
    sk = bd.RegularPolygon(af / 2.0, 6, major_radius=False, rotation=rotation)
    return bd.extrude(sk, amount=h)


def _rev(points, arc: float = 360.0):
    """Revolve a (r, z) profile about +Z."""
    pts = [(float(r), float(z)) for r, z in points]
    face = bd.make_face(bd.Polyline(*pts, close=True).edges())
    return bd.revolve(bd.Plane.XZ * face, bd.Axis.Z, arc)


def an_fitting(hex_af: float = 24.0, tail_l: float = 16.0, bore: float = 14.4,
               hex_l: float = 12.0):
    """A -AN hose end: wrench hex on the port face, beaded hose tail beyond.

    Local frame: z=0 on the port face, +Z along the hose, away from the port.
    """
    body = _hex_prism(hex_af, hex_l)
    tail_d = bore + 5.4
    prof = [(0.0, hex_l - 0.4)]
    z = hex_l - 0.4
    prof.append((tail_d / 2.0, z))
    n_bead = 3
    step = tail_l / (n_bead + 0.6)
    for k in range(n_bead):
        z0 = hex_l + step * (k + 0.2)
        prof += [(tail_d / 2.0, z0),
                 (tail_d / 2.0 + 1.6, z0 + step * 0.30),
                 (tail_d / 2.0, z0 + step * 0.62)]
    z_end = hex_l + tail_l
    prof += [(tail_d / 2.0, z_end - 2.2), (bore / 2.0 + 0.45, z_end),
             (0.0, z_end)]
    tail = _rev(prof)
    bore_cut = bd.Pos(0, 0, -1.0) * bd.Cylinder(
        bore / 2.0, hex_l + tail_l + 2.0, align=(None, None, None))
    return C.cut_all(C.fuse_all([body, tail]), [bore_cut])


def hex_cap(af: float, h: float, boss_d: float):
    """A screwed-in plug/cap: shoulder + hex, base at z=0, +Z up."""
    sh = _rev([(0.0, 0.0), (boss_d / 2.0, 0.0), (boss_d / 2.0, 3.0),
               (boss_d / 2.0 - 1.0, 4.0), (0.0, 4.0)])
    return C.fuse_all([sh, bd.Pos(0, 0, 3.5) * _hex_prism(af, h)])


def _toothed_pulley(x0, x1, od, bore, teeth, centre_y, centre_z,
                    flange_over=8.0, lighten=None):
    """A flat HTD pulley on the X axis: rim, retaining flanges, cut teeth."""
    r = od / 2.0
    w = x1 - x0
    body = geo.cyl_x(x0 + 2.0, x1 - 2.0, od, centre_y, centre_z)
    fl = [geo.cyl_x(x0, x0 + 2.0, od + flange_over, centre_y, centre_z),
          geo.cyl_x(x1 - 2.0, x1, od + flange_over, centre_y, centre_z)]
    web = geo.cyl_x(x0, x1, od * 0.55, centre_y, centre_z)
    pulley = C.fuse_all([body] + fl + [web])
    cuts = [geo.cyl_x(x0 - 2.0, x1 + 2.0, bore, centre_y, centre_z)]
    # lightening ring between hub and rim
    if lighten:
        n_l, r_l, d_l = lighten
        for k in range(n_l):
            a = 2.0 * math.pi * k / n_l
            cuts.append(geo.cyl_x(x0 - 2.0, x1 + 2.0, d_l,
                                  centre_y + r_l * math.cos(a),
                                  centre_z + r_l * math.sin(a)))
    slot_x0, slot_x1 = x0 + 1.6, x1 - 1.6
    for k in range(teeth):
        a = 360.0 * k / teeth
        slot = bd.Box(slot_x1 - slot_x0, 3.6, 5.0,
                      align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
        slot = slot.moved(bd.Location(((slot_x0 + slot_x1) / 2.0, 0.0, r)))
        cuts.append(bd.Pos(0, centre_y, centre_z) * slot.rotate(bd.Axis.X, a))
    return C.cut_all(pulley, cuts)


# ---------------------------------------------------------------------------
# Swept tubing: straight runs + exact constant-radius bends
# ---------------------------------------------------------------------------

def tube(points, d: float, bend_r: float):
    """A tube of diameter `d` through `points` with constant `bend_r` bends.

    Straight runs are cylinders trimmed by the tangent length at each corner;
    corners are torus sectors, so every bend is a true constant-radius arc.
    """
    pts = [bd.Vector(*p) for p in points]
    n = len(pts)
    dirs = [(pts[i + 1] - pts[i]).normalized() for i in range(n - 1)]
    trims = [0.0] * n
    angs = [0.0] * n
    for i in range(1, n - 1):
        u, v = dirs[i - 1], dirs[i]
        ang = math.acos(max(-1.0, min(1.0, u.dot(v))))
        angs[i] = ang
        trims[i] = bend_r * math.tan(ang / 2.0) if ang > 1e-9 else 0.0
    pieces = []
    for i in range(n - 1):
        a = pts[i] + dirs[i] * trims[i]
        b = pts[i + 1] - dirs[i] * trims[i + 1]
        if (b - a).length > 1e-4:
            pieces.append(geo.cyl_along((a.X, a.Y, a.Z), (b.X, b.Y, b.Z), d))
    for i in range(1, n - 1):
        if angs[i] < 1e-9:
            continue
        u, v = dirs[i - 1], dirs[i]
        start = pts[i] - u * trims[i]
        nv = (v - u * u.dot(v)).normalized()
        centre = start + nv * bend_r
        zdir = u.cross(nv)
        pl = bd.Plane(origin=centre, x_dir=-nv, z_dir=zdir)
        pieces.append(pl * bd.Torus(bend_r, d / 2.0,
                                    major_angle=math.degrees(angs[i]),
                                    align=(None, None, None)))
    return C.fuse_all(pieces)


def _p_clip(boss_pt, normal, hose_pt, hose_axis, d: float):
    """A stand-off line clip: foot plate on a cast boss, strap, band.

    Returns `(clip_solid, bolt_seat_point)`; the bolt is seated by the caller
    beside the strap so the head never buries itself in the bracket.
    """
    b = bd.Vector(*boss_pt)
    n = bd.Vector(*normal).normalized()
    lat = bd.Vector(*hose_axis).normalized()
    h = bd.Vector(*hose_pt)
    foot = geo.locate(bd.Box(26.0, 15.0, 3.5,
                             align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                      (b.X, b.Y, b.Z), (n.X, n.Y, n.Z), (lat.X, lat.Y, lat.Z))
    root = b + n * 3.5 - lat * 7.0
    v = h - root
    strap = geo.locate(bd.Box(10.0, 3.5, v.length,
                              align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                       (root.X, root.Y, root.Z), (v.X, v.Y, v.Z))
    a0 = h - lat * 4.5
    a1 = h + lat * 4.5
    band = (geo.cyl_along((a0.X, a0.Y, a0.Z), (a1.X, a1.Y, a1.Z), d + 8.0)
            - geo.cyl_along((a0.X - lat.X * 2, a0.Y - lat.Y * 2, a0.Z - lat.Z * 2),
                            (a1.X + lat.X * 2, a1.Y + lat.Y * 2, a1.Z + lat.Z * 2), d + 0.6))
    seat = b + n * 3.5 + lat * 8.0
    return C.fuse_all([foot, strap, band]), (seat.X, seat.Y, seat.Z)


# ---------------------------------------------------------------------------
# 1. Dry-sump pan
# ---------------------------------------------------------------------------

def _plan(w, h, r, cz, flip=False):
    """A rounded-rectangle sketch on a horizontal plane at z=cz, centred on the
    pan's plan centre. `flip` points the plane normal at -Z (draft downward)."""
    cx = (PAN_X0 + PAN_X1) / 2.0
    zdir = (0, 0, -1) if flip else (0, 0, 1)
    pl = bd.Plane(origin=(cx, 0.0, cz), x_dir=(1, 0, 0), z_dir=zdir)
    return pl * bd.RectangleRounded(w, h, r)


def _perimeter_points(w, h, r, pitch):
    """Points at even `pitch` around a rounded rectangle in the pan's plan,
    returned as engine (x, y). The pitch is trimmed so the ring closes."""
    cx = (PAN_X0 + PAN_X1) / 2.0
    hw, hh = w / 2.0 - r, h / 2.0 - r
    segs = []

    def straight(p0, p1):
        L = math.dist(p0, p1)
        segs.append((L, lambda t, p0=p0, p1=p1, L=L:
                     (p0[0] + (p1[0] - p0[0]) * t / L,
                      p0[1] + (p1[1] - p0[1]) * t / L)))

    def arc(c, a0, a1):
        L = r * math.radians(a1 - a0)
        segs.append((L, lambda t, c=c, a0=a0, L=L:
                     (c[0] + r * math.cos(math.radians(a0) + t / r),
                      c[1] + r * math.sin(math.radians(a0) + t / r))))

    straight((hw + r, -hh), (hw + r, hh))
    arc((hw, hh), 0, 90)
    straight((hw, hh + r), (-hw, hh + r))
    arc((-hw, hh), 90, 180)
    straight((-hw - r, hh), (-hw - r, -hh))
    arc((-hw, -hh), 180, 270)
    straight((-hw, -hh - r), (hw, -hh - r))
    arc((hw, -hh), 270, 360)

    total = sum(s[0] for s in segs)
    n = max(4, int(round(total / pitch)))
    step = total / n
    out = []
    for i in range(n):
        s = i * step
        for L, fn in segs:
            if s <= L + 1e-9:
                p = fn(min(s, L))
                out.append((cx + p[0], p[1]))
                break
            s -= L
    return out


def _pan_bolt_points():
    return S.pan_bolt_points()


CLIP_BOSS = [  # (x, z) of the scavenge P-clip bosses on the pan's -Y wall
    (268.0, -146.0), (238.0, -146.0),
    (208.0, -146.0), (178.0, -146.0),
    (60.0, -146.0), (-120.0, -146.0),
    (0.0, -146.0), (-180.0, -146.0),
]
PRESS_CLIP = [(276.0, -95.0), (276.0, 95.0)]   # (x, y) on the pan floor


def _near_edges(part, points, tol=9.0):
    """Edges whose bbox centre sits within `tol` of one of `points`."""
    out = []
    for e in part.edges():
        c = C.edge_center(e)
        for p in points:
            if (c - bd.Vector(*p)).length <= tol:
                out.append(e)
                break
    return out


def _wall_y(z):
    """|y| of the pan's drafted outer wall at height z (bank-2 side is -this)."""
    return (2 * PAN_Y_HALF - 2 * PAN_FLANGE_W) / 2.0 - (PAN_BODY_TOP_Z + 4.0 - z) * math.tan(
        math.radians(PAN_DRAFT))


RIBS = [(0.0, -286.0, 560.0), (62.0, -286.0, 560.0), (124.0, -286.0, 560.0),
        (-62.0, -145.0, 280.0), (-124.0, -145.0, 280.0)]


def build_pan(sectioned: bool = True):
    parts = []
    w_out, h_out = PAN_X1 - PAN_X0, 2 * PAN_Y_HALF
    w_body, h_body = w_out - 2 * PAN_FLANGE_W, h_out - 2 * PAN_FLANGE_W
    w_cav, h_cav = w_body - 2 * PAN_WALL, h_body - 2 * PAN_WALL
    drain_z = PAN_BOT_Z - POCKET_DROP
    body_top = PAN_BODY_TOP_Z + 4.0            # 4 mm into the flange: no coplanar joints

    # --- smooth cast shell: flange, drafted trough, two scavenge pockets -----
    shell = [bd.extrude(_plan(w_out, h_out, PAN_R, PAN_TOP_Z), amount=-PAN_FLANGE_T),
             C.drafted_prism(_plan(w_body, h_body, PAN_R - 6.0, body_top, flip=True),
                             body_top - PAN_BOT_Z, PAN_DRAFT)]
    for px in POCKET_X.values():
        pl = bd.Plane(origin=(px, POCKET_Y, PAN_BOT_Z + 4.0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
        shell.append(C.drafted_prism(pl * bd.RectangleRounded(POCKET_W, POCKET_H, POCKET_R),
                                     POCKET_DROP + 4.0, PAN_DRAFT))
    pan = C.fuse_all(shell)
    pan, _ = C.soften(pan, 8.0,
                      exclude=lambda e: e.bounding_box().max.Z > PAN_TOP_Z - 0.5,
                      min_r=1.5)

    # --- cast-in detail: floor ribs, outlet and clip bosses, drain boss ------
    detail = []
    for ry, rx0, rl in RIBS:
        rr = C.rib(rl, 12.0, 11.0, draft_deg=5.0, end_r=4.0, top_r=3.0)
        detail.append(bd.Pos(rx0, ry, PAN_BOT_Z + 4.0) * (bd.Rot(180, 0, 0) * rr))
    for ox in OUTLET_X:
        detail.append(geo.cyl_along((ox, -138.0, OUTLET_Z), (ox, -166.0, OUTLET_Z), 32.0))
    for bx, bz in CLIP_BOSS:
        detail.append(geo.cyl_along((bx, -140.0, bz), (bx, -160.0, bz), 20.0))
    for px, py in PRESS_CLIP:
        detail.append(geo.cyl_along((px, py, PAN_BOT_Z + 4.0), (px, py, PAN_BOT_Z - 10.0), 20.0))
    detail.append(geo.cyl_along((POCKET_X["rear"], POCKET_Y, drain_z + 5.0),
                                (POCKET_X["rear"], POCKET_Y, drain_z - 7.0), 36.0))
    pan = C.fuse_all([pan] + detail)

    # root blends, selected geometrically (a blanket fillet_all on this body
    # walks into OCC's sliver-face crash)
    roots = C.edges_at(pan, z=PAN_BOT_Z)
    roots += _near_edges(pan, [(ox, -_wall_y(OUTLET_Z), OUTLET_Z) for ox in OUTLET_X], tol=9.0)
    roots += _near_edges(pan, [(bx, -_wall_y(bz), bz) for bx, bz in CLIP_BOSS], tol=7.0)
    roots += _near_edges(pan, [(px, py, PAN_BOT_Z) for px, py in PRESS_CLIP], tol=7.0)
    pan, _ = C.safe_fillet(pan, roots, 3.5, min_r=0.8)

    # --- cavity -------------------------------------------------------------
    cav = [C.drafted_prism(_plan(w_cav, h_cav, PAN_R - 12.0, PAN_TOP_Z + 4.0, flip=True),
                           PAN_TOP_Z + 4.0 - (PAN_BOT_Z + PAN_WALL), PAN_DRAFT)]
    for px in POCKET_X.values():
        pl = bd.Plane(origin=(px, POCKET_Y, PAN_BOT_Z + 2.0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
        cav.append(C.drafted_prism(pl * bd.RectangleRounded(POCKET_W - 2 * PAN_WALL,
                                                            POCKET_H - 2 * PAN_WALL,
                                                            POCKET_R - 4.0),
                                   POCKET_DROP - PAN_WALL + 2.0, PAN_DRAFT))
    pan = C.cut_all(pan, [C.fuse_all(cav)])

    # bores: outlets, clip-boss tappings, bolt holes, drain
    cuts = []
    for ox in OUTLET_X:
        cuts.append(geo.cyl_along((ox, -110.0, OUTLET_Z), (ox, -170.0, OUTLET_Z), 18.0))
    for bx, bz in CLIP_BOSS:
        cuts.append(geo.cyl_along((bx, -152.0, bz), (bx, -168.0, bz), 6.6))
    for px, py in PRESS_CLIP:
        cuts.append(geo.cyl_along((px, py, PAN_BOT_Z - 4.0), (px, py, PAN_BOT_Z - 16.0), 6.6))
    bolt_pts = _pan_bolt_points()
    for bx, by in bolt_pts:
        cuts.append(geo.cyl_along((bx, by, PAN_TOP_Z + 2.0), (bx, by, PAN_BODY_TOP_Z - 2.0), 9.0))
    cuts.append(geo.cyl_along((POCKET_X["rear"], POCKET_Y, drain_z + 8.0),
                              (POCKET_X["rear"], POCKET_Y, drain_z - 9.0), 13.0))
    pan = C.cut_all(pan, cuts)

    # machined rail face + parting line along the flange
    rail_plane = bd.Plane(origin=(0, 0, PAN_TOP_Z), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    pan = C.machined_face(pan, rail_plane)
    pan = C.parting_line(pan, bd.Plane(origin=(0, 0, PAN_BODY_TOP_Z),
                                       x_dir=(1, 0, 0), z_dir=(0, 0, 1)),
                         height=0.4, width=1.4)
    skin = C.machined_skin(pan, rail_plane, t=0.4)
    if skin is not None:
        pan = pan - skin
        parts.append(P.style(skin, "sump_pan_rail", P.MACHINED))
    parts.insert(0, P.style(pan, "sump_pan", P.CAST))

    # gasket
    g_out = bd.extrude(_plan(w_out, h_out, PAN_R, S.SUMP_RAIL_Z), amount=-GASKET_T)
    g_in = bd.extrude(_plan(w_body, h_body, PAN_R - 6.0, S.SUMP_RAIL_Z + 1.0), amount=-GASKET_T - 2.0)
    gasket = g_out - g_in
    gasket = C.cut_all(gasket, [geo.cyl_along((bx, by, S.SUMP_RAIL_Z + 2.0),
                                              (bx, by, PAN_TOP_Z - 2.0), 9.0)
                                for bx, by in bolt_pts])
    parts.append(P.style(gasket, "sump_gasket", P.GASKET))

    # perimeter bolts: head under the flange, shank up into the block
    # 22 mm: a 26 mm shank at the front-wall station nearest y=0 pokes to
    # r = 85.3 about the crank axis, inside the 86 mm static-clearance rule.
    proto = F.hex_flange_bolt(8.0, 22.0)
    for i, (bx, by) in enumerate(bolt_pts, start=1):
        parts.append(P.style(F.place(proto, (bx, by, PAN_BODY_TOP_Z), (0, 0, -1)),
                             f"sump_bolt:{i}", P.TITANIUM))

    # drain plug + copper crush washer
    wsh = F.washer(14.0)
    parts.append(P.style(F.place(wsh, (POCKET_X["rear"], POCKET_Y, drain_z - 7.0), (0, 0, -1)),
                         "sump_drain_washer", P.COPPER))
    plug = F.hex_flange_bolt(14.0, 18.0)
    parts.append(P.style(F.place(plug, (POCKET_X["rear"], POCKET_Y, drain_z - 9.5), (0, 0, -1)),
                         "sump_drain_plug", P.STEEL_DARK))

    # pan-end -AN fittings
    fit = an_fitting(**PAN_FIT)
    for i, ox in enumerate(OUTLET_X, start=1):
        parts.append(P.style(F.place(fit, (ox, -166.0, OUTLET_Z), (0, -1, 0)),
                             f"scavenge_fitting:pan_{i}", P.MACHINED_STEEL))
    return parts


# ---------------------------------------------------------------------------
# 2. Windage tray / scraper
# ---------------------------------------------------------------------------

def _tray_centreline():
    """Half-section (y, z) of the tray sheet centreline, y >= 0, outward."""
    pts = []
    n = 14
    a_end = math.asin(TRAY_ARC_Y / TRAY_ARC_R)
    for k in range(n + 1):
        a = a_end * k / n
        pts.append((TRAY_ARC_R * math.sin(a), -TRAY_ARC_R * math.cos(a)))
    pts.append((140.0, TRAY_FLANGE_Z))
    pts.append((TRAY_FLANGE_Y, TRAY_FLANGE_Z))
    return pts


TAB_ROOT_Y = 96.0          # where the tab picks the tray's outer straight run


def _tray_run_z(y_abs: float) -> float:
    """z of the tray sheet centreline on its outer straight run at |y|."""
    y0, z0 = TRAY_ARC_Y, -math.sqrt(TRAY_ARC_R ** 2 - TRAY_ARC_Y ** 2)
    y1, z1 = 140.0, TRAY_FLANGE_Z
    return z0 + (z1 - z0) * (y_abs - y0) / (y1 - y0)


def _offset_polyline(pts, d):
    """Offset an open polyline by `d` along its left normal (2D)."""
    out = []
    n = len(pts)
    for i in range(n):
        if i == 0:
            seg = [(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])]
        elif i == n - 1:
            seg = [(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])]
        else:
            seg = [(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]),
                   (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])]
        nx = ny = 0.0
        for vx, vy in seg:
            L = math.hypot(vx, vy)
            nx += -vy / L
            ny += vx / L
        L = math.hypot(nx, ny)
        out.append((pts[i][0] + d * nx / L, pts[i][1] + d * ny / L))
    return out


def build_windage_tray(sectioned: bool = True):
    half = _tray_centreline()
    centre = [(-y, z) for y, z in reversed(half)][:-1] + half
    lower = _offset_polyline(centre, -TRAY_T / 2.0)
    upper = _offset_polyline(centre, TRAY_T / 2.0)
    poly = lower + list(reversed(upper))
    tray = geo.prism_yz(poly, TRAY_X0, TRAY_X1)
    # museum section: the tray's +y half in front of the opened crankcase goes with the block wall
    tray = geo.sectioned(tray, 1, sectioned)

    # louvres: through slots with a raised deflector lip, four radial bands
    slots, lips = [], []
    x_stations = [TRAY_X0 + 40.0 + k * (TRAY_X1 - TRAY_X0 - 80.0) / 4.0 for k in range(5)]
    for sy in (-1.0, 1.0):
        for band_y in (34.0, 60.0):
            a = math.asin(band_y / TRAY_ARC_R)
            py = sy * TRAY_ARC_R * math.sin(a)
            pz = -TRAY_ARC_R * math.cos(a)
            # radial unit vector at this station
            ry, rz = py / TRAY_ARC_R, pz / TRAY_ARC_R
            for xs in x_stations:
                slot = bd.Box(46.0, 7.0, 14.0,
                              align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
                slots.append(geo.locate(slot, (xs, py, pz), (0.0, ry, rz), (1, 0, 0)))
                lip = bd.Box(46.0, 3.0, 10.0,
                             align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
                lip = bd.Rot(22.0, 0, 0) * lip
                lips.append(geo.locate(lip, (xs, py + 1.5 * ry, pz + 1.5 * rz),
                                       (0.0, ry, rz), (1, 0, 0)))
    tray = C.cut_all(tray, slots)
    tray = C.fuse_all([tray] + lips)

    # Mounting tabs: a strut off the tray's outer run to a pad on the SIDE of
    # each main cap, one M8 inboard into the cap. The tabs live inside the
    # cap's own 20 mm slab, where no counterweight or crank web sweeps.
    tabs, seats = [], []
    for xm in TRAY_CAP_X:
        for sy in (1.0, -1.0):
            p0 = (xm, sy * TAB_ROOT_Y, _tray_run_z(TAB_ROOT_Y))
            p1 = (xm, sy * (TRAY_CAP_Y + 8.0), TRAY_CAP_Z)
            v = (0.0, p1[1] - p0[1], p1[2] - p0[2])
            L = math.hypot(v[1], v[2])
            # start 14 mm OUTBOARD of the sheet so the strut crosses it
            # cleanly instead of ending inside a 3 mm plate (knife edges there
            # make the fuse unsound)
            root = (xm, p0[1] - 14.0 * v[1] / L, p0[2] - 14.0 * v[2] / L)
            tabs.append(geo.locate(bd.Box(TRAY_TAB_W, 5.0, L + 14.0,
                                          align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                                   root, v, (1, 0, 0)))
            pad = bd.Box(TRAY_TAB_W, 9.0, 15.0,
                         align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
            tabs.append(pad.moved(bd.Location((xm, sy * (TRAY_CAP_Y + 4.0), TRAY_CAP_Z))))
            seats.append((xm, sy * (TRAY_CAP_Y + 8.0), TRAY_CAP_Z, sy))
    tray = C.fuse_all([tray] + tabs)
    tray = C.cut_all(tray, [geo.cyl_along((x, sy * 50.0, z), (x, sy * 74.0, z), 8.6)
                            for x, y, z, sy in seats])
    tray, _ = C.safe_fillet(tray, [e for e in tray.edges()
                                   if abs(e.bounding_box().center().X - TRAY_X0) < 1e-6
                                   or abs(e.bounding_box().center().X - TRAY_X1) < 1e-6],
                            1.2, min_r=0.4)
    # The tray needs no block trim: its flange stops at |y| = 146 inside the
    # crankcase wall (interior half-width 150.5 at this height) and the tabs
    # live in the void under each main cap. Cutting a 3 mm sheet with the
    # fused block trim only ever came back unsound, so it is not attempted;
    # the common-volume check below is what proves the clearance.
    parts = [P.style(tray, "windage_tray", P.STEEL_DARK)]
    bolt = F.socket_cap_bolt(8.0, 26.0)
    for k, xm in enumerate(TRAY_CAP_X, start=2):
        for sy, tag in ((1.0, "b1"), (-1.0, "b2")):
            parts.append(P.style(
                F.place(bolt, (xm, sy * (TRAY_CAP_Y + 8.0), TRAY_CAP_Z), (0, sy, 0)),
                f"windage_bolt:{k}_{tag}", P.TITANIUM))
    return parts


# ---------------------------------------------------------------------------
# 3. Scavenge / pressure pump stack + belt drive
# ---------------------------------------------------------------------------

SCAVENGE = [  # (pan outlet x, run y, run z, pump inlet x, pump inlet y)
    (235.0, -202.0, -158.0, 278.0, -234.0),
    (175.0, -226.0, -158.0, 250.0, -256.0),
    (-185.0, -202.0, -182.0, 222.0, -234.0),
    (-245.0, -226.0, -182.0, 194.0, -256.0),
]
HOSE_BEND = 15.0
PAN_FIT = dict(hex_af=26.0, tail_l=11.0, bore=HOSE_D + 0.3, hex_l=10.0)
PRESS_OUT = (316.0, PUMP_C[1], PUMP_BOT_Z)
FILTER_IN = (FILTER_X, 190.0, FILTER_Z - 50.0)


def build_pump(sectioned: bool = True):
    parts = []
    # five machined sections with a chamfered split line at every joint
    proto = bd.extrude(bd.RectangleRounded(PUMP_W, PUMP_H, PUMP_SEC_R), amount=PUMP_SEC)
    proto, _ = C.safe_chamfer(proto, C.edges_at(proto, z=0.0) + C.edges_at(proto, z=PUMP_SEC),
                              1.2, min_length=0.4)
    names = ["scavenge_4", "scavenge_3", "scavenge_2", "scavenge_1", "pressure"]
    bodies = []
    for k in range(5):
        x0 = PUMP_X0 + k * PUMP_SEC
        bodies.append(geo.locate(proto, (x0, PUMP_C[1], PUMP_C[2]), (1, 0, 0), (0, 1, 0)))

    # front (pressure) section gets the relief-valve boss and the drive nose
    relief = geo.cyl_along((306.0, PUMP_OUT_Y + 6.0, PUMP_C[2]),
                           (306.0, PUMP_OUT_Y - 22.0, PUMP_C[2]), 44.0)
    nose = C.fuse_all([geo.cyl_x(PUMP_X1 - 6.0, 382.0, 46.0, PUMP_C[1], PUMP_C[2]),
                       geo.cyl_x(PUMP_X1 - 10.0, PUMP_X1 + 4.0, 58.0, PUMP_C[1], PUMP_C[2])])
    front = C.fuse_all([bodies[4], relief, nose])
    front, _ = C.safe_fillet(front, [e for e in front.edges()
                                     if e.geom_type is not None
                                     and abs(e.bounding_box().center().X - PUMP_X1) < 0.6],
                             2.0, min_r=0.5)
    front = C.cut_all(front, [geo.cyl_x(PUMP_X1 - 20.0, 384.0, 26.0, PUMP_C[1], PUMP_C[2])])
    bodies[4] = front

    for k, b in enumerate(bodies):
        parts.append(P.style(b, f"oil_pump_section:{names[k]}", P.MACHINED))

    # four long through-studs and their nuts
    nut = F.hex_nut(10.0)
    for i, (dy, dz) in enumerate([(22.0, 26.0), (-22.0, 26.0), (22.0, -26.0), (-22.0, -26.0)],
                                 start=1):
        y, z = PUMP_C[1] + dy, PUMP_C[2] + dz
        parts.append(P.style(geo.cyl_x(PUMP_X0 - 10.0, PUMP_X1 + 10.0, 10.0, y, z),
                             f"oil_pump_stud:{i}", P.STEEL_DARK))
        parts.append(P.style(F.place(nut, (PUMP_X0, y, z), (-1, 0, 0)),
                             f"oil_pump_nut:{i}_rear", P.STEEL_DARK))
        parts.append(P.style(F.place(nut, (PUMP_X1, y, z), (1, 0, 0)),
                             f"oil_pump_nut:{i}_front", P.STEEL_DARK))

    parts.append(P.style(F.place(hex_cap(30.0, 12.0, 38.0),
                                 (306.0, PUMP_OUT_Y - 22.0, PUMP_C[2]), (0, -1, 0)),
                         "oil_pump_relief_cap", P.MACHINED_STEEL))

    # -AN inlets and the pressure outlet
    fit = an_fitting(hex_af=26.0, tail_l=16.0, bore=HOSE_D + 0.4, hex_l=11.0)
    for i, (_, _, _, ix, iy) in enumerate(SCAVENGE, start=1):
        parts.append(P.style(F.place(fit, (ix, iy, PUMP_BOT_Z), (0, 0, -1)),
                             f"scavenge_fitting:pump_{i}", P.MACHINED_STEEL))
    parts.append(P.style(F.place(fit, PRESS_OUT, (0, 0, -1)),
                         "pressure_fitting:pump", P.MACHINED_STEEL))

    # cast bracket to the block skirt
    n2 = skirt_normal(2)
    flange = geo.locate(bd.Box(128.0, 96.0, 14.0,
                               align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                        skirt_point(2, PUMP_C[0], -45.0), n2, (1, 0, 0))
    web = geo.prism_yz([(-skirt_y(-19.0), -19.0), (-skirt_y(-70.0), -70.0),
                        (PUMP_IN_Y, -70.0), (PUMP_IN_Y, -19.0)],
                       PUMP_C[0] - 58.0, PUMP_C[0] + 58.0)
    bracket = C.fuse_all([flange, web])
    bracket = C.cut_all(bracket, [_skirt_halfspace(2)])
    lighten = []
    for lx in (PUMP_C[0] - 38.0, PUMP_C[0], PUMP_C[0] + 38.0):
        lighten.append(geo.locate(bd.Box(26.0, 26.0, 120.0,
                                         align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER)),
                                  (lx, -200.0, -45.0), (0, -1, 0), (1, 0, 0)))
    bracket = C.cut_all(bracket, lighten)
    bracket, _ = C.soften(bracket, 4.0, min_r=0.8)
    bolt_pts = []
    for dx in (-50.0, 0.0, 50.0):
        p = skirt_point(2, PUMP_C[0] + dx, -45.0)
        bolt_pts.append((p[0] + 14.0 * n2[0], p[1] + 14.0 * n2[1], p[2] + 14.0 * n2[2]))
    bracket = C.cut_all(bracket, [geo.cyl_along(
        (p[0] - 20 * n2[0], p[1] - 20 * n2[1], p[2] - 20 * n2[2]),
        (p[0] + 4 * n2[0], p[1] + 4 * n2[1], p[2] + 4 * n2[2]), 11.0) for p in bolt_pts])
    # bear on the metal that is actually there: the skirt carries bulkhead ribs,
    # a rail rib and a parting bead proud of the nominal face
    bracket = C.cut_all(bracket, [block_trim(sectioned)])
    parts.append(P.style(bracket, "oil_pump_bracket", P.CAST))
    m10 = F.hex_flange_bolt(10.0, 34.0)
    for i, p in enumerate(bolt_pts, start=1):
        parts.append(P.style(F.place(m10, p, n2), f"oil_pump_bracket_bolt:{i}", P.TITANIUM))

    # drive: shaft, pump pulley, crank hub + pulley, belt
    parts.append(P.style(geo.cyl_x(PUMP_X1 - 24.0, BELT_X1, 24.0, PUMP_C[1], PUMP_C[2]),
                         "oil_pump_shaft", P.MACHINED_STEEL))
    parts.append(P.style(_toothed_pulley(PULLEY_X0, PULLEY_X1, PUMP_PULLEY_D, 24.4, 35,
                                         PUMP_C[1], PUMP_C[2], lighten=(5, 28.0, 16.0)),
                         "oil_pump_pulley", P.MACHINED_STEEL))

    # crank-nose adapter: bolts to the damper's ring face (x=370), reaches
    # forward over the damper washer and nose bolt to carry the drive pulley.
    hub = C.fuse_all([
        geo.cyl_x(370.0, 376.0, 168.0) - geo.cyl_x(368.0, 378.0, 80.0),
        geo.cyl_x(370.0, 392.0, 92.0) - geo.cyl_x(368.0, 394.0, 80.0),
        geo.cyl_x(386.0, 392.0, 92.0) - geo.cyl_x(384.0, 394.0, 38.0),
        geo.cyl_x(388.0, PULLEY_X1, CRANK_HUB_D) - geo.cyl_x(386.0, PULLEY_X1 + 2.0, 38.0),
    ])
    hub_r = 76.0
    hub = C.cut_all(hub, [geo.cyl_x(366.0, 378.0, 9.0,
                                    hub_r * math.cos(math.radians(60 * k)),
                                    hub_r * math.sin(math.radians(60 * k))) for k in range(6)]
                    + [geo.cyl_x(368.0, 378.0, 32.0,
                                 60.0 * math.cos(math.radians(60 * k + 30)),
                                 60.0 * math.sin(math.radians(60 * k + 30))) for k in range(6)])
    hub, _ = C.safe_fillet(hub, C.edges_at(hub, near=(376.0, 0.0, 0.0), tol=200.0,
                                           kind="CIRCLE"), 1.2, min_r=0.4)
    parts.append(P.style(hub, "crank_pulley_hub", P.MACHINED_STEEL))
    m8 = F.socket_cap_bolt(8.0, 22.0)
    for k in range(6):
        a = math.radians(60 * k)
        parts.append(P.style(F.place(m8, (376.0, hub_r * math.cos(a), hub_r * math.sin(a)), (1, 0, 0)),
                             f"crank_pulley_bolt:{k + 1}", P.TITANIUM))
    parts.append(P.style(_toothed_pulley(PULLEY_X0, PULLEY_X1, CRANK_PULLEY_D, CRANK_HUB_D, 28,
                                         0.0, 0.0),
                         "crank_oil_pulley", P.MACHINED_STEEL))

    def hull(c1, r1, c2, r2):
        """Face bounded by the two external tangents and the wrapped arcs."""
        dx, dy = c2[0] - c1[0], c2[1] - c1[1]
        d = math.hypot(dx, dy)
        al = math.degrees(math.atan2(dy, dx))
        be = math.degrees(math.acos(max(-1.0, min(1.0, (r1 - r2) / d))))
        a1, a2 = al + be, al - be

        def on(c, r, a):
            return (c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a)))

        edges = [bd.CenterArc(c1, r1, a1, 360.0 - 2 * be),
                 bd.Line(on(c1, r1, a2), on(c2, r2, a2)),
                 bd.CenterArc(c2, r2, a2, 2 * be),
                 bd.Line(on(c2, r2, a1), on(c1, r1, a1))]
        wire = bd.Wire([e for grp in edges for e in grp.edges()])
        return bd.make_face(wire)

    c_pump = (PUMP_C[1], PUMP_C[2])
    r_p, r_c = PUMP_PULLEY_D / 2.0, CRANK_PULLEY_D / 2.0
    band = hull(c_pump, r_p + BELT_T, (0.0, 0.0), r_c + BELT_T) - hull(c_pump, r_p, (0.0, 0.0), r_c)
    belt = bd.extrude(geo.yz_plane(BELT_X0) * band, amount=BELT_X1 - BELT_X0)
    parts.append(P.style(belt, "oil_drive_belt", P.BELT))
    return parts


# ---------------------------------------------------------------------------
# 4. Filter housing
# ---------------------------------------------------------------------------

def build_filter(sectioned: bool = True):
    parts = []
    n1 = skirt_normal(1)
    s1 = skirt_slope_dir(1)
    centre = skirt_point(1, FILTER_X, FILTER_Z)

    drum = geo.cyl_along((FILTER_X, 162.0, FILTER_Z), (FILTER_X, 212.0, FILTER_Z), 94.0)
    back = geo.locate(bd.Box(164.0, 96.0, 13.0,
                             align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                      centre, n1, (1, 0, 0))
    ears, ear_pts = [], []
    for dx in (-66.0, 66.0):
        for ds in (-36.0, 40.0):
            p = (centre[0] + dx, centre[1] + ds * s1[1], centre[2] + ds * s1[2])
            ear_pts.append((p[0] + 15.0 * n1[0], p[1] + 15.0 * n1[1], p[2] + 15.0 * n1[2]))
            ears.append(geo.locate(C.boss(30.0, 15.0, draft_deg=4.0, fillet_r=1.5), p, n1, (1, 0, 0)))
    housing = C.fuse_all([drum, back] + ears)
    below = bd.Box(1400.0, 1400.0, 700.0,
                   align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.MAX))
    housing = C.cut_all(housing, [_skirt_halfspace(1),
                                  below.moved(bd.Location((0.0, 168.0, -96.0)))])
    housing, _ = C.soften(housing, 5.0, min_r=0.8)
    housing = C.cut_all(housing, [geo.cyl_along(
        (p[0] - 30 * n1[0], p[1] - 30 * n1[1], p[2] - 30 * n1[2]),
        (p[0] + 4 * n1[0], p[1] + 4 * n1[1], p[2] + 4 * n1[2]), 11.0) for p in ear_pts]
        + [geo.cyl_along((FILTER_X, 200.0, FILTER_Z), (FILTER_X, 214.0, FILTER_Z), 40.0),
           geo.cyl_along((FILTER_X, 190.0, FILTER_Z - 40.0),
                         (FILTER_X, 190.0, FILTER_Z - 60.0), 18.0),
           geo.cyl_along((FILTER_X, 188.0, FILTER_Z + 40.0),
                         (FILTER_X, 188.0, FILTER_Z + 52.0), 16.0)])
    housing = C.cut_all(housing, [block_trim(sectioned)])
    parts.append(P.style(housing, "oil_filter_housing", P.CAST))

    m10 = F.hex_flange_bolt(10.0, 32.0)
    for i, p in enumerate(ear_pts, start=1):
        parts.append(P.style(F.place(m10, p, n1), f"oil_filter_bolt:{i}", P.TITANIUM))

    # oil-cooler sandwich adapter + spin-on mount flange
    ad = C.fuse_all([geo.cyl_along((FILTER_X, 212.0, FILTER_Z), (FILTER_X, 226.0, FILTER_Z), 112.0),
                     geo.cyl_along((FILTER_X, 226.0, FILTER_Z), (FILTER_X, 230.0, FILTER_Z), 88.0),
                     geo.cyl_along((FILTER_X - 34.0, 214.0, FILTER_Z + 44.0),
                                   (FILTER_X - 34.0, 214.0, FILTER_Z + 66.0), 34.0),
                     geo.cyl_along((FILTER_X + 34.0, 214.0, FILTER_Z + 44.0),
                                   (FILTER_X + 34.0, 214.0, FILTER_Z + 66.0), 34.0)])
    ad = C.cut_all(ad, [geo.cyl_along((FILTER_X, 208.0, FILTER_Z), (FILTER_X, 232.0, FILTER_Z), 34.0)])
    ad, _ = C.safe_fillet(ad, [e for e in ad.edges()
                               if abs(e.bounding_box().center().Y - 214.0) < 0.8], 2.0, min_r=0.5)
    parts.append(P.style(ad, "oil_cooler_adapter", P.MACHINED))

    for i, dx in enumerate((-34.0, 34.0), start=1):
        parts.append(P.style(F.place(an_fitting(hex_af=26.0, tail_l=14.0, bore=HOSE_D + 0.4, hex_l=11.0),
                                     (FILTER_X + dx, 214.0, FILTER_Z + 66.0), (0, 0, 1)),
                             f"oil_cooler_fitting:{i}", P.MACHINED_STEEL))

    # pressure sender on the housing
    sender = C.fuse_all([_hex_prism(22.0, 10.0), bd.Pos(0, 0, 9.0) * bd.Cylinder(9.0, 26.0, align=(None, None, None)),
                         bd.Pos(0, 0, 34.0) * bd.Cylinder(6.0, 5.0, align=(None, None, None))])
    parts.append(P.style(geo.locate(sender, (FILTER_X, 188.0, FILTER_Z + 45.0), (0, 0, 1)),
                         "oil_pressure_sender", P.STEEL_DARK))

    # spin-on canister with a knurled cap
    y0, y1 = FILTER_CAN_Y
    can = geo.cyl_along((FILTER_X, y0, FILTER_Z), (FILTER_X, y1 - 16.0, FILTER_Z), FILTER_CAN_D)
    cap = geo.cyl_along((FILTER_X, y1 - 18.0, FILTER_Z), (FILTER_X, y1, FILTER_Z), FILTER_CAN_D - 2.0)
    knurl = []
    for k in range(36):
        a = math.radians(360.0 * k / 36)
        sl = bd.Box(2.4, 3.0, 20.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
        sl = sl.moved(bd.Location((0.0, 0.0, FILTER_CAN_D / 2.0 - 1.0)))
        sl = sl.rotate(bd.Axis.X, math.degrees(a))
        knurl.append(geo.locate(sl, (FILTER_X, y1 - 9.0, FILTER_Z), (0, 1, 0), (1, 0, 0)))
    cap = C.cut_all(cap, knurl)
    can, _ = C.safe_fillet(can, [e for e in can.edges()
                                 if abs(e.bounding_box().center().Y - y0) < 0.6], 4.0, min_r=0.8)
    parts.append(P.style(can, "oil_filter_canister", P.OIL_FILTER))
    parts.append(P.style(cap, "oil_filter_cap", P.MACHINED_STEEL))
    return parts


# ---------------------------------------------------------------------------
# 5. Braided lines
# ---------------------------------------------------------------------------

def build_lines(sectioned: bool = True):
    parts = []
    clip_bolt = F.socket_cap_bolt(6.0, 16.0)
    for i, (px, ry, rz, ix, iy) in enumerate(SCAVENGE, start=1):
        pts = [(px, -182.0, OUTLET_Z), (px, ry, OUTLET_Z), (px, ry, rz),
               (ix, ry, rz), (ix, iy, rz), (ix, iy, PUMP_BOT_Z - 9.0)]
        parts.append(P.style(tube(pts, HOSE_D, HOSE_BEND), f"scavenge_hose:{i}", P.HOSE))
        run_lo, run_hi = min(px, ix), max(px, ix)
        used = []
        for j, frac in enumerate((0.3, 0.72), start=1):
            cx = run_lo + (run_hi - run_lo) * frac
            bx, bz = min((b for b in CLIP_BOSS if b not in used),
                         key=lambda b: abs(b[0] - cx))
            used.append((bx, bz))
            clip, seat = _p_clip((bx, -160.0, bz), (0, -1, 0), (bx, ry, rz), (1, 0, 0), HOSE_D)
            parts.append(P.style(clip, f"oil_line_clip:{i}_{j}", P.STEEL_DARK))
            parts.append(P.style(F.place(clip_bolt, seat, (0, -1, 0)),
                                 f"oil_line_clip_bolt:{i}_{j}", P.TITANIUM))

    pts = [(PRESS_OUT[0], PRESS_OUT[1], PUMP_BOT_Z - 9.0),
           (PRESS_OUT[0], PUMP_C[1], -172.0),
           (276.0, PUMP_C[1], -172.0), (276.0, FILTER_IN[1], -172.0),
           (FILTER_X, FILTER_IN[1], -172.0), (FILTER_X, FILTER_IN[1], FILTER_Z - 56.0)]
    parts.append(P.style(tube(pts, HOSE_D, 18.0), "pressure_hose", P.HOSE))
    for j, (cx, cy) in enumerate(PRESS_CLIP, start=1):
        clip, seat = _p_clip((cx, cy, PAN_BOT_Z - 10.0), (0, 0, -1),
                             (cx, cy, -172.0), (0, 1, 0), HOSE_D)
        parts.append(P.style(clip, f"oil_line_clip:p_{j}", P.STEEL_DARK))
        parts.append(P.style(F.place(clip_bolt, seat, (0, 0, -1)),
                             f"oil_line_clip_bolt:p_{j}", P.TITANIUM))

    parts.append(P.style(F.place(an_fitting(hex_af=26.0, tail_l=16.0, bore=HOSE_D + 0.4, hex_l=11.0),
                                 (FILTER_X, FILTER_IN[1], FILTER_Z - 48.0), (0, 0, -1)),
                         "pressure_fitting:filter", P.MACHINED_STEEL))
    return parts


# ---------------------------------------------------------------------------

def build(sectioned: bool = True):
    parts = []
    parts += build_pan(sectioned)
    parts += build_windage_tray(sectioned)
    parts += build_pump(sectioned)
    parts += build_filter(sectioned)
    parts += build_lines(sectioned)
    return parts


if __name__ == "__main__":
    import time

    t0 = time.time()
    bad = []
    parts = build(True)
    for p in parts:
        bb = p.bounding_box()
        ok = geo.sound(p)
        if not ok:
            bad.append(p.label)
        print(f"  {'ok  ' if ok else 'FAIL'}  {p.label:34s} "
              f"x[{bb.min.X:7.1f},{bb.max.X:7.1f}] y[{bb.min.Y:7.1f},{bb.max.Y:7.1f}] "
              f"z[{bb.min.Z:7.1f},{bb.max.Z:7.1f}]")
    print(f"{len(parts)} solids, {len(bad)} unsound, {time.time() - t0:.1f}s")
    if bad:
        print("UNSOUND:", bad)
