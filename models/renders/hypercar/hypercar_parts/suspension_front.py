"""Front suspension -- exposed-mechanism jewellery, Formula-car grammar.

Both corners: aerofoil-section upper and lower wishbones, machined-from-billet
uprights with lightening pockets, pushrod to an inboard bell-crank rocker,
inboard coilover with a visible spring and a bronze adjuster perch, a blade
anti-roll bar with drop links, and a front-steer rack with aerofoil tie rods.

All of it hangs off ONE governing structure: the front cradle.  A machined
bulkhead frame stands at the tub face and three tapered rails per side sweep
forward out of it, pinching together into a single machined prow that carries
the tow eye.  In side view that is a long wedge; in plan a tapering triangle;
and every link in the mechanism now starts on that wedge and terminates on the
upright, instead of ending on a mount pad hanging in mid air.  Outriggers carry
the cradle out to the body's inner flank (queried from ``S.body_section_bands``)
so the assembly is visibly bolted into the nose it sits in.

Every joint is a spherical bearing with a bronze housing -- the single warm
accent running through the whole mechanism.

Frame: +X forward, +Y car left, +Z up.  Front hub is (+1350, +/-850, 366.5).
Everything stays inboard of the tyre inner face and inside the arch radius
(``S.FRONT_ARCH_R``) wherever it crosses the wheelhouse.
"""

from __future__ import annotations

import math

from build123d import (
    Align,
    Circle,
    Cone,
    Cylinder,
    Helix,
    Line,
    Location,
    Plane,
    Polyline,
    Pos,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Rot,
    Sphere,
    Spline,
    Vector,
    extrude,
    fillet,
    loft,
    make_face,
    sweep,
)

from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style
from hypercar_parts import palette as P

# ---------------------------------------------------------------------------
# hard points (left corner, y > 0).  Mirrored by ``_p(name, side)``.
# ---------------------------------------------------------------------------

HX = S.FRONT_AXLE_X          # 1350
HZ = S.FRONT_HUB_Z           # 366.45

_HP = {
    # lower wishbone
    "lwb_in_f": (1512.0, 316.0, 172.0),
    "lwb_in_r": (1176.0, 302.0, 163.0),
    "lwb_out": (1352.0, 736.0, 208.0),
    # upper wishbone
    "uwb_in_f": (1472.0, 342.0, 434.0),
    "uwb_in_r": (1214.0, 330.0, 424.0),
    "uwb_out": (1350.0, 700.0, 494.0),
    # pushrod
    "pr_out": (1352.0, 690.0, 240.0),
    "pr_in": (1288.0, 392.0, 468.0),
    # rocker
    "rk_piv": (1288.0, 268.0, 486.0),
    "rk_damp": (1288.0, 212.0, 586.0),
    "rk_arb": (1264.0, 296.0, 386.0),
    # coilover chassis end
    "dmp_ch": (1010.0, 92.0, 494.0),
    # anti-roll bar
    "arb_end": (1428.0, 246.0, 520.0),
    "arb_tip": (1358.0, 300.0, 476.0),
    # steering
    "tie_in": (1470.0, 300.0, 300.0),
    "tie_out": (1446.0, 692.0, 320.0),
}

RACK_X, RACK_Z = 1470.0, 300.0
ARB_X, ARB_Z = 1428.0, 520.0

FWD = Vector(1, 0, 0)
UPZ = Vector(0, 0, 1)


def _p(name, side):
    x, y, z = _HP[name]
    return (x, side * y, z)


def _v(p):
    return Vector(*p) if not isinstance(p, Vector) else p


def _mid(a, b, f=0.5):
    a, b = _v(a), _v(b)
    return a + (b - a) * f


# ---------------------------------------------------------------------------
# framing helpers
# ---------------------------------------------------------------------------


def _plane_at(origin, normal, ref=(1, 0, 0)):
    """Plane whose Z is ``normal`` and whose X is ``ref`` projected onto it."""
    z = _v(normal).normalized()
    x = _v(ref)
    x = x - z * x.dot(z)
    if x.length < 1e-6:
        x = Vector(0, 0, 1) if abs(z.Z) < 0.9 else Vector(1, 0, 0)
        x = x - z * x.dot(z)
    return Plane(origin=_v(origin), x_dir=x.normalized(), z_dir=z)


def _seg(p0, p1, ref=(1, 0, 0)):
    """(plane at p0 with Z along p0->p1, length)."""
    d = _v(p1) - _v(p0)
    return _plane_at(p0, d, ref), d.length


def _shift(pl, t):
    return Plane(origin=pl.origin + pl.z_dir * t, x_dir=pl.x_dir, z_dir=pl.z_dir)


def _rod(p0, p1, r, ref=(1, 0, 0)):
    pl, L = _seg(p0, p1, ref)
    return pl * Cylinder(r, L, align=(Align.CENTER, Align.CENTER, Align.MIN))


# ---------------------------------------------------------------------------
# aerofoil section -- the signature of the whole assembly
# ---------------------------------------------------------------------------

_AF_N = 10


def _aero_sketch(chord, tc=0.34, le=0.32, trunc=0.92):
    """Symmetric teardrop, LEADING edge toward +X (streamwise, nose-first)."""
    xs = [trunc * 0.5 * (1.0 - math.cos(math.pi * i / _AF_N)) for i in range(_AF_N + 1)]

    def yt(t):
        return 5.0 * tc * (
            0.2969 * math.sqrt(t)
            - 0.1260 * t
            - 0.3516 * t * t
            + 0.2843 * t ** 3
            - 0.1036 * t ** 4
        )

    up = [(chord * (le - t), chord * yt(t)) for t in xs]
    lo = [(chord * (le - t), -chord * yt(t)) for t in xs]
    pts = list(reversed(up)) + lo[1:]
    return make_face(Spline(*pts) + Line(pts[-1], pts[0]))


def _aero_member(p0, p1, c0, c1, tc=0.34, t0=48.0, t1=20.0, stub=None,
                 stub1=True, le=0.32):
    """Aerofoil-section link running p0 -> p1.  Returns [fairing, *end_fittings].

    Two rules learned the hard way on this assembly:

    * The fairing is lofted between EXACTLY two sections.  A loft through more
      sections rings between them and the ringing shows up as scalloped
      shading down the arm.
    * The pieces are returned SEPARATELY and never booleaned together.  Fusing
      two of these arms where they cross at the wishbone apex gives OCC a
      near-tangential intersection curve, and the sewn result is visibly
      crumpled along the whole span.  Overlapping solids of one colour read as
      a single part and stay perfectly smooth.

    The section plane is normal to the member and its chord lies as close to
    streamwise (+X) as the member allows.
    """
    pl, L = _seg(p0, p1)
    out = [loft([
        _shift(pl, t0) * _aero_sketch(c0, tc, le),
        _shift(pl, L - t1) * _aero_sketch(c1, tc, le),
    ])]
    # the end fitting must stay strictly INSIDE the fairing it plugs into --
    # a stub fatter than the local half-thickness breaks out through the skin
    # and the two overlapping solids read as a torn, crumpled seam.
    if stub is None:
        stub = 0.72 * 0.5 * c0 * tc
    if stub:
        out.append(_shift(pl, 4.0) * Cone(
            stub * 0.76, stub, t0 + 4.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        ))
        if stub1:
            out.append(_shift(pl, L - t1 - 6.0) * Cone(
                stub, stub * 0.80, t1 + 2.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            ))
    return out


# ---------------------------------------------------------------------------
# jewellery: spherical bearings, rod ends, forks
# ---------------------------------------------------------------------------


def _sph_joint(c, axis, tag, k=1.0):
    """Spherical bearing: bronze race, steel ball, titanium pin. 3 leaves."""
    R, W, BR = 15.5 * k, 17.0 * k, 10.4 * k
    pl = _plane_at(c, axis)
    ring = extrude(pl * (Circle(R) - Circle(BR)), W / 2.0, both=True)
    ball = Pos(*c) * Sphere(BR * 0.985)
    pin = pl * Cylinder(5.4 * k, W + 27.0 * k)
    return [
        style(ring, f"sph_race:{tag}", P.BRONZE),
        style(ball, f"sph_ball:{tag}", P.RIM),
        style(pin, f"sph_pin:{tag}", P.STEEL_DARK),
    ]


def _rod_end(c, axis, shank_dir, tag, k=1.0, shank=52.0):
    """Spherical bearing plus its threaded shank and lock nut. 5 leaves."""
    out = _sph_joint(c, axis, tag, k)
    sd = _v(shank_dir).normalized()
    ps = _plane_at(c, sd)
    body = ps * Cylinder(
        11.0 * k, 24.0 * k, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    stem = _shift(ps, 20.0 * k) * Cylinder(
        7.2 * k, shank - 20.0 * k, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    nut = extrude(
        _shift(ps, shank - 18.0 * k) * RegularPolygon(11.6 * k, 6), 13.0 * k
    )
    out.append(style(body, f"rod_end_body:{tag}", P.ALUMINIUM))
    out.append(style(stem, f"rod_end_stem:{tag}", P.TITANIUM))
    out.append(style(nut, f"rod_end_nut:{tag}", P.BRONZE_DARK))
    return out


def _fork(c, axis, base, tag, colour=None, r_tip=20.0, r_base=14.0, t=7.0,
          gap=19.0, lighten=True):
    """Two-tine clevis straddling a bearing at ``c``, rooted at ``base``."""
    colour = colour or P.ALUMINIUM
    d = _v(base) - _v(c)
    L = d.length
    pl = _plane_at(c, axis, ref=d)
    sk = (
        Circle(r_tip)
        + Pos(L, 0) * Circle(r_base)
        + Pos(L / 2.0, 0) * Rectangle(L, 1.55 * min(r_tip, r_base))
    )
    if lighten and L > 40.0:
        sk = sk - Pos(L * 0.56, 0) * Circle(0.42 * min(r_tip, r_base))
    out = []
    for i, off in enumerate((gap / 2.0, -gap / 2.0 - t)):
        plate = extrude(_shift(pl, off) * sk, t)
        out.append(style(plate, f"clevis:{tag}_{i}", colour))
    return out


def _pad(c, axis, base, tag, colour=None, gap=19.0, t=7.0):
    """Machined chassis mounting foot closing off a clevis root."""
    colour = colour or P.TITANIUM
    d = _v(base) - _v(c)
    pl = _plane_at(base, axis, ref=d)
    sk = RectangleRounded(gap + 2 * t + 24.0, 48.0, 9.0)
    for dx in ((gap + 2 * t + 24.0) * 0.33, -(gap + 2 * t + 24.0) * 0.33):
        for dy in (15.0, -15.0):
            sk = sk - Pos(dx, dy) * Circle(4.6)
    plr = Plane(origin=pl.origin, x_dir=pl.z_dir, z_dir=pl.x_dir)
    blk = extrude(plr * sk, 8.0, both=True)
    return [style(blk, f"mount_pad:{tag}", colour)]


# ---------------------------------------------------------------------------
# wishbones
# ---------------------------------------------------------------------------


def _wishbone(side, kind):
    """One aerofoil wishbone: two tapered legs into a machined outboard yoke."""
    tag = ("fl" if side > 0 else "fr") + "_" + kind
    pf = _p(f"{kind}_in_f", side)
    pr = _p(f"{kind}_in_r", side)
    po = _p(f"{kind}_out", side)

    if kind == "lwb":
        c0, c1, tc = 78.0, 54.0, 0.40
        t0, t1 = 58.0, 10.0
        yoke_r, yoke_h = 28.0, 46.0
    else:
        c0, c1, tc = 66.0, 46.0, 0.42
        t0, t1 = 52.0, 9.0
        yoke_r, yoke_h = 24.0, 40.0

    kp = (_v(_p("uwb_out", side)) - _v(_p("lwb_out", side))).normalized()

    leaves = []
    parts = []
    for nm, pin in (("f", pf), ("r", pr)):
        parts += _aero_member(pin, po, c0, c1, tc, t0, t1, stub1=False)
    parts.append(_plane_at(po, kp) * Cylinder(yoke_r, yoke_h))
    for i, part in enumerate(parts):
        leaves.append(style(part, f"{kind}_arm:{tag}_{i}", P.ALUMINIUM))

    # inboard spherical bearings, pressed into the arm ends, in chassis clevises
    for nm, pin in (("f", pf), ("r", pr)):
        axis = (_v(pr) - _v(pf)).normalized()
        inb = Vector(0, -side, 0)
        inb = (inb - axis * inb.dot(axis)).normalized()
        base = _v(pin) + inb * 48.0
        leaves += _sph_joint(pin, axis, f"{tag}_{nm}")
        leaves += _fork(pin, axis, base, f"{tag}_{nm}", colour=P.ALUMINIUM_DARK)
        leaves += _pad(pin, axis, base, f"{tag}_{nm}")

    # outboard ball joint into the upright: bronze race ring on each face of
    # the yoke, steel ball on the kingpin axis
    for s in (1, -1):
        ring = extrude(
            _plane_at(_v(po) + kp * (s * (yoke_h / 2.0 - 5.0)), kp)
            * (Circle(yoke_r) - Circle(yoke_r - 9.0)),
            6.0 * s,
        )
        leaves.append(
            style(ring, f"{kind}_bj_race:{tag}_{'a' if s > 0 else 'b'}", P.BRONZE)
        )
    stud = _plane_at(po, kp) * Cylinder(10.0, yoke_h + 14.0)
    leaves.append(style(stud, f"{kind}_bj_stud:{tag}", P.TITANIUM))
    return leaves


# ---------------------------------------------------------------------------
# upright -- billet, pocketed
# ---------------------------------------------------------------------------

_UP_OUTLINE = [
    (-36, -164), (40, -164), (62, -116), (76, -26),
    (60, 50), (34, 116), (28, 166), (-28, 166),
    (-34, 116), (-58, 50), (-70, -26), (-56, -116),
]

_UP_T = 23.0        # half thickness of the main web
_POCKET_D = 15.0


def _upright(side):
    tag = "fl" if side > 0 else "fr"
    lo = _p("lwb_out", side)
    uo = _p("uwb_out", side)
    O = _mid(lo, uo)
    kp = (_v(uo) - _v(lo)).normalized()
    n = kp.cross(FWD)                       # plate normal, outboard on the left
    pl = Plane(origin=O, x_dir=(-1, 0, 0), z_dir=n)

    pts = [(-f, u) for (f, u) in _UP_OUTLINE]
    face = make_face(Polyline(*pts, close=True))
    try:
        face = fillet(face.vertices(), 15)
    except Exception:  # pragma: no cover
        pass
    solid = extrude(pl * face, _UP_T, both=True)

    # bearing barrel around the hub axis (global Y)
    hub_y = side * 744.0
    barrel = Pos(HX, hub_y, HZ) * Rot(-90, 0, 0) * Cylinder(52.0, 96.0)
    solid = solid + barrel

    # hub bore
    bore = Pos(HX, side * 730.0, HZ) * Rot(-90, 0, 0) * Cylinder(33.0, 260.0)
    solid = solid - bore

    # lightening pockets, both faces
    pockets = [
        (Pos(0, 112) * RectangleRounded(44, 66, 15)),
        (Pos(-1, 46) * RectangleRounded(30, 34, 12)),
        (Pos(-26, -118) * RectangleRounded(38, 58, 13)),
        (Pos(28, -118) * RectangleRounded(40, 58, 13)),
        (Pos(0, -62) * RectangleRounded(84, 26, 11)),
    ]
    for sk in pockets:
        for base in (_UP_T - _POCKET_D, -_UP_T - 3.0):
            solid = solid - extrude(_shift(pl, base) * sk, _POCKET_D + 3.0)

    # steering arm reaching forward to the tie-rod ball
    to = _p("tie_out", side)
    root = (1362.0, side * 706.0, 344.0)
    pa, La = _seg(root, to, ref=(0, 0, 1))
    arm = loft([
        pa * RectangleRounded(78, 26, 11),
        _shift(pa, La * 0.55) * RectangleRounded(46, 24, 10),
        _shift(pa, La) * RectangleRounded(32, 22, 10),
    ])
    solid = solid + arm

    leaves = [style(solid, f"upright:{tag}", P.TITANIUM)]

    # bronze bearing retainer on the outboard face of the carrier barrel --
    # the warm ring the wheel spokes will frame
    retainer = extrude(
        Plane(origin=(HX, side * 786.0, HZ), x_dir=(1, 0, 0), z_dir=(0, side, 0))
        * (Circle(52.0) - Circle(38.0)),
        7.0,
    )
    leaves.append(style(retainer, f"hub_retainer:{tag}", P.BRONZE_DARK))

    # wheel hub flange + bronze centre-lock collar
    flange = Pos(HX, side * 788.0, HZ) * Rot(-90, 0, 0) * Cylinder(45.0, 16.0)
    collar = extrude(
        Plane(origin=(HX, side * 800.0, HZ), x_dir=(1, 0, 0), z_dir=(0, side, 0))
        * RegularPolygon(31.0, 12),
        22.0,
    )
    leaves.append(style(flange, f"hub_flange:{tag}", P.RIM))
    leaves.append(style(collar, f"hub_collar:{tag}", P.BRONZE))

    # pushrod lug rising off the lower ball joint
    po = _p("lwb_out", side)
    pr_out = _p("pr_out", side)
    leaves += _fork(
        pr_out, FWD, po, f"{tag}_pushrod_lug", colour=P.ALUMINIUM,
        r_tip=22.0, r_base=30.0, t=9.0, gap=20.0,
    )
    return leaves


# ---------------------------------------------------------------------------
# rocker (bell crank) + its pedestal
# ---------------------------------------------------------------------------

_RK_T = 16.0        # half thickness
_RK_SLOT = 19.0


def _rocker(side):
    tag = "fl" if side > 0 else "fr"
    piv = _p("rk_piv", side)
    lobes = {
        "push": _p("pr_in", side),
        "damp": _p("rk_damp", side),
        "arb": (1288.0, _HP["rk_arb"][1] * side, _HP["rk_arb"][2]),
    }
    x0 = piv[0]
    pl = Plane.YZ.offset(x0)

    pv = Vector(piv[1], piv[2], 0)
    dirs, tips = {}, {}
    for k, pt in lobes.items():
        d = Vector(pt[1], pt[2], 0) - pv
        dirs[k] = d.normalized()
        tips[k] = pv + d + dirs[k] * 22.0

    # three-lobe crank: hub disc, three tapered arms, a round eye on each
    sk = Pos(pv.X, pv.Y) * Circle(41.0)
    for k, pt in lobes.items():
        c = Vector(pt[1], pt[2], 0)
        d = dirs[k]
        L = (c - pv).length
        mid = pv + d * (L / 2.0)
        ang = math.degrees(math.atan2(d.Y, d.X))
        sk = sk + Pos(c.X, c.Y) * Circle(25.0)
        sk = sk + Location((mid.X, mid.Y, 0), (0, 0, ang)) * Rectangle(L, 37.0)
    try:
        sk = fillet(sk.vertices(), 13)
    except Exception:  # pragma: no cover
        pass
    plate = extrude(pl * sk, _RK_T, both=True)

    # pivot boss
    boss = _plane_at(piv, FWD) * Cylinder(35.0, 58.0)
    plate = plate + boss

    # drilled lightening in each arm
    for k, pt in lobes.items():
        c = Vector(pt[1], pt[2], 0)
        d = dirs[k]
        hole = pv + d * ((c - pv).length * 0.60)
        plate = plate - extrude(
            _shift(pl, -_RK_T - 4.0) * (Pos(hole.X, hole.Y) * Circle(8.5)),
            2 * _RK_T + 8.0,
        )

    # fork slots at each lobe
    for k, pt in lobes.items():
        d = dirs[k]
        c = Vector(pt[1], pt[2], 0)
        slot_c = c + d * 20.0
        sk_slot = Location(
            (slot_c.X, slot_c.Y, 0), (0, 0, math.degrees(math.atan2(d.Y, d.X)))
        ) * Rectangle(92, 44)
        plate = plate - extrude(_shift(pl, -_RK_SLOT / 2.0) * sk_slot, _RK_SLOT)

    # bores
    plate = plate - _plane_at(piv, FWD) * Cylinder(15.0, 120.0)

    leaves = [style(plate, f"rocker:{tag}", P.ALUMINIUM)]

    shaft = _plane_at(piv, FWD) * Cylinder(14.0, 96.0)
    leaves.append(style(shaft, f"rocker_shaft:{tag}", P.TITANIUM))
    for s in (1, -1):
        nut = extrude(
            _shift(_plane_at(piv, FWD), s * 48.0 - (7.0 if s < 0 else 0.0))
            * RegularPolygon(19.0, 6),
            7.0,
        )
        leaves.append(style(nut, f"rocker_nut:{tag}_{'a' if s > 0 else 'b'}", P.BRONZE))

    # pedestal: two shear plates dropping to a chassis pad
    base = (x0, side * 118.0, 336.0)
    bp = Vector(base[1], base[2], 0)
    L = (bp - pv).length
    ang = math.degrees(math.atan2((bp - pv).Y, (bp - pv).X))
    ped_sk = (
        Pos(pv.X, pv.Y) * Circle(30.0)
        + Pos(bp.X, bp.Y) * Circle(26.0)
        + Location(((pv.X + bp.X) / 2, (pv.Y + bp.Y) / 2, 0), (0, 0, ang))
        * Rectangle(L, 34)
    )
    ped_sk = ped_sk - Location(
        ((pv.X + bp.X) / 2, (pv.Y + bp.Y) / 2, 0), (0, 0, ang)
    ) * (Pos(0, 0) * Circle(11.0))
    for i, off in enumerate((_RK_T + 13.0, -_RK_T - 24.0)):
        pedestal = extrude(_shift(pl, off) * ped_sk, 11.0)
        leaves.append(style(pedestal, f"rocker_pedestal:{tag}_{i}", P.ALUMINIUM_DARK))
    pad_sk = RectangleRounded(86.0, 72.0, 15.0)
    for dx, dy in ((29, 24), (-29, 24), (29, -24), (-29, -24)):
        pad_sk = pad_sk - Pos(dx, dy) * Circle(6.0)
    pad = extrude(
        Plane(origin=(x0, side * 118.0, 322.0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        * pad_sk,
        11.0,
        both=True,
    )
    leaves.append(style(pad, f"rocker_pad:{tag}", P.TITANIUM))
    return leaves


# ---------------------------------------------------------------------------
# coilover
# ---------------------------------------------------------------------------


def _coilover(side):
    tag = "fl" if side > 0 else "fr"
    a = _p("rk_damp", side)
    b = _p("dmp_ch", side)
    pl, L = _seg(a, b)

    t_eye = 30.0
    t_p1 = t_eye + 4.0
    t_p2 = t_p1 + 152.0
    t_body_end = L - 34.0

    leaves = []
    shaft = _shift(pl, t_eye) * Cylinder(
        9.5, t_p2 - t_eye + 26.0, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    body = _shift(pl, t_p2 - 8.0) * Cylinder(
        27.0, t_body_end - t_p2 + 8.0, align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    leaves.append(style(shaft, f"damper_shaft:{tag}", P.RIM))
    leaves.append(style(body, f"damper_body:{tag}", P.STEEL_DARK))

    # piggyback reservoir, offset off the damper body
    res_off = pl.x_dir * 40.0
    r0 = pl.origin + pl.z_dir * (t_p2 + 26.0) + res_off
    r1 = pl.origin + pl.z_dir * (t_body_end - 4.0) + res_off
    res = _rod(r0, r1, 15.0)
    leaves.append(style(res, f"damper_reservoir:{tag}", P.ALUMINIUM))
    bridge = _rod(
        pl.origin + pl.z_dir * (t_p2 + 34.0),
        pl.origin + pl.z_dir * (t_p2 + 34.0) + res_off,
        7.0,
    )
    leaves.append(style(bridge, f"damper_hose:{tag}", P.BRONZE_DARK))

    # perches -- the adjustable one is the bronze jewel of the assembly
    p_low = extrude(_shift(pl, t_p1) * (Circle(45) - Circle(10.5)), 10.0)
    p_high = extrude(_shift(pl, t_p2 - 17.0) * (Circle(45) - Circle(27.5)), 12.0)
    knurl = extrude(_shift(pl, t_p2 - 5.0) * (RegularPolygon(31.0, 18) - Circle(27.5)), 12.0)
    leaves.append(style(p_low, f"spring_perch:{tag}_low", P.ALUMINIUM))
    leaves.append(style(p_high, f"spring_perch:{tag}_adj", P.BRONZE))
    leaves.append(style(knurl, f"spring_collar:{tag}", P.BRONZE_DARK))

    # spring
    h = (t_p2 - 17.0) - (t_p1 + 10.0)
    turns = 7.5
    hx = Helix(pitch=h / turns, height=h, radius=34.5)
    sec = Plane(origin=hx @ 0, z_dir=hx % 0) * Circle(5.9)
    coil = _shift(pl, t_p1 + 10.0) * sweep(sec, path=hx, is_frenet=True)
    leaves.append(style(coil, f"spring:{tag}", P.RIM_DARK))

    # ends: rod end into the rocker fork, clevis at the chassis
    leaves += _rod_end(a, FWD, _v(b) - _v(a), f"{tag}_dmp_rkr", k=0.95, shank=t_eye + 6)
    chassis_base = _v(b) + (_v(b) - _v(a)).normalized() * 46.0
    leaves += _sph_joint(b, FWD, f"{tag}_dmp_ch", k=0.95)
    leaves += _fork(b, FWD, chassis_base, f"{tag}_dmp_ch", colour=P.SUBFRAME)
    leaves += _pad(b, FWD, chassis_base, f"{tag}_dmp_ch")
    return leaves


# ---------------------------------------------------------------------------
# pushrod
# ---------------------------------------------------------------------------


def _pushrod(side):
    tag = "fl" if side > 0 else "fr"
    a = _p("pr_out", side)
    b = _p("pr_in", side)
    parts = _aero_member(a, b, 58.0, 54.0, 0.44, t0=62.0, t1=58.0)
    leaves = [
        style(pt, f"pushrod:{tag}_{i}", P.ALUMINIUM) for i, pt in enumerate(parts)
    ]
    leaves += _rod_end(a, FWD, _v(b) - _v(a), f"{tag}_pr_lo", k=0.9, shank=56.0)
    leaves += _rod_end(b, FWD, _v(a) - _v(b), f"{tag}_pr_hi", k=0.9, shank=56.0)
    return leaves


# ---------------------------------------------------------------------------
# steering
# ---------------------------------------------------------------------------


def _steering_rack():
    """Front-steer rack: slim machined tube, ribbed centre casting, boots."""
    leaves = []
    ax = (0, 0, 1)
    tube = _rod((RACK_X, -258.0, RACK_Z), (RACK_X, 258.0, RACK_Z), 21.0, ref=ax)
    leaves.append(style(tube, "rack_tube:front", P.ALUMINIUM))

    centre_sk = RectangleRounded(74.0, 56.0, 20.0) - Circle(9.0)
    centre = extrude(
        Plane(origin=(RACK_X, -132.0, RACK_Z), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        * centre_sk,
        264.0,
    )
    leaves.append(style(centre, "rack_casting:front", P.ALUMINIUM_DARK))

    for side in (1, -1):
        nm = "left" if side > 0 else "right"
        boot = _rod(
            (RACK_X, side * 214.0, RACK_Z), (RACK_X, side * 284.0, RACK_Z),
            25.0, ref=ax,
        )
        leaves.append(style(boot, f"rack_boot:{nm}", P.TYRE))
        cap = _rod(
            (RACK_X, side * 284.0, RACK_Z), (RACK_X, side * 296.0, RACK_Z),
            23.0, ref=ax,
        )
        leaves.append(style(cap, f"rack_cap:{nm}", P.BRONZE))
        for dy in (168.0, 206.0):
            band = _rod(
                (RACK_X, side * dy, RACK_Z), (RACK_X, side * (dy + 9.0), RACK_Z),
                24.0, ref=ax,
            )
            leaves.append(style(band, f"rack_band:{nm}_{int(dy)}", P.ALUMINIUM_DARK))
        ear_sk = RectangleRounded(58.0, 88.0, 14.0) - Circle(8.0)
        ear = extrude(
            Plane(origin=(RACK_X, side * 148.0, RACK_Z), x_dir=(1, 0, 0),
                  z_dir=(0, side, 0)) * ear_sk,
            16.0,
        )
        leaves.append(style(ear, f"rack_mount:{nm}", P.TITANIUM))

    # pinion housing + column stub
    pin_a = (RACK_X, 108.0, RACK_Z + 6.0)
    pin_b = (1414.0, 138.0, 396.0)
    pinion = _rod(pin_a, pin_b, 24.0, ref=(0, 0, 1))
    ring = _rod(pin_b, (1400.0, 145.0, 410.0), 27.0, ref=(0, 0, 1))
    col = _rod(pin_b, (1336.0, 158.0, 456.0), 14.0, ref=(0, 0, 1))
    leaves.append(style(pinion, "steering_pinion:front", P.ALUMINIUM_DARK))
    leaves.append(style(ring, "steering_pinion_cap:front", P.BRONZE))
    leaves.append(style(col, "steering_column:front", P.TITANIUM))
    return leaves


def _tie_rod(side):
    tag = "fl" if side > 0 else "fr"
    a = _p("tie_in", side)
    b = _p("tie_out", side)
    parts = _aero_member(a, b, 50.0, 44.0, 0.44, t0=58.0, t1=54.0)
    leaves = [
        style(pt, f"tie_rod:{tag}_{i}", P.ALUMINIUM) for i, pt in enumerate(parts)
    ]
    leaves += _rod_end(a, UPZ, _v(b) - _v(a), f"{tag}_tie_in", k=0.85, shank=54.0)
    leaves += _rod_end(b, UPZ, _v(a) - _v(b), f"{tag}_tie_out", k=0.85, shank=50.0)
    return leaves


# ---------------------------------------------------------------------------
# anti-roll bar
# ---------------------------------------------------------------------------


def _anti_roll_bar():
    leaves = []
    hs = _HP["arb_end"][1]
    tube = _rod((ARB_X, -hs, ARB_Z), (ARB_X, hs, ARB_Z), 15.0, ref=(0, 0, 1))
    leaves.append(style(tube, "arb_bar:front", P.STEEL_DARK))
    for side in (1, -1):
        nm = "left" if side > 0 else "right"
        blk_sk = RectangleRounded(56.0, 50.0, 12.0) - Circle(15.5)
        blk = extrude(
            Plane(origin=(ARB_X, side * 100.0, ARB_Z), x_dir=(1, 0, 0),
                  z_dir=(0, side, 0)) * blk_sk,
            36.0,
        )
        leaves.append(style(blk, f"arb_bearing:{nm}", P.ALUMINIUM))
        strap = _rod(
            (ARB_X, side * 98.0, ARB_Z), (ARB_X, side * 138.0, ARB_Z), 19.5, ref=(0, 0, 1)
        )
        leaves.append(style(strap, f"arb_bush:{nm}", P.BRONZE_DARK))
        post_sk = RectangleRounded(34.0, 52.0, 10.0) - Circle(5.5)
        stem = extrude(
            Plane(origin=(ARB_X, side * 100.0, ARB_Z - 42.0), x_dir=(1, 0, 0),
                  z_dir=(0, side, 0)) * post_sk,
            36.0,
        )
        leaves.append(style(stem, f"arb_bearing_post:{nm}", P.TITANIUM))

        a = _p("arb_end", side)
        b = _p("arb_tip", side)
        pa, La = _seg(a, b, ref=(0, 0, 1))
        blade = loft([
            pa * RectangleRounded(46, 26, 12),
            _shift(pa, La * 0.5) * RectangleRounded(52, 15, 7),
            _shift(pa, La) * RectangleRounded(40, 14, 6.8),
        ])
        leaves.append(style(blade, f"arb_blade:{nm}", P.ALUMINIUM))
    return leaves


def _drop_link(side):
    tag = "fl" if side > 0 else "fr"
    a = _p("arb_tip", side)
    b = _p("rk_arb", side)
    parts = _aero_member(a, b, 30.0, 30.0, 0.52, t0=36.0, t1=36.0)
    leaves = [
        style(pt, f"drop_link:{tag}_{i}", P.ALUMINIUM) for i, pt in enumerate(parts)
    ]
    leaves += _rod_end(a, FWD, _v(b) - _v(a), f"{tag}_dl_up", k=0.72, shank=36.0)
    leaves += _rod_end(b, FWD, _v(a) - _v(b), f"{tag}_dl_lo", k=0.72, shank=36.0)
    return leaves


# ---------------------------------------------------------------------------


def _corner(side):
    name = "front_left" if side > 0 else "front_right"
    kids = []
    kids += _wishbone(side, "lwb")
    kids += _wishbone(side, "uwb")
    kids += _upright(side)
    kids += _pushrod(side)
    kids += _rocker(side)
    kids += _coilover(side)
    kids += _tie_rod(side)
    kids += _drop_link(side)
    return group(name, kids)


def build():
    """Return ONE labelled group Compound."""
    kids = [
        _corner(1),
        _corner(-1),
        group("steering", _steering_rack()),
        group("anti_roll_bar", _anti_roll_bar()),
    ]
    return group("suspension_front", kids)
