"""Crankshaft system: the P&W-style two-piece single-throw crankshaft.

FRONT half  (`crank:front_crank`, one forging): nose flange (front face on
            spec.CRANK_NOSE_FLANGE_Y), hollow nose shaft, splined cam-gear
            seat, front main journal, pear-shaped front cheek and the integral
            hollow crankpin (Ø70, runs through the rear cheek to y = +64).
REAR half   (`crank:rear_crank`): rear cheek split-clamped onto the crankpin
            (clamp slot + clamp bolt + castellated nut + cotter pin), rear main
            journal and the splined rear shaft for the blower drive gear.
Each cheek's lower lobe is a FORK carrying a pendulum (dynamic-damper)
counterweight on two hardened pins in oversize bushings — the counterweight
tongue hangs in the fork slot, its heavy crescent rim sweeps outside the cheek
(r 80..110, |y| 42..64).
Main bearings: cylindrical roller bearings, inner race + rollers + cage as ONE
rotating body (`crank:<end>_main_inner`), outer race static
(`crankshaft:<end>_main_outer`, OD 140) for the crankcase to house.

Authored at theta = 0: crankpin centre (0, y, 73), counterweights hang at -Z.
All rotating parts are labelled `crank:` and turn with `kin.pose_crank`.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("steel_machined", "steel_dark", "fastener", "safety_wire")

# ---------------------------------------------------------------------------
# Dimensions (engine frame; see spec.py)
# ---------------------------------------------------------------------------
PIN_Z = S.R_CRANK                      # 73
PIN_R = S.CRANKPIN_D / 2.0             # 35
PIN_BORE_R = 17.0
JOURNAL_R = S.MAIN_JOURNAL_D / 2.0     # 40
CHEEK_IN, CHEEK_OUT = S.CHEEK_Y        # 42, 64
CHEEK_LOBE_R = 76.0                    # lower (fork) lobe of each cheek
PIN_BOSS_R = {-1: 52.0, 1: 58.0}       # front (integral pin) / rear (clamp boss)
FORK_SLOT = (48.0, 58.0)               # |y| of the fork slot in each cheek
TONGUE = (48.5, 57.5)                  # |y| of the counterweight tongue
CW_RIM_R = (80.0, 109.5)
CW_RIM_HALF = 58.0                     # rim half-angle about -Z (deg)
CW_PIN_R, CW_PIN_ANG = 58.0, 20.0      # pendulum pins: radius, +-angle about -Z
CW_PIN_D, CW_BUSH_OD = 14.0, 22.0
CW_BUSH_ID = 18.0
BRG_Y = {-1: (-100.0, -72.0), 1: (72.0, 100.0)}
NS = S.NOSE_SHIFT                      # nose section moved forward (-130)
FLANGE_Y0 = S.CRANK_NOSE_FLANGE_Y      # front face (-256 + NOSE_SHIFT)
FLANGE_T = 14.0
FLANGE_R = 75.0
BELL_PCD_R = 62.5
NOSE_THREAD_L = 12.0                   # flange-nut thread at the nose end (in the flange recess)
FLANGE_HUB_L = 29.0                    # splined hub length behind the recess (ends 3 mm ahead of the nose diaphragm, y -342)
FLANGE_RECESS_R = 38.0
NOSE_BORE_R = 18.0                     # crank-nose bore: propshaft pilot (r 17.6) runs in it
BELL_BOLTS = 8
BELL_FLANGE_T = 6.0                    # assumed bell-gear flange thickness at the bolt circle
CLAMP_Z, CLAMP_SEAT_X = 118.0, 22.0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _xz_plane(y_hi):
    """Sketch plane whose local (x, y) are world (X, Z); +normal = -Y, at y_hi."""
    return bd.Plane(origin=(0, y_hi, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))


def slab(sketch, y_lo, y_hi):
    """Extrude a 2D (x, z) sketch between stations y_lo < y_hi."""
    return bd.extrude(_xz_plane(y_hi) * sketch, amount=y_hi - y_lo)


def ip(b_deg, r):
    """2D (x, z) point at in-plane angle b (deg from +Z, see spec) and radius r."""
    b = math.radians(b_deg)
    return (-r * math.sin(b), r * math.cos(b))


def sector2d(b0, b1, r0, r1):
    """True-arc annular sector between in-plane angles b0 < b1 (2D x, z)."""
    bm = 0.5 * (b0 + b1)
    edges = [
        bd.ThreePointArc(ip(b0, r1), ip(bm, r1), ip(b1, r1)),
        bd.Line(ip(b1, r1), ip(b1, r0)),
        bd.ThreePointArc(ip(b1, r0), ip(bm, r0), ip(b0, r0)),
        bd.Line(ip(b0, r0), ip(b0, r1)),
    ]
    return bd.Sketch() + bd.make_face(edges)


def yspan(s, a, b):
    """(lo, hi) of the |y| span a..b on side s (-1 front, +1 rear)."""
    return (min(s * a, s * b), max(s * a, s * b))


def circle_edges(shape, r, y, tol=0.05):
    out = []
    for e in shape.edges():
        if e.geom_type != bd.GeomType.CIRCLE:
            continue
        try:
            if abs(e.radius - r) < tol and abs(C.edge_center(e).Y - y) < tol:
                out.append(e)
        except Exception:
            pass
    return out


def styled(shape, label, color):
    return P.style(shape, label, color)


# ---------------------------------------------------------------------------
# Shaft pieces
# ---------------------------------------------------------------------------
def spline_ring(y_lo, y_hi, r_root=27.0, r_tip=30.0, n=18, w=5.0):
    teeth = [bd.Rot(0, 0, 360.0 * i / n) * bd.Pos(0, 0.5 * (r_root - 0.4 + r_tip + 0.4))
             * bd.Rectangle(w, r_tip - r_root + 0.8) for i in range(n)]
    sk = (bd.Circle(r_root) + teeth) & bd.Circle(r_tip)
    return slab(sk, y_lo, y_hi)


def cheek_outline(s):
    """Pear-shaped cheek: hull of the pin boss and the lower fork lobe."""
    pin = bd.Pos(0, PIN_Z) * bd.Circle(PIN_BOSS_R[s])
    lobe = bd.Circle(CHEEK_LOBE_R)
    return bd.make_hull(pin.edges() + lobe.edges())


def cheek_plate(s):
    lo, hi = yspan(s, CHEEK_IN, CHEEK_OUT)
    plate = slab(cheek_outline(s), lo, hi)
    rims = [e for e in plate.edges() if abs(abs(C.edge_center(e).Y) - CHEEK_IN) < 1e-3
            or abs(abs(C.edge_center(e).Y) - CHEEK_OUT) < 1e-3]
    plate, _ = C.safe_fillet(plate, rims, 3.0, min_r=1.0)
    return plate


def fork_cuts(s):
    """The fork slot and the pendulum-pin holes through the cheek's lower lobe."""
    lo, hi = yspan(s, *FORK_SLOT)
    slot = bd.Box(260, hi - lo, 200, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MAX))
    slot = bd.Pos(0, lo, -30.0) * slot
    holes = []
    for a in (180.0 - CW_PIN_ANG, 180.0 + CW_PIN_ANG):
        x, z = ip(a, CW_PIN_R)
        holes.append(geo.cyl_y(*yspan(s, 36.0, 70.0), CW_PIN_D, x, z))
    return slot, holes


def front_crank():
    s = -1
    fy = FLANGE_Y0
    # nose: threaded end (flange nut) + spline for the separate bell-gear flange hub,
    # everything forward of the crankcase <= r 31 so the nose case slides off forward
    ns0, ns1 = fy + NOSE_THREAD_L, fy + NOSE_THREAD_L + FLANGE_HUB_L
    prof = [(NOSE_BORE_R, fy + 2), (25, fy + 2), (26, fy + 3), (26, ns0), (28, ns0), (28, ns1), (31, ns1),
            (31, -152 + NS), (28, -152 + NS), (28, -140 + NS), (27, -140 + NS), (27, -116 + NS),
            (33, -116 + NS), (33, -110 + NS), (30, -107 + NS),      # cam-gear seat + shoulder
            (30, -113), (33, -110),                                  # Ø60 neck shaft
            (38, -110), (38, -100), (39.2, -100), (40, -99.2), (40, -61), (0, -61), (0, -104),
            (NOSE_BORE_R, -112)]
    shaft = geo.revolve_y(prof)
    nose_spline = spline_ring(ns0, ns1, r_root=28.0, r_tip=31.0)
    splines = spline_ring(-140.0 + NS, -116.0 + NS)
    pin = geo.cyl_y(-61.0, CHEEK_OUT, S.CRANKPIN_D, 0.0, PIN_Z)
    body = C.fuse_all([shaft, cheek_plate(s), pin, splines, nose_spline])
    # journal root fillet (forged-to-ground transition)
    body, _ = C.safe_fillet(body, circle_edges(body, JOURNAL_R, -CHEEK_OUT), 5.0, min_r=1.0)

    slot, holes = fork_cuts(s)
    pin_bore = geo.cyl_y(-70.0, 70.0, 2 * PIN_BORE_R, 0.0, PIN_Z)
    # crankpin oil holes (bore -> bearing surface), leading side of the pin
    oil = []
    for y in (-20.0, 20.0):
        d = ip(-35.0, 1.0)
        p0 = (0.0, y, PIN_Z)
        p1 = (d[0] * (PIN_R + 3), y, PIN_Z + d[1] * (PIN_R + 3))
        oil.append(geo.cyl_along(p0, p1, 6.0))
    # the spline rings are solid discs: re-drill the nose bore through them (the
    # prop shaft's pilot runs in it, r 17.6 in Ø36)
    nose_bore = geo.cyl_y(fy - 1.0, -112.0, 2 * NOSE_BORE_R)
    body = C.cut_all(body, [slot, pin_bore, nose_bore] + holes + oil)
    return body


def bell_flange():
    """Separate splined hub + Ø150 flange the bell gear bolts to; withdraws forward
    off the nose spline once `crank:bell_flange_nut` (in the front recess) is off."""
    fy = FLANGE_Y0
    ns0, ns1 = fy + NOSE_THREAD_L, fy + NOSE_THREAD_L + FLANGE_HUB_L
    prof = [(FLANGE_RECESS_R, fy), (FLANGE_R - 1.5, fy), (FLANGE_R, fy + 1.5), (FLANGE_R, fy + FLANGE_T - 1.5),
            (FLANGE_R - 1.5, fy + FLANGE_T), (44, fy + FLANGE_T), (44, ns1 - 1.0), (43, ns1),
            (20, ns1), (20, ns0), (FLANGE_RECESS_R, ns0)]
    hub = geo.revolve_y(prof)
    hub, _ = C.safe_fillet(hub, circle_edges(hub, 44.0, fy + FLANGE_T), 6.0, min_r=1.0)
    bore = spline_ring(ns0 - 1.0, ns1 + 1.0, r_root=28.15, r_tip=31.15, w=5.3)
    bolt_holes = []
    for i in range(BELL_BOLTS):
        x, z = ip(22.5 + 45.0 * i, BELL_PCD_R)
        bolt_holes.append(geo.cyl_y(fy - 2, fy + FLANGE_T + 2, 8.4, x, z))
    return C.cut_all(hub, [bore] + bolt_holes)


def rear_crank():
    s = 1
    prof = [(0, 61), (40, 61), (40, 99.2), (39.2, 100), (38, 100), (38, 110), (30, 110), (30, 118),
            (27, 118), (27, 145), (26, 146), (15, 146), (15, 90), (0, 80)]
    shaft = geo.revolve_y(prof)
    splines = spline_ring(118.0, 145.0)
    body = C.fuse_all([shaft, cheek_plate(s), splines])
    body = C.cut_all(body, [geo.cyl_y(88.0, 147.0, 30.0)])      # oil bore through the spline core
    body, _ = C.safe_fillet(body, circle_edges(body, JOURNAL_R, CHEEK_OUT), 5.0, min_r=1.0)

    slot, holes = fork_cuts(s)
    bore = geo.cyl_y(38.0, 68.0, S.CRANKPIN_D, 0.0, PIN_Z)
    # split clamp: slot from the pin bore out through the boss top
    clamp_slot = bd.Pos(0, 53.0, PIN_Z + PIN_R + 15.0) * bd.Box(2.2, 30.0, 40.0)
    bolt_hole = geo.cyl_along((-60, 53.0, CLAMP_Z), (60, 53.0, CLAMP_Z), 10.5)
    seats = [bd.Pos(sx * (CLAMP_SEAT_X + 30.0), 53.0, 131.0) * bd.Box(60.0, 30.0, 58.0)
             for sx in (-1, 1)]
    # tool families that do not overlap each other
    for fam in ([slot, bore] + holes, seats, [clamp_slot], [bolt_hole]):
        body = C.cut_all(body, fam)
    # break the bore edge on the inner (rod-side) face
    body, _ = C.safe_chamfer(body, [e for e in body.edges()
                                    if e.geom_type == bd.GeomType.CIRCLE
                                    and abs(C.edge_center(e).Y - CHEEK_IN) < 1e-3
                                    and abs(e.radius - PIN_R) < 0.05], 1.0, min_length=0.3)
    return body


# ---------------------------------------------------------------------------
# Pendulum counterweights
# ---------------------------------------------------------------------------
def counterweight(s):
    lo, hi = yspan(s, CHEEK_IN, CHEEK_OUT)
    rim = slab(sector2d(180.0 - CW_RIM_HALF, 180.0 + CW_RIM_HALF, *CW_RIM_R), lo, hi)
    rim, _ = C.safe_fillet(rim, rim.edges().filter_by(bd.GeomType.LINE, reverse=True)
                           + rim.edges().filter_by(bd.GeomType.LINE), 3.0, min_r=1.0)
    # forging flash line round the crescent's mid-plane
    rim = C.parting_line(rim, bd.Plane(origin=(0, 0.5 * (lo + hi), 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0)),
                         height=0.4, width=1.2)
    tlo, thi = yspan(s, *TONGUE)
    tongue_sk = sector2d(180.0 - 40.0, 180.0 + 40.0, 38.0, CW_RIM_R[0] + 4.0) & \
        (bd.Pos(0, -34.0 - 100.0) * bd.Rectangle(300, 200))
    tongue = slab(tongue_sk, tlo, thi)
    tongue, _ = C.safe_fillet(tongue, [e for e in tongue.edges()
                                       if C.edge_center(e).Z > -CW_RIM_R[0] * math.cos(math.radians(40))
                                       and e.geom_type == bd.GeomType.LINE
                                       and abs(e.tangent_at(0).Y) < 0.5], 1.5, min_r=0.5)
    cw = C.fuse_all([rim, tongue])
    holes = []
    for a in (180.0 - CW_PIN_ANG, 180.0 + CW_PIN_ANG):
        x, z = ip(a, CW_PIN_R)
        holes.append(geo.cyl_y(tlo - 1, thi + 1, CW_BUSH_OD, x, z))
    ym = 0.5 * (lo + hi)
    for a in (180.0 - 30.0, 180.0 + 30.0):       # balance drillings in the rim
        d = ip(a, 1.0)
        p0 = (d[0] * (CW_RIM_R[1] - 10.0), ym, d[1] * (CW_RIM_R[1] - 10.0))
        p1 = (d[0] * (CW_RIM_R[1] + 2.0), ym, d[1] * (CW_RIM_R[1] + 2.0))
        holes.append(geo.cyl_along(p0, p1, 11.0))
    return C.cut_all(cw, holes)


def cw_pin_proto():
    """Hardened pendulum pin, head seat at z = 0, body down -Z (22 long)."""
    r, rh = CW_PIN_D / 2.0, CW_BUSH_OD / 2.0
    L = CHEEK_OUT - CHEEK_IN
    return F._rev([(0, -L), (r - 0.6, -L), (r, -L + 0.6), (r, 0), (rh - 0.6, 0), (rh, 0.6),
                   (rh, 1.4), (rh - 0.6, 2.0), (0, 2.0)])


def bushing_proto():
    L = TONGUE[1] - TONGUE[0]
    ro, ri = CW_BUSH_OD / 2.0, CW_BUSH_ID / 2.0
    return F._rev([(ri + 0.4, 0), (ro, 0), (ro, L), (ri + 0.4, L), (ri, L - 0.4), (ri, 0.4)])


def crankpin_plug():
    """Sealing plug: pressed into the pin bore, domed cap with a hex wrenching boss."""
    body = F._rev([(0, -10.0), (PIN_BORE_R - 0.5, -10.0), (PIN_BORE_R, -9.5), (PIN_BORE_R, 0),
                   (PIN_BORE_R + 4.0 - 0.5, 0), (PIN_BORE_R + 4.0, 0.5), (PIN_BORE_R + 4.0, 0.8),
                   (PIN_BORE_R + 2.5, 1.2), (0, 1.3)])
    hexb = F._wrench_head(14.0, 1.0, 2.0, dish=0.0)
    return C.fuse_all([body, hexb])


# ---------------------------------------------------------------------------
# Main bearings
# ---------------------------------------------------------------------------
def bearing(s):
    y0, y1 = BRG_Y[s]
    inner = geo.revolve_y([(40.0, y0), (50.0, y0), (50.5, y0 + 0.5), (50.5, y0 + 2.5), (47.0, y0 + 3.0),
                           (47.0, y1 - 3.0), (50.5, y1 - 2.5), (50.5, y1 - 0.5), (50.0, y1), (40.0, y1)])
    n, rp, rr = 16, 52.8, 6.0
    rollers, bars = [], []
    for i in range(n):
        b = 360.0 * i / n
        x, z = ip(b, rp)
        c = geo.cyl_y(y0 + 4.0, y1 - 4.0, 2 * rr, x, z)
        c, _ = C.safe_chamfer(c, c.edges().filter_by(bd.GeomType.CIRCLE), 0.8, min_length=0.3)
        rollers.append(c)
        xb, zb = ip(b + 180.0 / n, 54.2)
        bar = geo.locate(bd.Box(4.2, 5.0, y1 - y0 - 7.0), (xb, 0.5 * (y0 + y1), zb), (0, 1, 0),
                         (math.cos(math.radians(b + 180.0 / n)), 0, math.sin(math.radians(b + 180.0 / n))))
        bars.append(bar)
    rings = [geo.revolve_y([(51.0, ya), (58.0, ya), (58.0, ya + 2.5), (51.0, ya + 2.5)])
             for ya in (y0 + 3.2, y1 - 5.7)]
    inner_body = C.fuse_all([inner] + rollers + rings + bars)
    outer = geo.revolve_y([(59.4, y0 + 1.0), (60.4, y0), (69.0, y0), (70.0, y0 + 1.0), (70.0, y1 - 1.0),
                           (69.0, y1), (60.4, y1), (59.4, y1 - 1.0)])
    return inner_body, outer


def spanner_nut(r_in, r_out, h, slots=6, slot_w=6.0, slot_d=3.5):
    """Slotted bearing-retaining ring nut, seat at z = 0, body up +Z."""
    body = F._rev([(r_in, 0.6), (r_in + 0.6, 0), (r_out - 0.8, 0), (r_out, 0.8), (r_out, h - 0.8),
                   (r_out - 0.8, h), (r_in + 0.6, h), (r_in, h - 0.6)])
    cuts = [bd.Rot(0, 0, 360.0 * i / slots) * bd.Pos(r_out, 0, h / 2.0) * bd.Box(2 * slot_d, slot_w, h + 2)
            for i in range(slots)]
    return C.cut_all(body, cuts)


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def hex_bolt(d, af, head_h, length):
    """Plain AN-style hex bolt: bearing face z = 0, head up, shank `length` down."""
    head = F._wrench_head(af, 0.0, head_h, chamfer_bottom=True, dish=0.0)
    ch = 0.8
    r = d / 2 - 0.1                    # shank a hair under the nut's thread bore
    shank = F._rev([(0, -length), (r - ch, -length), (r, -length + ch), (r, 0.5), (0, 0.5)])
    return C.fuse_all([head, shank])


def castellated_nut(d, af, h, slot_h=4.0, slot_w=3.2):
    body = F._wrench_head(af, 0.0, h, chamfer_bottom=True, dish=0.0)
    bore = bd.Pos(0, 0, -1) * bd.Cylinder(d / 2.0, h + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    slots = [bd.Rot(0, 0, a) * bd.Pos(0, 0, h - slot_h / 2.0 + 0.5) * bd.Box(af * 1.4, slot_w, slot_h + 1)
             for a in (0.0, 60.0, 120.0)]
    body = body - bore
    return C.cut_all(body, slots)


def cotter_pin(length, d=2.6):
    """Split cotter along +Z from z = 0 (eye end) to z = -length."""
    shaft = bd.Pos(0, 0, -length) * bd.Cylinder(d / 2.0, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    eye = bd.Pos(0, 0, 2.2) * bd.Rot(90, 0, 0) * bd.Torus(2.2, d / 2.0)
    return C.fuse_all([shaft, eye])


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build():
    SM, SD, FA, SW = P.STEEL_MACHINED, P.STEEL_DARK, P.FASTENER, P.SAFETY_WIRE
    parts = []
    parts.append(styled(front_crank(), "crank:front_crank", SM))
    parts.append(styled(rear_crank(), "crank:rear_crank", SM))

    pin_p, bush_p = cw_pin_proto(), bushing_proto()
    for s, side in ((-1, "front"), (1, "rear")):
        parts.append(styled(counterweight(s), f"crank:{side}_counterweight", SD))
        for i, a in enumerate((180.0 - CW_PIN_ANG, 180.0 + CW_PIN_ANG), start=1):
            x, z = ip(a, CW_PIN_R)
            parts.append(styled(F.place(pin_p, (x, s * CHEEK_OUT, z), (0, s, 0)),
                                f"crank:{side}_cw_pin_{i}", SM))
            tlo, _ = yspan(s, *TONGUE)
            parts.append(styled(F.place(bush_p, (x, tlo, z), (0, 1, 0)),
                                f"crank:{side}_cw_bushing_{i}", SM))
        inner, outer = bearing(s)
        parts.append(styled(inner, f"crank:{side}_main_inner", SM))
        parts.append(styled(outer, f"crankshaft:{side}_main_outer", SM))

    plug = crankpin_plug()
    parts.append(styled(F.place(plug, (0, -CHEEK_OUT, PIN_Z), (0, -1, 0)), "crank:crankpin_front_plug", SM))
    parts.append(styled(F.place(plug, (0, CHEEK_OUT, PIN_Z), (0, 1, 0)), "crank:crankpin_rear_plug", SM))

    # bearing retaining nuts + cam-gear lock nut
    main_nut = spanner_nut(38.0, 48.0, 10.0)
    parts.append(styled(F.place(main_nut, (0, -100.0, 0), (0, -1, 0)), "crank:front_main_nut", SD))
    parts.append(styled(F.place(main_nut, (0, 100.0, 0), (0, 1, 0)), "crank:rear_main_nut", SD))
    parts.append(styled(bell_flange(), "crank:bell_flange", SM))
    fnut = spanner_nut(26.0, 36.0, 10.0, slots=6, slot_w=5.0, slot_d=2.5)
    parts.append(styled(F.place(fnut, (0, FLANGE_Y0 + NOSE_THREAD_L, 0), (0, -1, 0)), "crank:bell_flange_nut", SD))
    cam_nut = spanner_nut(28.0, 36.0, 10.0, slots=6, slot_w=5.0, slot_d=2.5)
    parts.append(styled(F.place(cam_nut, (0, -140.0 + NS, 0), (0, -1, 0)), "crank:cam_gear_nut", SD))

    # rear-cheek clamp: bolt head on +X, castellated nut + cotter on -X
    clamp_bolt = hex_bolt(10.0, 15.0, 7.0, 60.0)
    cot_x = -(CLAMP_SEAT_X + 10.0)
    bolt = F.place(clamp_bolt, (CLAMP_SEAT_X, 53.0, CLAMP_Z), (1, 0, 0), (0, 1, 0))
    bolt = bolt - geo.cyl_along((cot_x, 40.0, CLAMP_Z), (cot_x, 66.0, CLAMP_Z), 3.0)
    parts.append(styled(bolt, "crank:clamp_bolt", FA))
    cnut = castellated_nut(10.0, 15.0, 12.0)
    parts.append(styled(F.place(cnut, (-CLAMP_SEAT_X, 53.0, CLAMP_Z), (-1, 0, 0), (0, 1, 0)),
                        "crank:clamp_nut", FA))
    cot = cotter_pin(17.0)
    parts.append(styled(F.place(cot, (cot_x, 62.5, CLAMP_Z), (0, 1, 0), (1, 0, 0)), "crank:clamp_cotter", SW))

    # nose flange: 8 bolts, heads forward on the bell-gear flange, nuts on the rear face
    head_seat = FLANGE_Y0 - BELL_FLANGE_T
    grip = BELL_FLANGE_T + FLANGE_T + 6.5 + 2.5
    bbolt = hex_bolt(8.0, 13.0, 5.5, grip)
    bnut = F._wrench_head(13.0, 0.0, 6.5, chamfer_bottom=True, dish=0.0) - \
        (bd.Pos(0, 0, -1) * bd.Cylinder(4.0, 9, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    for i in range(BELL_BOLTS):
        b = 22.5 + 45.0 * i
        x, z = ip(b, BELL_PCD_R)
        rad = (x / BELL_PCD_R, 0, z / BELL_PCD_R)
        parts.append(styled(F.place(bbolt, (x, head_seat, z), (0, -1, 0), rad), f"crank:bell_bolt_{i + 1}", FA))
        parts.append(styled(F.place(bnut, (x, FLANGE_Y0 + FLANGE_T, z), (0, 1, 0), rad),
                            f"crank:bell_nut_{i + 1}", FA))
    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    bad = [p.label for p in ps if not geo.sound(p)]
    print(len(ps), "parts", f"{time.time() - t0:.1f}s", "unsound:", bad)
    for p in ps:
        bb = p.bounding_box()
        print(f"{p.label:32s} vol {p.volume:10.0f}  y[{bb.min.Y:7.1f},{bb.max.Y:7.1f}]  "
              f"z[{bb.min.Z:7.1f},{bb.max.Z:7.1f}]  x[{bb.min.X:7.1f},{bb.max.X:7.1f}]")
