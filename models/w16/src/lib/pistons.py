"""Pistons, rings, wrist pins, circlips, connecting rods, rod bolts, rod shells.

Local frames:
  piston  origin = wrist-pin centre, +Z = bore axis (toward the head), +X = engine X.
          The crown is a WEDGE tilted `crown_tilt` deg about local X so that at
          TDC it lies parallel to (and just under) the inclined deck — the VR
          piston's signature.
  rod     origin = big-end centre, +Z toward the small end, +X = engine X.
Placement comes from lib/kin.py at theta = 0.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import fasteners as F, geo, kin, palette as P, spec as S
from lib.castings import safe_fillet, safe_chamfer, fuse_all, is_sound

PISTON_R = S.BORE / 2.0 - 0.05
SKIRT_BOTTOM = -(S.PISTON_H - S.PISTON_CH)      # -22
RING_LAND_BOTTOM = 12.0                          # below the crown centre
PIN_BOSS_D = 34.0
PIN_BOSS_HALF = 31.0
RELIEF_CLEAR = 5.0                               # crown kept this far from every valve seat plane at TDC
RELIEF_DEPTH = 3.0                               # valve pocket depth below the crown
ROD_CLEAR_R = 19.5                               # small end is R 18 about the pin axis
ROD_CLEAR_HALF = 11.6                            # small end is 21 wide
RIB_X, RIB_T = 14.5, 4.0                         # boss-to-skirt struts, clear of the rod


def _oil_drains():
    """Eight Ø3 drains angled 45 deg out of the oil-ring groove into the
    underside cavity, placed on the two skirt panels the windows leave."""
    holes = []
    for phi in (60.0, 80.0, 100.0, 120.0, 240.0, 260.0, 280.0, 300.0):
        a = math.radians(phi)
        p0 = (41.5 * math.cos(a), 41.5 * math.sin(a), 18.2)
        p1 = (32.0 * math.cos(a), 32.0 * math.sin(a), 8.7)
        holes.append(geo.cyl_along(p0, p1, 3.0))
    return holes


def crown_tilt(cyl: int) -> float:
    """deg about local X: the deck normal is the bore axis rotated by this."""
    c = S.CYLINDERS[cyl - 1]
    return S.bank_angle(c.bank) - c.angle


def piston_plane(cyl: int, theta: float = 0.0) -> bd.Plane:
    c = S.CYLINDERS[cyl - 1]
    st = kin.piston(cyl, theta)
    return geo.plane((c.x, st.small_end[0], st.small_end[1]), c.axis, (1, 0, 0))


def rod_plane(cyl: int, theta: float = 0.0) -> bd.Plane:
    c = S.CYLINDERS[cyl - 1]
    st = kin.piston(cyl, theta)
    return geo.plane((c.x, st.pin[0], st.pin[1]), (0.0, st.rod_dir[0], st.rod_dir[1]), (1, 0, 0))


def build_piston_local(cyl: int):
    d = math.radians(crown_tilt(cyl))
    body = bd.Cylinder(PISTON_R, 40.0 - SKIRT_BOTTOM, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, SKIRT_BOTTOM)))
    # wedge crown: remove everything above the plane through (0,0,CH) with normal (0,-sin d,cos d)
    cutter = bd.Box(200, 200, 60, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    nrm = (0.0, -math.sin(d), math.cos(d))
    cutter = geo.locate(cutter, (0, 0, S.PISTON_CH), nrm, (1, 0, 0))
    body = body - cutter
    # crisp top land: a 0.8 mm break on the crown edge, cut before anything else
    # touches the OD so it is one clean ellipse
    body, _ = safe_chamfer(body, [e for e in body.edges() if e.center().Z > S.PISTON_CH - 6.0], 0.8, min_length=0.3)
    # forged crown: a shallow spherical dish, 0.9 mm at the centre, tangent to
    # the crown plane at r 22 so it never leaves an edge of its own
    dish_r, dish_d = 22.0, 0.9
    sph = (dish_r ** 2 + dish_d ** 2) / (2 * dish_d)
    body = body - bd.Sphere(sph).moved(bd.Location(
        (nrm[0] * (sph - dish_d), nrm[1] * (sph - dish_d), S.PISTON_CH + nrm[2] * (sph - dish_d))))
    # ring grooves
    grooves = []
    for depth, w in S.RING_GROOVES:
        g = bd.Cylinder(PISTON_R + 1.0, w, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
            bd.Location((0, 0, S.PISTON_CH - depth)))
        g = g - bd.Cylinder(PISTON_R - 4.0, w + 1, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
            bd.Location((0, 0, S.PISTON_CH - depth + 0.5)))
        grooves.append(g)
    body = body - grooves
    # hollow: bore out the underside, leave a 6 mm crown and 3.5 mm skirt
    under = bd.Cylinder(PISTON_R - 3.5, 100.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
        bd.Location((0, 0, S.PISTON_CH - RING_LAND_BOTTOM - 3.0)))
    body = body - under
    # slipper skirt: open the +-X sides below the ring lands
    for sx in (-1, 1):
        win = bd.Box(60, 62, 40, align=(bd.Align.MIN if sx > 0 else bd.Align.MAX, bd.Align.CENTER, bd.Align.MIN)).moved(
            bd.Location((sx * 20.0, 0, SKIRT_BOTTOM - 1)))
        body = body - win
    # pin bosses, tied to the skirt by two forged struts
    boss = bd.Cylinder(PIN_BOSS_D / 2, 2 * PIN_BOSS_HALF, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
    boss = boss.rotate(bd.Axis.Y, 90)
    strut = bd.Box(2 * PIN_BOSS_HALF, 20.0, 22.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    ribs = [(bd.Box(RIB_T, 100.0, 17.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((sx * RIB_X, 0, 0)))
        & bd.Cylinder(PISTON_R - 2.4, 17.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
        for sx in (-1, 1)]
    body = fuse_all([body, boss, strut] + ribs)
    # rod clearance: the small end is R 18 about the pin axis and swings inside
    # the piston, so the bosses are split and the crown underside scalloped
    body = body - (bd.Cylinder(ROD_CLEAR_R, 2 * ROD_CLEAR_HALF, align=(bd.Align.CENTER,) * 3)
                   .rotate(bd.Axis.Y, 90))
    body = body - _oil_drains()
    body = body - bd.Cylinder(S.WRIST_PIN_D / 2, 120, align=(bd.Align.CENTER,) * 3).rotate(bd.Axis.Y, 90)
    # circlip grooves
    for sx in (-1, 1):
        cg = (bd.Cylinder(S.WRIST_PIN_D / 2 + 1.2, 1.4, align=(bd.Align.CENTER,) * 3)
              .rotate(bd.Axis.Y, 90).moved(bd.Location((sx * (PIN_BOSS_HALF - 2.5), 0, 0))))
        body = body - cg
    body, _ = safe_fillet(body, [e for e in body.edges() if e.center().Z < SKIRT_BOTTOM + 0.5], 1.5)
    # break the skirt-window edges so the slipper reads forged, not sawn
    body, _ = safe_fillet(body, [e for e in body.edges()
                                 if 19.4 < abs(e.center().X) < 20.6 and e.length > 4.0], 2.0, min_r=0.5)
    body = _valve_reliefs(body, cyl)
    return body


def _valve_reliefs(body, cyl: int):
    """Shallow reliefs under the four valves: the region of the crown within
    RELIEF_CLEAR of each valve's seat plane (measured along the valve axis,
    with the piston at its firing TDC) is removed, so a valve cracked open at
    overlap TDC can never touch the crown."""
    c = S.CYLINDERS[cyl - 1]
    pp = piston_plane(cyl, c.tdc)
    # The pockets are BOUNDED to RELIEF_DEPTH below the crown. Unbounded (as
    # they were) each cutter reached 40 mm down the piston and, because these
    # seats sit ~15 mm clear of the crown at TDC, took the whole crown with it:
    # the piston had four holes straight through it. Axes, diameters and
    # positions are untouched.
    dn = math.radians(crown_tilt(cyl))
    floor = bd.Box(300, 300, 90, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    nd = (0.0, -math.sin(dn), math.cos(dn))
    floor = geo.locate(floor, (0, -nd[1] * RELIEF_DEPTH, S.PISTON_CH - nd[2] * RELIEF_DEPTH), nd, (1, 0, 0))
    cutters = []
    for kind in ("intake", "exhaust"):
        d_head = S.INTAKE_HEAD_D if kind == "intake" else S.EXHAUST_HEAD_D
        for side in (-1, 1):
            g = kin.valve_geom(cyl, kind, side)
            seat = bd.Vector(*g.point3(g.seat))
            v = bd.Vector(*g.axis3)
            seat_l = pp.to_local_coords(seat)
            v_l = pp.to_local_coords(seat + v) - seat_l
            top = seat_l - v_l * RELIEF_CLEAR             # plane RELIEF_CLEAR under the seat, along -v
            cutter = bd.Cylinder(d_head / 2 + 1.5, 40.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
            cutters.append(geo.locate(cutter, (top.X, top.Y, top.Z), (v_l.X, v_l.Y, v_l.Z), (1, 0, 0)) & floor)
    cutters = [c for c in cutters if c is not None and c.volume > 1e-3]
    if not cutters:
        return body
    out = body - cutters
    return out if geo.sound(out) else body


def build_wrist_pin_local():
    pin = bd.Cylinder(S.WRIST_PIN_D / 2, S.WRIST_PIN_LEN, align=(bd.Align.CENTER,) * 3)
    pin = pin - bd.Cylinder(6.5, S.WRIST_PIN_LEN + 2, align=(bd.Align.CENTER,) * 3)
    pin, _ = safe_chamfer(pin, pin.edges(), 1.0)
    return pin.rotate(bd.Axis.Y, 90)


def build_circlip_local(sx: int):
    ring = (bd.Cylinder(S.WRIST_PIN_D / 2 + 1.1, 1.2, align=(bd.Align.CENTER,) * 3)
            - bd.Cylinder(S.WRIST_PIN_D / 2 - 0.8, 2, align=(bd.Align.CENTER,) * 3))
    gap = bd.Box(3.0, 4.0, 3.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER)).moved(bd.Location((0, 8, 0)))
    ring = ring - gap
    return ring.rotate(bd.Axis.Y, 90).moved(bd.Location((sx * (PIN_BOSS_HALF - 2.5), 0, 0)))


def build_rings_local():
    """Three piston rings as separate parts (compression x2, oil control)."""
    out = []
    for k, (depth, w) in enumerate(S.RING_GROOVES):
        r_out = PISTON_R + 0.02              # 42.97: rings ride the wall, never into it (bore R 43)
        ring = (bd.Cylinder(r_out, w - 0.15, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
                - bd.Cylinder(PISTON_R - 3.6, w + 1, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)))
        ring = ring.moved(bd.Location((0, 0, S.PISTON_CH - depth - 0.05)))
        gap = bd.Box(1.0, 6.0, 5.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER)).moved(
            bd.Location((0, PISTON_R - 3, S.PISTON_CH - depth - w / 2))).rotate(bd.Axis.Z, 40 + 120 * k)
        out.append(ring - gap)
    return out


BIG_END_OD = 82.0
SHELL_T = 1.5
SMALL_END_OD = 36.0
SMALL_END_W = 21.0
BOLT_Y = 33.0
BOLT_BOSS_R = 8.3       # keeps the boss corner at hypot(41.3, 11) = 42.7 < 43.3
BOLT_D = 9.0
CBORE_R = 7.25          # shallow counterbore: the 12-point head measures 13.95 across corners
CBORE_DEPTH = 2.5
SPLIT_BAND = 0.6        # machined skin taken off the OD either side of the split face


def build_rod_local():
    """Rod body (upper) and cap (lower) + bolts + shells, all in the rod frame."""
    w = S.ROD_BIG_END_W
    big = bd.Cylinder(BIG_END_OD / 2, w, align=(bd.Align.CENTER,) * 3).rotate(bd.Axis.Y, 90)
    # bolt bosses hug the split plane (z +/-11) so no corner of the big end
    # reaches further than 43 mm from the pin centre: the rod sweeps R 86 about
    # the crank axis and the bays are cleared to CRANKCASE_CLEAR_R = 88
    bosses = [bd.Cylinder(BOLT_BOSS_R, 22.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
              .moved(bd.Location((0, sy * BOLT_Y, 0.0))) for sy in (-1, 1)]
    bridge = bd.Box(w, 2 * BOLT_Y, 22.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER))
    big = fuse_all([big, bridge] + bosses)
    big = big - bd.Cylinder(BIG_END_OD / 2 - 11.0, w + 2, align=(bd.Align.CENTER,) * 3).rotate(bd.Axis.Y, 90)
    # beam: lofted I-section, tapered in both planes. Flanges 4.5 -> 4.0 thick
    # over a 5.5 -> 5.0 web, which is the ratio a forged titanium rod actually
    # runs; the outer envelope is unchanged at the big end (19 x 26) because the
    # first 14 mm of beam is the tightest part of the crankcase sweep.
    z0, z1 = 31.0, S.ROD_LEN - 14.0      # beam starts outside the shell OD (28.5) and the pin (R 27)
    outer = bd.loft([bd.Plane.XY.offset(z0) * bd.Rectangle(w, 26.0),
                     bd.Plane.XY.offset(z1) * bd.Rectangle(w - 2.0, 20.0)])
    pockets = []
    for sx in (-1, 1):
        pk = bd.loft([bd.Plane.XY.offset(z0 + 4) * bd.Pos(sx * 7.2, 0) * bd.Rectangle(9.0, 26.0 - 9.0),
                      bd.Plane.XY.offset(z1 - 4) * bd.Pos(sx * 6.75, 0) * bd.Rectangle(8.5, 20.0 - 8.0)])
        pockets.append(pk)
    beam = outer - pockets
    beam, _ = safe_fillet(beam, [e for e in beam.edges() if 2 < e.center().Z < S.ROD_LEN - 2], 2.0, min_r=1.0)
    small = bd.Cylinder(SMALL_END_OD / 2, SMALL_END_W, align=(bd.Align.CENTER,) * 3).rotate(bd.Axis.Y, 90).moved(
        bd.Location((0, 0, S.ROD_LEN)))
    rod = fuse_all([big, beam, small])
    rod = rod - bd.Cylinder(S.WRIST_PIN_D / 2 + 1.5, 60, align=(bd.Align.CENTER,) * 3).rotate(bd.Axis.Y, 90).moved(
        bd.Location((0, 0, S.ROD_LEN)))
    # a machined skin either side of the split face, so the joint reads as a
    # ground parting line rather than a seam in a turned cylinder
    band = (geo.cyl_x(-12, 12, 2 * (BIG_END_OD / 2 + 20)) - geo.cyl_x(-13, 13, BIG_END_OD - 2 * SPLIT_BAND)) & bd.Box(
        30, 200, 5.0, align=(bd.Align.CENTER,) * 3)
    # pin oiling: a 4 mm drilling down the crown side of the small end into the bush bore
    oil = bd.Cylinder(2.0, 16.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, S.ROD_LEN + 6.0)))
    rod = rod - [band, oil]
    # split: cap is everything below z = 0
    lower = bd.Box(100, 200, 100, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
    cap = rod & lower
    body = rod - lower
    # bolt holes through both, with the heads seated in shallow counterbores
    holes = [bd.Cylinder(BOLT_D / 2 + 0.1, 30, align=(bd.Align.CENTER,) * 3).moved(bd.Location((0, sy * BOLT_Y, 0)))
             for sy in (-1, 1)]
    cbores = [bd.Cylinder(CBORE_R, CBORE_DEPTH, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, sy * BOLT_Y, -11.0))) for sy in (-1, 1)]
    # machined balance pad across the bottom of the cap
    pad = bd.Box(30.0, 26.0, 20.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
        bd.Location((0, 0, -(BIG_END_OD / 2 - 0.9))))
    cap = cap - (holes + cbores + [pad])
    body = body - holes
    # ShapeFix both halves: the split-off cap is OCCT-valid here but comes back
    # from the package's exact-shape round trip with invalid topology unless
    # it is healed first (see BUGS.md).
    parts = {"rod": body, "cap": cap}
    bolts = []
    for sy in (-1, 1):
        b = F.twelve_point_bolt(BOLT_D, 18.5)
        bolts.append(geo.locate(b, (0, sy * BOLT_Y, -11.0 + CBORE_DEPTH), (0, 0, -1)))
    parts["bolts"] = bolts
    shells = []
    for half in (1, -1):
        ring = (bd.Cylinder(S.PIN_D / 2 + SHELL_T, w - 2.0, align=(bd.Align.CENTER,) * 3)
                - bd.Cylinder(S.PIN_D / 2 + 0.05, w, align=(bd.Align.CENTER,) * 3)).rotate(bd.Axis.Y, 90)
        cutter = bd.Box(60, 200, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN if half < 0 else bd.Align.MAX))
        shells.append(ring - cutter)
    parts["shells"] = shells
    bush = (bd.Cylinder(S.WRIST_PIN_D / 2 + 1.5, SMALL_END_W - 0.5, align=(bd.Align.CENTER,) * 3)
            - bd.Cylinder(S.WRIST_PIN_D / 2 + 0.05, SMALL_END_W + 1, align=(bd.Align.CENTER,) * 3)).rotate(bd.Axis.Y, 90)
    parts["bush"] = bush.moved(bd.Location((0, 0, S.ROD_LEN)))
    return parts


_ROD_CACHE = {}


def build_cylinder_set(cyl: int, theta: float = 0.0):
    """All moving parts of one cylinder, placed in the engine frame."""
    pp = piston_plane(cyl, theta)
    rp = rod_plane(cyl, theta)
    out = []
    piston = build_piston_local(cyl)
    out.append(P.style(pp.location * piston, f"piston:{cyl}", P.MACHINED))
    for k, ring in enumerate(build_rings_local()):
        out.append(P.style(pp.location * ring, f"piston_ring:{cyl}_{k + 1}", P.MACHINED_STEEL))
    out.append(P.style(pp.location * build_wrist_pin_local(), f"wrist_pin:{cyl}", P.MACHINED_STEEL))
    for sx in (-1, 1):
        out.append(P.style(pp.location * build_circlip_local(sx), f"circlip:{cyl}_{'f' if sx > 0 else 'r'}", P.STEEL_BLUE))
    if "rod" not in _ROD_CACHE:
        _ROD_CACHE["rod"] = build_rod_local()
    r = _ROD_CACHE["rod"]
    out.append(P.style(rp.location * r["rod"], f"rod:{cyl}", P.TITANIUM))
    out.append(P.style(rp.location * r["cap"], f"rod_cap:{cyl}", P.TITANIUM))
    for k, b in enumerate(r["bolts"]):
        out.append(P.style(rp.location * b, f"rod_bolt:{cyl}_{k + 1}", P.STEEL_DARK))
    for k, sh in enumerate(r["shells"]):
        out.append(P.style(rp.location * sh, f"rod_shell:{cyl}_{'upper' if k == 0 else 'lower'}", P.MACHINED_STEEL))
    out.append(P.style(rp.location * r["bush"], f"rod_bush:{cyl}", P.BRASS))
    return out


def build(theta: float = 0.0, cylinders=range(1, 17)):
    parts = []
    for cyl in cylinders:
        parts += build_cylinder_set(cyl, theta)
    return parts
