"""64 valves, springs, spring-seat cups, retainers, collets, roller finger
followers (with rollers and axles), hydraulic lash adjusters.

Each valve's geometry comes from lib/kin.valve_geom(). Local valve frame:
origin at the seat centre, +Z = stem direction (seat -> tip), +X = engine X.
The spring RIDES the valve (it is captured under the retainer); its bottom
coil sits inside a deep spring-seat cup in the head, so at full lift the
rigid coil is still clear of the cup floor. Followers are built directly in
the engine frame in the YZ plane at the valve's x.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import geo, kin, palette as P, spec as S
from lib.castings import safe_fillet, safe_chamfer, fuse_all

COLLET_Z = (S.VALVE_LEN - 14.0, S.VALVE_LEN - 5.0)
RETAINER_Z = S.VALVE_LEN - 16.0            # retainer top face
SPRING_TOP_Z = RETAINER_Z - 4.0            # spring top coil under the retainer
SPRING_BOTTOM_Z = SPRING_TOP_Z - S.SPRING_INSTALLED_H
CUP_FLOOR_Z = SPRING_BOTTOM_Z - S.VALVE_LIFT - 3.0   # cup floor: spring clears it at full lift (measured: the coil sits ~1.5 lower than its nominal bottom)


def valve_local(kind: str):
    d = S.INTAKE_HEAD_D if kind == "intake" else S.EXHAUST_HEAD_D
    r = d / 2.0
    pts = [(0, -3.0), (r, -3.0), (r, -1.4), (r - 1.6, 0.2), (r - 6.0, 4.5), (4.0, 10.0),
           (S.VALVE_STEM_D / 2, 14.0), (S.VALVE_STEM_D / 2, S.VALVE_LEN), (0, S.VALVE_LEN)]
    prof = bd.make_face(bd.Polyline(*pts, close=True).edges())
    valve = bd.revolve(bd.Plane.XZ * prof, bd.Axis.Z, 360)
    # collet groove
    groove = (bd.Cylinder(4.0, COLLET_Z[1] - COLLET_Z[0], align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
              - bd.Cylinder(2.3, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))).moved(bd.Location((0, 0, COLLET_Z[0])))
    valve = valve - groove
    return valve


def spring_local(turns: float = 6.0):
    r_mean = (S.SPRING_OD - S.SPRING_WIRE_D) / 2.0
    h = S.SPRING_INSTALLED_H - S.SPRING_WIRE_D
    helix = bd.Helix(pitch=h / turns, height=h, radius=r_mean)
    prof = bd.Plane(origin=helix @ 0, z_dir=helix % 0) * bd.Circle(S.SPRING_WIRE_D / 2)
    coil = bd.sweep(prof, path=helix, is_frenet=True)
    return coil.moved(bd.Location((0, 0, SPRING_BOTTOM_Z + S.SPRING_WIRE_D / 2)))


def retainer_local():
    pts = [(3.1, 0), (16.0, 0), (16.0, 3.2), (13.0, 5.0), (8.0, 5.0), (8.0, 9.0), (6.4, 9.0), (6.4, 3.0), (3.1, 3.0)]
    prof = bd.make_face(bd.Polyline(*pts, close=True).edges())
    ret = bd.revolve(bd.Plane.XZ * prof, bd.Axis.Z, 360)
    return ret.moved(bd.Location((0, 0, RETAINER_Z - 3.0)))


def collets_local():
    cone = bd.Cone(4.0, 3.0, COLLET_Z[1] - COLLET_Z[0], align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    cone = cone - bd.Cylinder(S.VALVE_STEM_D / 2 - 0.7, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    cone = cone.moved(bd.Location((0, 0, COLLET_Z[0])))
    slot = bd.Box(0.8, 20, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((0, 0, COLLET_Z[0] - 1)))
    cone = cone - slot
    halves = []
    for sx in (-1, 1):
        keep = bd.Box(20, 20, 20, align=(bd.Align.MIN if sx > 0 else bd.Align.MAX, bd.Align.CENTER, bd.Align.MIN)).moved(
            bd.Location((0, 0, COLLET_Z[0] - 1)))
        halves.append(cone & keep)
    return halves


def cup_local():
    """Spring-seat cup pressed into the head: floor + a skirt hiding the
    spring's travel; bore for the stem/guide."""
    od = S.SPRING_OD + 3.0
    cup = bd.Cylinder(od / 2, SPRING_BOTTOM_Z + 2.0 - CUP_FLOOR_Z + 2.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    inner = bd.Cylinder(S.SPRING_OD / 2 + 0.4, 60, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, 2.0)))
    cup = cup - inner
    cup = cup - bd.Cylinder(6.0, 60, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((0, 0, -1)))
    return cup.moved(bd.Location((0, 0, CUP_FLOOR_Z - 2.0)))


def guide_local():
    g = bd.Cylinder(6.0, 34.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) - bd.Cylinder(
        S.VALVE_STEM_D / 2 + 0.05, 40, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return g.moved(bd.Location((0, 0, CUP_FLOOR_Z - 20.0)))


_LOCAL = {}


def _local(kind):
    if kind not in _LOCAL:
        _LOCAL[kind] = {
            "valve": valve_local(kind),
            "spring": spring_local(),
            "retainer": retainer_local(),
            "collets": collets_local(),
            "cup": cup_local(),
            "guide": guide_local(),
        }
    return _LOCAL[kind]


def valve_plane(g: kin.ValveGeom, theta: float = 0.0) -> bd.Plane:
    lift = kin.valve_lift(g.cyl, g.kind, theta)
    origin = (g.x, g.seat[0] - lift * g.v[0], g.seat[1] - lift * g.v[1])
    return geo.plane(origin, g.axis3, (1, 0, 0))


def seat_plane(g: kin.ValveGeom) -> bd.Plane:
    return geo.plane(g.point3(g.seat), g.axis3, (1, 0, 0))


def follower(g: kin.ValveGeom, theta: float = 0.0):
    """Finger follower + roller + axle in the engine frame at crank angle theta."""
    lift, eps, roller, pad = kin.follower_state(g, theta)
    piv = g.pivot
    # build at rest (eps = 0) in the YZ plane, then rotate about the pivot by eps
    p0 = g.pad0
    r0 = g.roller0
    d = kin.norm(kin.sub(p0, piv))
    n = (-d[1], d[0])
    # n must point AWAY from the valve (up the bank), whichever way d runs
    upb = S.bank_up(S.CYLINDERS[g.cyl - 1].bank)
    if kin.dot(n, (upb[1], upb[2])) < 0:
        n = (-n[0], -n[1])
    L = math.dist(p0, piv)
    t = 9.5
    # side plates: a slab following pivot -> pad, beam depth t, offset so its top passes just under the roller axle
    def slab(x0, x1, top_off):
        # the plates start just past the pivot ball (R 5) so they never clip it;
        # the cup block bridges them to the ball
        s_start = 6.5 / L
        pts2 = []
        for s_, k in ((s_start, top_off), (1.0, top_off), (1.0, top_off - t), (s_start, top_off - t)):
            base = kin.add(piv, kin.mul(d, s_ * L))
            pts2.append(kin.add(base, kin.mul(n, k)))
        return geo.prism_yz(_ccw(pts2), x0, x1)
    # the roller centre sits above/below the pivot->pad line by this much (signed along n)
    roll_off = kin.dot(kin.sub(r0, piv), n)
    # plates: 9.5 deep, their top 6.5 above the roller centre so the cam's base
    # circle (8 above the roller centre) and the lobe flank stay clear, and
    # never higher than that even when the roller sits below the pivot-pad line
    top_off = roll_off + 5.5
    # plates on both sides of the roller
    half_gap = S.ROLLER_W / 2 + 0.6
    plate_t = 2.6
    body = fuse_all([slab(g.x - half_gap - plate_t, g.x - half_gap, top_off),
                     slab(g.x + half_gap, g.x + half_gap + plate_t, top_off)])
    # bridges: pivot socket block and pad block spanning the full width
    socket_c = piv
    # The socket is a CUP over the ball: the spherical shell is kept only on
    # the follower's side of a plane 1 mm below the ball's equator (the ball
    # side of the adjuster's neck), so it never reaches the adjuster body and
    # its rim stays clear of the neck through the follower's +/- 7 deg rock.
    c_ = S.CYLINDERS[g.cyl - 1]
    up3 = S.bank_up(c_.bank)
    sock = bd.Sphere(S.PIVOT_BALL_R + 4.5).moved(bd.Location((g.x, socket_c[0], socket_c[1])))
    sock = sock & bd.Box(2 * (half_gap + plate_t), 60, 60, align=(bd.Align.CENTER,) * 3).moved(bd.Location((g.x, piv[0], piv[1])))
    keep = bd.Box(200, 200, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    keep = geo.locate(keep, (g.x, piv[0] - 1.0 * up3[1], piv[1] - 1.0 * up3[2]), up3, (1, 0, 0))
    sock = sock & keep
    sock = sock - bd.Sphere(S.PIVOT_BALL_R + 0.05).moved(bd.Location((g.x, socket_c[0], socket_c[1])))
    padc = p0
    padblock = geo.cyl_x(g.x - half_gap - plate_t, g.x + half_gap + plate_t, 2 * S.PAD_R, padc[0], padc[1])
    body = fuse_all([body, sock, padblock])
    # roller and axle
    rollr = geo.cyl_x(g.x - S.ROLLER_W / 2, g.x + S.ROLLER_W / 2, 2 * S.ROLLER_R, r0[0], r0[1])
    axle = geo.cyl_x(g.x - half_gap - plate_t - 0.5, g.x + half_gap + plate_t + 0.5, 6.0, r0[0], r0[1])
    body = body - geo.cyl_x(g.x - 40, g.x + 40, 6.1, r0[0], r0[1])
    rollr = rollr - geo.cyl_x(g.x - 40, g.x + 40, 6.1, r0[0], r0[1])
    if abs(eps) > 1e-9:
        ax = bd.Axis((g.x, piv[0], piv[1]), (1, 0, 0))
        body = body.rotate(ax, eps)
        rollr = rollr.rotate(ax, eps)
        axle = axle.rotate(ax, eps)
    return body, rollr, axle


def _ccw(pts):
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if area > 0 else list(reversed(pts))


def hla(g: kin.ValveGeom):
    c = S.CYLINDERS[g.cyl - 1]
    m_p, _ = S.bank_of_point_m_h(c.bank, (0, g.pivot[0], g.pivot[1]))
    top = g.point3(g.pivot)
    up3 = S.bank_up(c.bank)
    bot = S.bank_point(c.bank, g.x, m_p, S.FOLLOWER_H_BAND - 32.0)
    # body ends 3.5 mm under the ball centre; a Ø6.5 neck carries the ball.
    # The follower's cup (outer R 9.5, rim 1 mm below the equator) clears the
    # body top by 2.5 mm and the neck radially by 1.5 mm at any rock angle.
    shoulder = (top[0] - 3.5 * up3[0], top[1] - 3.5 * up3[1], top[2] - 3.5 * up3[2])
    body = geo.cyl_along(bot, shoulder, 12.0)
    neck = geo.cyl_along(shoulder, top, 6.5)
    ball = bd.Sphere(S.PIVOT_BALL_R).moved(bd.Location(top))
    return fuse_all([body, neck, ball])


def valve_tag(g: kin.ValveGeom) -> str:
    return f"{g.cyl}_{'in' if g.kind == 'intake' else 'ex'}{'f' if g.side > 0 else 'r'}"


def build_valve(g: kin.ValveGeom, theta: float = 0.0):
    tag = valve_tag(g)
    loc = _local(g.kind)
    vp = valve_plane(g, theta).location
    sp = seat_plane(g).location
    out = [
        P.style(vp * loc["valve"], f"valve:{tag}", P.MACHINED_STEEL),
        P.style(vp * loc["spring"], f"valve_spring:{tag}", P.STEEL_BLUE),
        P.style(vp * loc["retainer"], f"retainer:{tag}", P.TITANIUM_DARK),
        P.style(vp * loc["collets"][0], f"collet:{tag}_a", P.STEEL_DARK),
        P.style(vp * loc["collets"][1], f"collet:{tag}_b", P.STEEL_DARK),
        P.style(sp * loc["cup"], f"spring_cup:{tag}", P.MACHINED_STEEL),
        P.style(sp * loc["guide"], f"valve_guide:{tag}", P.BRASS),
    ]
    body, rollr, axle = follower(g, theta)
    out.append(P.style(body, f"follower:{tag}", P.MACHINED_STEEL))
    out.append(P.style(rollr, f"roller:{tag}", P.STEEL))
    out.append(P.style(axle, f"roller_axle:{tag}", P.STEEL_DARK))
    out.append(P.style(hla(g), f"lash_adjuster:{tag}", P.STEEL_DARK))
    return out


def build(theta: float = 0.0, cylinders=range(1, 17)):
    parts = []
    for cyl in cylinders:
        for kind in ("intake", "exhaust"):
            for side in (-1, 1):
                parts += build_valve(kin.valve_geom(cyl, kind, side), theta)
    return parts
