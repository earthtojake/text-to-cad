"""Exhaust: 16 primaries into four merge collectors on the turbine inlets,
flanges/studs/nuts, gaskets, downpipes with V-bands, heat shields.

LEAN BY DESIGN (the previous construction reached 19 GB): every tube is ONE
annulus swept once along a FilletPolyline; every trumpet and collector is a
two-section loft minus a smaller loft; no retry ladders, no fuzzy booleans,
no per-part clearance sweeps inside build().

Geometry: the exhaust ports leave each head's outer face pointing outward and
down at 45 deg; the turbo sits directly outboard-below (axis at |y| 425,
z 25) with its turbine inlet facing up at |y| 395, z 120, and the cam cover's
outer edge runs from (|y| 349, z 167) up to (|y| 396, z 215). The only clean
corridor is the band above the turbo housing and below that cover edge, so
the manifold is a compact log: each cylinder's two ports merge in a short
trumpet, the four Ø42 runners of a turbo fan in plan toward a merge collector
whose inboard flank they enter, and the collector's cone drops onto the
turbine flange.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import fasteners as F, geo, palette as P, spec as S

TUBE_OD, TUBE_WALL = 42.0, 1.5
FLANGE_T, FLANGE_W, FLANGE_H, FLANGE_R = 12.0, 72.0, 52.0, 10.0   # 72 at the 74 mm pitch: 2 mm between flanges
PORT_D = 26.0
STUD_D, STUD_DX, STUD_DH = 8.0, 27.0, 18.0
TRUMPET_LEN = 30.0
GASKET_T, CFLANGE_T = 3.0, 5.0
CFLANGE_W, CFLANGE_H, CFLANGE_BORE = 96.0, 74.0, 40.0
CFLANGE_STUD = (38.0, 16.0)          # matches turbos.py's inlet stud pattern (x, y offsets)
COLL_W = 36.0                        # log width (inboard face at LOG_FLANK_Y)
COLL_WALL = 3.0
DP_OD, DP_WALL, DP_DROP, DP_AFT = 76.0, 1.6, 115.0, 220.0
DP_FRONT_OUT = -130.0                # front downpipe swings INBOARD (under the block skirt) before running aft past the rear turbo:
                                     # outboard put the widest point of the engine at |y| 590
SHIELD_T, SHIELD_GAP = 1.2, 8.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _out(bank):
    m = S.bank_m(bank)
    return (0.0, -m[1], -m[2])                 # outward normal of the head's outer face


def _face_pt(bank, x, dm=0.0, dh=0.0):
    return S.bank_point(bank, x, S.EXHAUST_EXIT_M - 4.0 + dm, S.EXHAUST_EXIT_H + dh)   # pads reach m = -134


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dist(a, b):
    return math.dist(a, b)


def _tube(points, od, wall, radius):
    """One annulus swept along a FilletPolyline through `points`. The bend
    radius is the largest that fits every corner (each leg must exceed
    r * tan(turn/2) with margin) and must stay above 0.6 x OD, or the sweep
    self-intersects and OCCT eats memory instead of failing."""
    r = radius
    for i in range(1, len(points) - 1):
        a = bd.Vector(*points[i]) - bd.Vector(*points[i - 1])
        b = bd.Vector(*points[i + 1]) - bd.Vector(*points[i])
        turn = math.acos(max(-1.0, min(1.0, a.normalized().dot(b.normalized()))))
        leg = min(a.length, b.length) * (0.5 if i in (1, len(points) - 2) and len(points) > 3 else 0.85)
        t = math.tan(turn / 2.0)
        if t > 1e-6:
            r = min(r, leg / t)
    if r < 0.6 * od:
        raise ValueError(f"tube bend radius {r:.1f} < 0.6 x OD {od}: lengthen the path legs")
    path = bd.FilletPolyline(*[bd.Vector(*p) for p in points], radius=r)
    t0 = bd.Vector(*points[1]) - bd.Vector(*points[0])
    plane = geo.plane(points[0], (t0.X, t0.Y, t0.Z))
    face = plane * (bd.Circle(od / 2.0) - bd.Circle(od / 2.0 - wall))
    return bd.sweep(face, path=path, transition=bd.Transition.ROUND)


def _loft_shell(plane_a, sketch_a, plane_b, sketch_b, wall):
    outer = bd.loft([plane_a * sketch_a, plane_b * sketch_b])
    inner = bd.loft([plane_a * bd.offset(sketch_a, -wall), plane_b * bd.offset(sketch_b, -wall)])
    return outer - inner


# ---------------------------------------------------------------------------
# per-cylinder: flange, studs, trumpet, primary
# ---------------------------------------------------------------------------

def _group(cyl):
    return "front" if S.pin_index(cyl) < 4 else "rear"


# --- log collectors -----------------------------------------------------------
# One slim cast log per turbo, spanning its four cylinders INBOARD of the charge
# couplers (which rise at |y| 435 from the compressor outlets at x 192 / -222 and
# cap the log at |y| <= 397).  The turbine flange sits under a saddle on the
# log's outboard side.  Runners are short and straight: no lean along X, so
# neighbours never touch and the routing reads like the compact production
# manifolds of the real engine.  Envelope checks against the cam-cover edge line
# (z < 1.02 |y| - 189): log inboard-top corner (355, 159.5) vs 173; shield lid
# (355, 168.7) vs 173; trumpet mouth top (325.8, 129.3) vs 143.
LOG_FLANK_Y = 355.0                  # |y| of the log's inboard face (outboard face 391: 4 mm inside the charge clamps at ~395)
COLL_Z0, COLL_Z1 = 94.5, 159.5       # log z band: bottom 11.5 mm over the turbine flange top (83)
RUNNER_IN_Z = 127.0                  # runner axis height where it meets the flank (log mid-height)
RUNNER_UP_DEG = 30.0                 # trumpet exit / runner climb angle; the loft is sound at 30-35.  The runner
                                     # axis meets the flank at z ~126 (log mid-height): its Ø42 window then spans
                                     # z 102-151, inside the cavity's 97.5-156.5
LOG_END = TUBE_OD / 2.0 + 3.0        # log overhang past the end cylinders' runner axes
BOSS_R, BOSS_Z1 = 28.0, 127.0        # round boss over the turbine flange: r 28 clears the M8 nuts on the
                                     # 38 x 16 stud pattern (41 from centre) by 4 mm; wall 8 around the Ø40 bore


def _collector_frame(bank, pos):
    t = S.turbo(bank, pos)
    xi, yi, zi = t["turbine_inlet"]
    s = S.sign_of_bank(bank)
    xs = sorted(d.x for d in S.CYLINDERS if d.bank == bank and _group(d.number) == pos)
    x0, x1 = xs[0] - LOG_END, xs[-1] + LOG_END
    return {"x": xi, "y": yi, "z": zi, "s": s, "x0": x0, "x1": x1, "xc": 0.5 * (x0 + x1), "length": x1 - x0,
            "flank_y": s * LOG_FLANK_Y, "log_y": s * (LOG_FLANK_Y + COLL_W / 2.0)}


def _runner_geometry(c):
    """(runner direction d0, trumpet mouth, point on the log flank, end inside the wall)."""
    bank = c.bank
    s = S.sign_of_bank(bank)
    o = _out(bank)
    face = _face_pt(bank, c.x)
    up = math.radians(RUNNER_UP_DEG)
    d0 = (0.0, s * math.cos(up), math.sin(up))
    mouth = _add(_add(face, _mul(o, FLANGE_T)), _mul(d0, TRUMPET_LEN))
    # the straight runner continues along d0 to the flank; RUNNER_IN_Z is where
    # that line meets |y| = LOG_FLANK_Y (documented, checked in the test)
    L = (LOG_FLANK_Y - abs(mouth[1])) / math.cos(up)
    flank = _add(mouth, _mul(d0, L))
    end = _add(flank, _mul(d0, (COLL_WALL + 2.0) / math.cos(up)))
    return d0, mouth, flank, end


def build_cylinder(c, sectioned):
    bank = c.bank
    o = _out(bank)
    up = S.bank_up(bank)
    face = _face_pt(bank, c.x)
    parts = []
    if geo.in_section_void(face, bank, sectioned):
        return parts                      # bank-1 statics in the museum void: nothing on this port
    # flange plate on the port pad, two port openings, four studs + nuts
    plate = bd.Box(FLANGE_W, FLANGE_H, FLANGE_T, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    plate = plate - [bd.Cylinder(PORT_D / 2, 40).moved(bd.Location((sx * S.VALVE_X_HALF, 0, 0))) for sx in (-1, 1)]
    plate = plate - [bd.Cylinder(STUD_D / 2 + 0.4, 40).moved(bd.Location((sx * STUD_DX, sy * STUD_DH, 0)))
                     for sx in (-1, 1) for sy in (-1, 1)]
    x_dir = (1.0, 0.0, 0.0)
    plate = geo.locate(plate, face, o, x_dir)
    parts.append(P.style(plate, f"exhaust_flange:{c.number}", P.MACHINED))
    stud = F.stud(STUD_D, FLANGE_T + 9.0, 14.0)
    nut = F.flange_nut(STUD_D)
    k = 0
    for sx in (-1, 1):
        for sy in (-1, 1):
            k += 1
            seat = _add(face, _add(_mul(x_dir, sx * STUD_DX), _mul(up, sy * STUD_DH)))
            parts.append(P.style(geo.locate(stud, seat, o, x_dir), f"exhaust_flange_stud:{c.number}_{k}", P.STEEL_DARK))
            parts.append(P.style(geo.locate(nut, _add(seat, _mul(o, FLANGE_T)), o, x_dir),
                                 f"exhaust_flange_nut:{c.number}_{k}", P.STEEL_DARK))
    # trumpet: a cast elbow — stadium over the two ports on the flange face,
    # turning into a round that already points along the runner direction
    d0, mouth, flank, end = _runner_geometry(c)
    p_a = _add(face, _mul(o, FLANGE_T))
    pl_a = geo.plane(p_a, o, x_dir)
    pl_b = geo.plane(mouth, d0, x_dir)
    stadium = bd.SlotCenterToCenter(2 * S.VALVE_X_HALF, PORT_D + 6.0)
    trumpet = _loft_shell(pl_a, stadium, pl_b, bd.Circle(TUBE_OD / 2.0), TUBE_WALL)
    parts.append(P.style(trumpet, f"exhaust_trumpet:{c.number}", P.INCONEL))
    # runner: one straight annulus from the trumpet mouth into the log wall
    ring = pl_b * (bd.Circle(TUBE_OD / 2.0) - bd.Circle(TUBE_OD / 2.0 - TUBE_WALL))
    tube = bd.extrude(ring, amount=_dist(mouth, end))
    parts.append(P.style(tube, f"exhaust_primary:{c.number}", P.INCONEL))
    return parts


# ---------------------------------------------------------------------------
# per-turbo: gasket, flange, log collector, downpipe, heat shield
# ---------------------------------------------------------------------------

def _plan_rect(xc, yc, z, length, width, r):
    return bd.Plane(origin=(xc, yc, z), z_dir=(0, 0, 1)) * bd.RectangleRounded(length, width, r)


def build_collector(bank, pos, sectioned):
    t = S.turbo(bank, pos)
    fr = _collector_frame(bank, pos)
    x, y, z, s = fr["x"], fr["y"], fr["z"], fr["s"]
    xc, length, log_y = fr["xc"], fr["length"], fr["log_y"]
    tag = f"{bank}_{pos}"
    parts = []
    gasket = bd.Box(CFLANGE_W, CFLANGE_H, GASKET_T, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((x, y, z)))
    gasket = gasket - ([bd.Cylinder(CFLANGE_BORE / 2, 20).moved(bd.Location((x, y, z)))] +
                       [bd.Cylinder(STUD_D / 2 + 0.6, 20).moved(bd.Location((x + sx * CFLANGE_STUD[0], y + sy * CFLANGE_STUD[1], z)))
                        for sx in (-1, 1) for sy in (-1, 1)])
    parts.append(P.style(gasket, f"turbine_inlet_gasket:{tag}", P.GASKET))
    z_f = z + GASKET_T
    flange = bd.Box(CFLANGE_W, CFLANGE_H, CFLANGE_T, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((x, y, z_f)))
    holes = [bd.Cylinder(STUD_D / 2 + 0.4, 40).moved(bd.Location((x + sx * CFLANGE_STUD[0], y + sy * CFLANGE_STUD[1], z_f)))
             for sx in (-1, 1) for sy in (-1, 1)]
    flange = flange - (holes + [bd.Cylinder(CFLANGE_BORE / 2, 40).moved(bd.Location((x, y, z_f)))])
    parts.append(P.style(flange, f"collector_flange:{tag}", P.MACHINED_STEEL))
    # log: rounded-plan box, soft top and bottom edges, hollow; saddle block over
    # the turbine flange on the outboard side with the Ø40 bore up into the log
    z_top = z_f + CFLANGE_T                      # 83: the saddle stands on the collector flange
    outer = bd.extrude(_plan_rect(xc, log_y, COLL_Z0, length, COLL_W, 15.0), amount=COLL_Z1 - COLL_Z0)
    for r, zz in ((7.0, COLL_Z1), (5.0, COLL_Z0)):
        try:
            outer = outer.fillet(r, [e for e in outer.edges() if abs(e.center().Z - zz) < 1e-6])
        except Exception:
            pass
    saddle = bd.Cylinder(BOSS_R, BOSS_Z1 - z_top, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((x, y, z_top)))
    try:
        saddle = saddle.fillet(5.0, [e for e in saddle.edges() if abs(e.center().Z - BOSS_Z1) < 1e-6])
    except Exception:
        pass
    inner = bd.extrude(_plan_rect(xc, log_y, COLL_Z0 + COLL_WALL, length - 2 * COLL_WALL, COLL_W - 2 * COLL_WALL, 12.0),
                       amount=COLL_Z1 - COLL_Z0 - 2 * COLL_WALL)
    bore = bd.Cylinder(CFLANGE_BORE / 2, (COLL_Z1 - COLL_WALL - 10.0) - (z_top - 2.0), align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((x, y, z_top - 2.0)))
    body = geo.cut_fuzzy(geo.fuse_fuzzy([outer, saddle]), [inner, bore])
    # runner windows, cut along each runner's own axis through the inboard flank
    wins = []
    for c in S.CYLINDERS:
        if c.bank != bank or _group(c.number) != pos:
            continue
        d0, mouth, flank, end = _runner_geometry(c)
        w = bd.Cylinder(TUBE_OD / 2 + 0.2, 30.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
        wins.append(geo.locate(w, flank, d0, (1, 0, 0)))
    taps = [bd.Cylinder(3.3, 16.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(bd.Location((xc + dx, log_y, COLL_Z1 + 1.0)))
            for dx in (-100.0, 0.0, 100.0)]
    body = geo.cut_fuzzy(body, wins + taps)
    body = geo.sectioned(body, bank, sectioned)
    parts.append(P.style(body, f"exhaust_collector:{tag}", P.CAST_DARK))
    if sectioned and bank == S.SECTION_BANK and t["centre"][0] > S.SECTION_X:
        return parts                       # the sectioned bank's front turbo is lifted off: no downpipe, no log shield past the cut
    # downpipe: V-band ring + pipe down, then aft (front turbo swings INBOARD first)
    fx, fy, fz = t["downpipe_flange"]
    ring = bd.Cylinder((DP_OD + 16.0) / 2, 10.0).moved(bd.Location((fx, fy, fz - 5.0))) - bd.Cylinder(DP_OD / 2 + 0.2, 20).moved(bd.Location((fx, fy, fz - 10.0)))
    parts.append(P.style(ring, f"downpipe_vband:{tag}", P.STEEL_DARK))
    pts = [(fx, fy, fz - 2.0), (fx, fy, fz - DP_DROP)]
    if pos == "front":
        pts.append((fx, fy + s * DP_FRONT_OUT, fz - DP_DROP))
        pts.append((fx - DP_AFT, fy + s * DP_FRONT_OUT, fz - DP_DROP))
    else:
        pts.append((fx - DP_AFT, fy, fz - DP_DROP))
    pipe = _tube(pts, DP_OD, DP_WALL, 50.0)
    parts.append(P.style(pipe, f"downpipe:{tag}", P.INCONEL))
    # heat shield: a formed lid floating SHIELD_GAP over the log top, 3 spacers + M6
    z_lid = COLL_Z1 + SHIELD_GAP
    lid = bd.extrude(_plan_rect(xc, log_y, z_lid, length - 16.0, COLL_W, 12.0), amount=SHIELD_T)
    lip = bd.extrude(_plan_rect(xc, log_y, z_lid - 6.0, length - 16.0, COLL_W, 12.0)
                     - _plan_rect(xc, log_y, z_lid - 6.0, length - 16.0 - 2 * SHIELD_T, COLL_W - 2 * SHIELD_T, 11.0), amount=6.0)
    shield = (lid + lip) - [bd.Cylinder(3.3, 20.0).moved(bd.Location((xc + dx, log_y, z_lid))) for dx in (-100.0, 0.0, 100.0)]
    shield = geo.sectioned(shield, bank, sectioned)
    parts.append(P.style(shield, f"exhaust_heat_shield:{tag}", P.MACHINED_STEEL))
    for k, dx in enumerate((-100.0, 0.0, 100.0)):
        base = (xc + dx, log_y, COLL_Z1)
        if geo.in_section_void(base, bank, sectioned):
            continue
        spacer = geo.cyl_along(base, (base[0], base[1], base[2] + SHIELD_GAP), 8.0) - bd.Cylinder(3.3, 40.0).moved(bd.Location(base))
        parts.append(P.style(spacer, f"heat_shield_spacer:{tag}_{k + 1}", P.MACHINED_STEEL))
        bolt = F.socket_cap_bolt(6.0, SHIELD_GAP + 6.0)
        parts.append(P.style(geo.locate(bolt, (base[0], base[1], base[2] + SHIELD_GAP + SHIELD_T), (0, 0, 1)),
                             f"heat_shield_bolt:{tag}_{k + 1}", P.TITANIUM))
    return parts


def build(sectioned: bool = True):
    parts = []
    for c in S.CYLINDERS:
        parts += build_cylinder(c, sectioned)
    for bank in (1, 2):
        for pos in ("front", "rear"):
            parts += build_collector(bank, pos, sectioned)
    return parts
