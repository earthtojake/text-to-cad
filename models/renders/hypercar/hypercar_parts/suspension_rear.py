"""Rear suspension -- pushrod-actuated double wishbone, both sides.

Design language
---------------
Everything that carries load is a *sculpted machined billet*, never a slab and
never a plain tube.  Three rules give the whole assembly one silhouette:

1. **Section changes along every span.**  Each link is lofted through five
   stations, not two, and both the chord *and* the thickness-to-chord ratio
   fall from a fat root to a knife tip -- so a link is genuinely thinner where
   it is narrower.  Two-force members (pushrod, toe link, drop link) instead
   *waist*: fat at both rod ends, slim through the middle.
2. **Crowned, not flat.**  The aerofoil section is cambered, so the upper face
   is a convex crown that carries one continuous highlight from root to tip
   while the lower face stays taut and nearly flat.  Nothing has a dead flat
   side.
3. **Bowed and twisted.**  Centrelines are quadratic-Bezier bows, not straight
   lines, and the section rolls a few degrees along the span, so every arm has
   a scimitar silhouette that is readable at thumbnail size.

The upright follows the same law in plate form: a crowned lens section whose
perimeter falls away faster at the ball-joint horns than at the bearing boss,
so the plate is visibly thick at the hub and blade-thin at its extremities.

The rear items are deliberately beefier than the front -- they take the drive
torque -- but they use exactly the same section language, so front and rear
read as one family.

Layout
------
* wide-base lower wishbone, long rearward leg carrying the pushrod foot and
  the anti-roll-bar drop link,
* compact upper wishbone,
* upright machined as a stepped rail around a pierced web,
* pushrod running up and inboard, passing *behind* the driveshaft corridor
  that runs from the transaxle at (-1500, 0, 380) out to the hub,
* bell-crank rocker on a canted transverse pivot,
* long inboard coilover lying rearward over the transaxle,
* tubular anti-roll bar behind the axle with near-vertical drop links,
* rearward toe link.

Frame: +X forward, +Y car left, +Z up, ground Z=0.  Rear hub is at
``(S.REAR_AXLE_X, +/-S.REAR_HUB_Y, S.REAR_HUB_Z)`` = (-1350, +/-830, 385.9).
"""

from __future__ import annotations

import math

from build123d import (
    Circle,
    Compound,
    Cone,
    Cylinder,
    Helix,
    Plane,
    Pos,
    Solid,
    Sphere,
    Spline,
    Torus,
    Vector,
    Wire,
    extrude,
    make_hull,
    sweep,
)

from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style
from hypercar_parts import palette as P


# ---------------------------------------------------------------------------
# hard points  (left-hand side, +Y; mirrored by `side`)
# ---------------------------------------------------------------------------

HUB = (S.REAR_AXLE_X, S.REAR_HUB_Y, S.REAR_HUB_Z)      # (-1350, 830, 385.9)

LWB_IF = (-1140.0, 300.0, 206.0)      # lower wishbone, inboard front bush
LWB_IR = (-1660.0, 300.0, 232.0)      # lower wishbone, inboard rear bush
LBJ = (-1350.0, 668.0, 198.0)         # lower ball joint

UWB_IF = (-1180.0, 378.0, 550.0)      # upper wishbone, inboard front bush
UWB_IR = (-1470.0, 378.0, 564.0)      # upper wishbone, inboard rear bush
UBJ = (-1352.0, 660.0, 578.0)         # upper ball joint

TOE_I = (-1690.0, 332.0, 340.0)       # toe link, inboard
TOE_O = (-1462.0, 702.0, 322.0)       # toe link, upright clevis

PR_F = (-1499.0, 485.0, 248.0)        # pushrod foot, on the lower rear leg
PR_A = (-1570.0, 345.0, 672.0)        # pushrod eye, on the rocker

RK_P = (-1420.0, 330.0, 682.0)        # rocker pivot
RK_B = (-1424.0, 312.0, 780.0)        # rocker damper eye
RK_BR = (-1362.0, 330.0, 654.0)       # rocker bracket anchor (into bulkhead)
DMP_C = (-1800.0, 276.0, 742.0)       # coilover chassis eye

ARB_X, ARB_Z = -1735.0, 582.0         # anti-roll bar torsion tube
ARB_HALF_Y = 300.0
ARB_END = (-1575.0, 336.0, 480.0)     # drop-link top, on the anti-roll-bar arm
ARB_TIP = (-1533.0, 344.0, 458.0)     # arm tip, just past the drop link
DL_BOT = (-1602.0, 366.0, 246.0)      # drop-link foot, on the lower rear leg


# ---------------------------------------------------------------------------
# small vector / placement helpers
# ---------------------------------------------------------------------------


def _V(p):
    return p if isinstance(p, Vector) else Vector(p)


def _mir(p, side):
    """Hard point for one side."""
    return Vector(p[0], side * p[1], p[2])


def _u(v):
    v = _V(v)
    n = v.length
    return v / n if n > 1e-12 else Vector(0, 0, 1)


def _perp(axis, hint=(1, 0, 0)):
    """Unit vector perpendicular to `axis`, as close to `hint` as possible."""
    w = _u(axis)
    for h in (_V(hint), Vector(0, 0, 1), Vector(1, 0, 0)):
        c = h - w * h.dot(w)
        if c.length > 1e-6:
            return _u(c)
    return _u(Vector(0, 1, 0))


def _frame(origin, axis, hint=(1, 0, 0)):
    """Plane whose +Z is `axis` and +X is the in-plane part of `hint`."""
    return Plane(origin=_V(origin), x_dir=_perp(axis, hint), z_dir=_u(axis))


def _cyl(center, axis, r, h, hint=(1, 0, 0)):
    """Cylinder radius r, length h, centred on `center`, axis along `axis`."""
    return _frame(center, axis, hint) * Cylinder(radius=r, height=h)


def _cone(center, axis, r0, r1, h, hint=(1, 0, 0)):
    return _frame(center, axis, hint) * Cone(
        bottom_radius=r0, top_radius=r1, height=h
    )


def _ball(center, r):
    c = _V(center)
    return Pos(c.X, c.Y, c.Z) * Sphere(radius=r)


def _span(p0, p1):
    """(centre, axis, length) of the segment p0->p1."""
    a, b = _V(p0), _V(p1)
    d = b - a
    return (a + b) * 0.5, _u(d), d.length


def _one(shape):
    """Normalise a boolean result to a single colourable leaf occurrence.

    build123d returns a bare ShapeList when a fuse leaves disjoint solids, and
    a ShapeList cannot be a Compound child -- collapse it to one Compound.
    """
    if hasattr(shape, "is_valid"):
        return shape
    solids = []
    for s in shape:
        solids.extend(s.solids())
    return Compound(solids)


def _leaf(shape, label, colour, alpha=1.0):
    return style(_one(shape), label, colour, alpha)


def _sn(side):
    return "left" if side > 0 else "right"


# ---------------------------------------------------------------------------
# the aerofoil section -- the whole visual language of this part
# ---------------------------------------------------------------------------


def _af_half(u, thick):
    return 5.0 * thick * (
        0.2969 * math.sqrt(u)
        - 0.1260 * u
        - 0.3516 * u * u
        + 0.2843 * u ** 3
        - 0.1015 * u ** 4
    )


def _af_wire(chord, thick=0.30, n=16, le=0.40, cut=0.92, camber=0.0):
    """A closed, periodic aerofoil wire on Plane.XY.

    ONE periodic B-spline edge, deliberately: a multi-edge wire with a cusp at
    the leading edge lofts into a solid OCC reports invalid, and every boolean
    afterwards silently collapses.  A single periodic edge lofts clean, and it
    also guarantees that every station of a loft has identical topology.

    +X is the leading edge, so struts get a nose-forward section for free.
    `camber` bows the mean line toward +Y, which crowns the upper face and
    flattens the lower one -- that asymmetry is what puts a single travelling
    highlight down the top of every arm instead of a dead flat slab side.
    """
    ups, los = [], []
    for i in range(n + 1):
        u = cut * (i / n) ** 2
        s = u / cut
        yc = camber * chord * 4.0 * s * (1.0 - s)
        h = _af_half(u, thick) * chord
        x = (le - u) * chord
        ups.append((x, yc + h))
        los.append((x, yc - h))
    pts = list(reversed(los[1:])) + ups
    return Wire([Spline(*pts, periodic=True).edge()])


def _strut(p0, p1, chords, thick=0.32, hint=(1, 0, 0), ts=None,
           thicks=None, camber=0.0, crown_dir=None,
           bow=0.0, bow_dir=None, twist=0.0):
    """Sculpted aerofoil billet from p0 to p1.

    `chords` / `thicks` are per-station, so chord AND thickness ratio can fall
    together (a real section change, not a scaled slab).  `bow` pulls the
    centreline off the straight line onto a quadratic Bezier; `twist` rolls the
    section progressively along the span.  Both give the arm visible tension.

    `crown_dir` names the world direction the cambered face must bulge toward.
    Without it the section frame is only defined up to handedness, and the two
    sides of the car come out crowned in opposite directions -- the left arm
    domed on top, the right one domed underneath.
    """
    a, b = _V(p0), _V(p1)
    w = _u(b - a)
    c = _perp(w, hint)
    n = len(chords) - 1
    if ts is None:
        ts = [i / n for i in range(len(chords))]
    if thicks is None:
        thicks = [thick] * len(chords)
    bd = _u(bow_dir) if bow_dir is not None else c
    ctrl = (a + b) * 0.5 + bd * (bow * 2.0)

    def _pos(t):
        return a * ((1.0 - t) ** 2) + ctrl * (2.0 * (1.0 - t) * t) + b * (t * t)

    def _tan(t):
        return _u((ctrl - a) * (2.0 * (1.0 - t)) + (b - ctrl) * (2.0 * t))

    if camber and crown_dir is not None:
        tg_m = _tan(0.5)
        yd_m = tg_m.cross(_perp(tg_m, c))
        if yd_m.dot(_u(crown_dir)) < 0.0:
            camber = -camber

    wires = []
    for t, ch, th in zip(ts, chords, thicks):
        tg = _tan(t)
        xd = _perp(tg, c)
        if twist:
            ang = math.radians(twist) * t
            yd = tg.cross(xd)
            xd = _u(xd * math.cos(ang) + yd * math.sin(ang))
        pl = Plane(origin=_pos(t), x_dir=xd, z_dir=tg)
        wires.append(pl * _af_wire(ch, th, camber=camber))
    return Solid.make_loft(wires, ruled=len(wires) == 2)


def _resample(face, n=88):
    """A single periodic-spline wire tracing `face`'s outer boundary.

    Every crowned loft in this module needs its stations to share topology, and
    a hull-minus-scallops outline does not: the edge count changes as the
    outline shrinks.  Resampling each station onto one periodic B-spline makes
    the loft both legal and G2 across the whole perimeter.
    """
    src = max(face.faces(), key=lambda f: f.area) if hasattr(face, "faces") else face
    wire = max(src.wires(), key=lambda q: q.length)
    pts = []
    for i in range(n):
        p = wire @ (i / n)
        pts.append((p.X, p.Y))
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    area = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    if area < 0.0:
        pts.reverse()
    k = min(range(n), key=lambda i: abs(math.atan2(pts[i][1] - cy, pts[i][0] - cx)))
    pts = pts[k:] + pts[:k]
    return Wire([Spline(*pts, periodic=True).edge()])


def _rod_end(center, axis, r_out=20.0, w=26.0, r_ball=13.0, hint=(1, 0, 0)):
    """Spherical rod end: (housing, bore_cutter, ball)."""
    return (
        _cyl(center, axis, r_out, w, hint),
        _cyl(center, axis, r_ball, w + 8.0, hint),
        _ball(center, r_ball),
    )


# ---------------------------------------------------------------------------
# rocker plane -- P, A, B are coplanar by construction
# ---------------------------------------------------------------------------


def _rocker_plane(side):
    p, a, b = _mir(RK_P, side), _mir(PR_A, side), _mir(RK_B, side)
    n = _u((a - p).cross(b - p))
    pl = Plane(origin=p, x_dir=_u(a - p), z_dir=n)

    def local(q):
        d = _V(q) - p
        return (d.dot(pl.x_dir), d.dot(pl.y_dir))

    return pl, n, local


_PLATE_CROWN = ((-1.0, 1.00), (-0.70, 0.28), (0.0, 0.0),
                (0.70, 0.28), (1.0, 1.00))


def _hull_face(lobes, shrink=0.0):
    edges = []
    for (u, v, r) in lobes:
        edges += (Pos(u, v) * Circle(max(r - shrink, 2.0))).edges()
    return make_hull(edges)


def _hull_plate(lobes, thick, crown=0.0):
    """Hull-of-lobes plate.  `crown` > 0 gives it a lens section instead of a
    slab: the perimeter falls away over `crown` mm, so the rim carries a
    continuous highlight all the way round."""
    if crown <= 0.0:
        return extrude(_hull_face(lobes), amount=thick * 0.5, both=True)
    wires = []
    for (f, k) in _PLATE_CROWN:
        w = _resample(_hull_face(lobes, crown * k), n=40)
        wires.append(Pos(0.0, 0.0, f * thick * 0.5) * w)
    return Solid.make_loft(wires, ruled=False)


# ---------------------------------------------------------------------------
# components
# ---------------------------------------------------------------------------


# station spacing shared by every wishbone leg: a fat root that holds its
# section for a fifth of the span, then a fast fall to a slim tip
_LEG_TS = (0.0, 0.19, 0.52, 0.82, 1.0)
_LEG_THICKS = (0.36, 0.325, 0.275, 0.238, 0.215)


def _lower_wishbone(side):
    itf, itr, bj = _mir(LWB_IF, side), _mir(LWB_IR, side), _mir(LBJ, side)
    piv = _u(itf - itr)                      # inboard pivot axis (~X)
    yh = (0, side, 0)

    # Front leg bows forward, rear leg bows rearward, and each carries its round
    # leading edge on the OUTSIDE of the vee (`hint`) with its knife trailing
    # edge facing into it.  The pair therefore opens out like a bird's wing
    # instead of reading as two sticks meeting at a point.
    body = _strut(
        itf, bj, [104.0, 95.0, 74.0, 60.0, 55.0], ts=list(_LEG_TS),
        thicks=list(_LEG_THICKS), camber=0.085, crown_dir=(0, 0, 1), bow=28.0,
        bow_dir=(1, 0, 0), hint=(1, 0, 0), twist=-11.0 * side,
    )
    # the rear leg keeps a fat mid-span station: that is the pushrod pickup,
    # the most loaded point on the arm, so the taper deliberately pauses there
    body = body + _strut(
        itr, bj, [120.0, 110.0, 96.0, 70.0, 58.0],
        ts=[0.0, 0.19, 0.50, 0.82, 1.0],
        thicks=[0.36, 0.33, 0.30, 0.245, 0.215], camber=0.085,
        crown_dir=(0, 0, 1), bow=24.0,
        bow_dir=(-1, 0, 0), hint=(-1, 0, 0), twist=9.0 * side,
    )
    # one batched fuse then one batched cut: sequential booleans against a
    # spline-surfaced billet are an order of magnitude slower
    body = body + [
        _cyl(itf, piv, 27.0, 62.0, hint=yh),
        _cyl(itr, piv, 27.0, 62.0, hint=yh),
        _cyl(bj + Vector(0, 0, 14.0), (0, 0, 1), 37.0, 72.0),
        _ball(bj + Vector(0, 0, 8.0), 39.0),
        # pushrod foot boss and drop-link lug, both on the rear leg
        _cone(_mir(PR_F, side) + Vector(0, 0, -22.0), (0, 0, 1), 34.0, 24.0, 44.0),
        _cone(_mir(DL_BOT, side) + Vector(0, 0, -20.0), (0, 0, 1), 30.0, 21.0, 40.0),
    ]
    body = body - [_cyl(pt, piv, 15.0, 74.0, hint=yh) for pt in (itf, itr)]

    out = [_leaf(body, f"lower_wishbone:{_sn(side)}", P.ALUMINIUM)]
    for i, pt in enumerate((itf, itr)):
        out.append(
            _leaf(
                _cyl(pt, piv, 14.0, 96.0, hint=yh),
                f"lower_wishbone_pin:{_sn(side)}{i}",
                P.TITANIUM,
            )
        )
        for j, s2 in enumerate((1.0, -1.0)):
            out.append(
                _leaf(
                    _cyl(pt + piv * (s2 * 37.0), piv, 21.0, 12.0, hint=yh),
                    f"lower_wishbone_nut:{_sn(side)}{i}{j}",
                    P.BRONZE,
                )
            )
    out.append(
        _leaf(_cyl(bj + Vector(0, 0, -34.0), (0, 0, 1), 26.0, 15.0),
              f"lower_balljoint_cap:{_sn(side)}", P.BRONZE)
    )
    return out


def _upper_wishbone(side):
    itf, itr, bj = _mir(UWB_IF, side), _mir(UWB_IR, side), _mir(UBJ, side)
    piv = _u(itf - itr)
    yh = (0, side, 0)

    # same law as the lower arm, one size down
    body = _strut(
        itf, bj, [88.0, 80.0, 63.0, 51.0, 47.0], ts=list(_LEG_TS),
        thicks=list(_LEG_THICKS), camber=0.09, crown_dir=(0, 0, 1), bow=24.0,
        bow_dir=(1, 0, 0), hint=(1, 0, 0), twist=-9.0 * side,
    )
    body = body + _strut(
        itr, bj, [95.0, 86.0, 67.0, 54.0, 49.0], ts=list(_LEG_TS),
        thicks=list(_LEG_THICKS), camber=0.09, crown_dir=(0, 0, 1), bow=27.0,
        bow_dir=(-1, 0, 0), hint=(-1, 0, 0), twist=8.0 * side,
    )
    body = body + [
        _cyl(itf, piv, 23.0, 52.0, hint=yh),
        _cyl(itr, piv, 23.0, 52.0, hint=yh),
        _cyl(bj + Vector(0, 0, -12.0), (0, 0, 1), 31.0, 60.0),
        _ball(bj + Vector(0, 0, -6.0), 33.0),
    ]
    body = body - [_cyl(pt, piv, 13.0, 64.0, hint=yh) for pt in (itf, itr)]

    out = [_leaf(body, f"upper_wishbone:{_sn(side)}", P.ALUMINIUM)]
    for i, pt in enumerate((itf, itr)):
        out.append(
            _leaf(
                _cyl(pt, piv, 12.0, 84.0, hint=yh),
                f"upper_wishbone_pin:{_sn(side)}{i}",
                P.TITANIUM,
            )
        )
        for j, s2 in enumerate((1.0, -1.0)):
            out.append(
                _leaf(
                    _cyl(pt + piv * (s2 * 32.0), piv, 18.0, 11.0, hint=yh),
                    f"upper_wishbone_nut:{_sn(side)}{i}{j}",
                    P.BRONZE,
                )
            )
    out.append(
        _leaf(_cyl(bj + Vector(0, 0, 30.0), (0, 0, 1), 22.0, 13.0),
              f"upper_balljoint_cap:{_sn(side)}", P.BRONZE)
    )
    return out


# ---------------------------------------------------------------------------
# upright -- a crowned machined plate, not a slab
#
# The outline is the convex hull of four lobes (three joints plus the bearing
# boss), waisted by two scallops on the leading edge.  Its SECTION is a lens:
# lofted through five stations so the perimeter rolls away continuously, and
# each lobe falls at its own rate (`w`), so the plate is fat and domed at the
# bearing boss and blade-thin out at the ball-joint horns.  A pocket cut leaves
# a crowned perimeter rail around a thin pierced web.
# ---------------------------------------------------------------------------

_UP_LOBES = [               # (x, z, radius, crown weight)
    (-1350.0, 200.0, 42.0, 1.50),     # lower ball joint -- falls away fast
    (-1466.0, 322.0, 34.0, 1.65),     # toe-link clevis  -- thinnest horn
    (-1352.0, 578.0, 34.0, 1.50),     # upper ball joint
    (-1350.0, 386.0, 68.0, 0.50),     # bearing boss -- stays proud and fat
]
_UP_SCALLOPS = [            # (x, z, radius, crown weight)
    (-1200.0, 284.0, 124.0, 0.85),
    (-1188.0, 488.0, 130.0, 0.85),
    (-1428.0, 234.0, 33.0, 1.25),
]
_UP_Y = 702.0               # plate mid-plane
_UP_RAIL_T, _UP_WEB_T, _UP_RAIL_W = 68.0, 32.0, 21.0
_UP_CROWN = 11.0            # depth of the perimeter roll-off
# (fraction of half-thickness, fraction of crown depth)
_UP_STATIONS = ((-1.0, 1.00), (-0.76, 0.34), (0.0, 0.0),
                (0.76, 0.34), (1.0, 1.00))

_UP_FACES = {}


def _up_plane(side):
    """local (u, v) -> global (x, side*_UP_Y, -v); extrudes along +/-Y."""
    return Plane(origin=(0.0, side * _UP_Y, 0.0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))


def _upright_outline(shrink=0.0, weighted=False):
    """Outline face.  `weighted` lets every lobe shrink at its own rate, which
    is what turns a constant plate into one with a real section gradient."""
    key = (round(shrink, 3), weighted)
    hit = _UP_FACES.get(key)
    if hit is not None:
        return hit
    edges = []
    for (x, z, r, w) in _UP_LOBES:
        d = shrink * (w if weighted else 1.0)
        edges += (Pos(x, -z) * Circle(max(r - d, 3.0))).edges()
    face = make_hull(edges)
    for (x, z, r, w) in _UP_SCALLOPS:
        d = shrink * (w if weighted else 1.0)
        face = face - Pos(x, -z) * Circle(r + d)
    _UP_FACES[key] = face
    return face


def _upright_shell(side):
    """The crowned lens plate: one loft, five stations, G2 all the way round."""
    half = _UP_RAIL_T * 0.5
    wires = []
    for (f, k) in _UP_STATIONS:
        w = _resample(_upright_outline(_UP_CROWN * k, weighted=True), n=56)
        pl = Plane(origin=(0.0, side * _UP_Y + f * half, 0.0),
                   x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        wires.append(pl * w)
    return Solid.make_loft(wires, ruled=False)


def _upright(side):
    hub = _mir(HUB, side)
    yax = (0, 1, 0)
    pl = _up_plane(side)

    body = _upright_shell(side)

    # pocket the middle out, leaving the crowned rail and a thin pierced web.
    # Every plate-side cut goes in one pass: the crowned shell is a heavy spline
    # surface and each separate boolean against it re-solves the whole thing.
    inner = _upright_outline(_UP_RAIL_W)
    pocket = pl * extrude(inner, amount=_UP_RAIL_T, both=True)
    pocket = pocket - pl * extrude(inner, amount=_UP_WEB_T * 0.5, both=True)
    toe = _mir(TOE_O, side)
    body = body - [
        pocket,
        # pierced web
        _cyl(Vector(-1350.0, side * _UP_Y, 274.0), yax, 21.0, 220.0),
        _cyl(Vector(-1352.0, side * _UP_Y, 492.0), yax, 22.0, 220.0),
        # toe-link clevis: bore plus a central slot for the rod end
        _cyl(toe, yax, 31.0, 34.0),
        _cyl(toe, yax, 13.5, 200.0),
    ]

    # bearing carrier, added after the pocket so the pocket cannot eat it
    body = body + [
        _cyl(Vector(hub.X, side * 728.0, hub.Z), yax, 76.0, 132.0),
        _cyl(Vector(hub.X, side * 798.0, hub.Z), yax, 60.0, 34.0),
        _cyl(Vector(hub.X, side * 654.0, hub.Z), yax, 52.0, 26.0),
    ]
    body = body - [
        _cyl(Vector(hub.X, side * 818.0, hub.Z), yax, 51.0, 20.0),
        _cyl(Vector(hub.X, side * 640.0, hub.Z), yax, 40.0, 22.0),
    ]

    return [
        _leaf(body, f"upright:{_sn(side)}", P.ALUMINIUM_DARK),
        _leaf(
            _cyl(Vector(hub.X, side * 816.0, hub.Z), yax, 34.0, 28.0),
            f"hub_spigot:{_sn(side)}",
            P.STEEL_DARK,
        ),
    ]


def _pushrod(side):
    f, a = _mir(PR_F, side), _mir(PR_A, side)
    w = _u(a - f)
    _, n, _l = _rocker_plane(side)

    # two-force member: waisted, fat at both rod ends, slim through the middle
    body = _strut(
        f + w * 12.0, a - w * 14.0,
        [60.0, 47.0, 40.0, 45.0, 56.0], ts=[0.0, 0.24, 0.52, 0.78, 1.0],
        thicks=[0.36, 0.31, 0.285, 0.30, 0.35], camber=0.05,
        crown_dir=(0, -side, 0), bow=13.0, bow_dir=(1, 0, 0),
    )
    h0, b0, ball0 = _rod_end(f, (1, 0, 0), 22.0, 32.0, 14.0, hint=(0, 0, 1))
    h1, b1, ball1 = _rod_end(a, n, 22.0, 32.0, 14.0, hint=(0, 0, 1))
    body = body + [h0, h1] - [b0, b1]

    return [
        _leaf(body, f"pushrod:{_sn(side)}", P.ALUMINIUM),
        _leaf(ball0, f"pushrod_joint:{_sn(side)}0", P.STEEL_DARK),
        _leaf(ball1, f"pushrod_joint:{_sn(side)}1", P.STEEL_DARK),
        _leaf(_cyl(f + w * 46.0, w, 27.0, 15.0),
              f"pushrod_collar:{_sn(side)}0", P.BRONZE),
        _leaf(_cyl(a - w * 48.0, w, 27.0, 15.0),
              f"pushrod_collar:{_sn(side)}1", P.BRONZE),
    ]


def _rocker(side):
    pl, n, local = _rocker_plane(side)
    p, a, b = _mir(RK_P, side), _mir(PR_A, side), _mir(RK_B, side)
    ua, va = local(a)
    ub, vb = local(b)

    plate = _hull_plate(
        [(0.0, 0.0, 36.0), (ua, va, 30.0), (ub, vb, 32.0)], 26.0, crown=6.5
    )
    plate = plate - extrude(
        Pos(0.54 * ua + 0.10 * ub, 0.30 * vb + 0.22 * va) * Circle(21.0),
        amount=40.0, both=True,
    )
    body = pl * plate
    body = body + [
        _cyl(p, n, 40.0, 74.0),
        _cyl(a, n, 27.0, 46.0),
        _cyl(b, n, 29.0, 48.0),
    ]
    body = body - [
        _cyl(p, n, 20.0, 96.0),
        _cyl(a, n, 14.0, 64.0),
        _cyl(b, n, 14.5, 66.0),
    ]

    # chassis-side pivot fork: two ears joined at the bulkhead anchor
    anchor = _mir(RK_BR, side)
    ua2, va2 = local(anchor)
    fork = _cyl(anchor, n, 26.0, 88.0)
    for s in (1.0, -1.0):
        ear2d = _hull_plate(
            [(0.0, 0.0, 40.0), (ua2, va2, 23.0)], 19.0, crown=5.0
        )
        ear = Plane(origin=pl.origin + n * (s * 34.0),
                    x_dir=pl.x_dir, z_dir=n) * ear2d
        fork = fork + ear
    fork = fork - _cyl(p, n, 20.0, 120.0)

    return [
        _leaf(body, f"rocker:{_sn(side)}", P.ALUMINIUM),
        _leaf(fork, f"rocker_fork:{_sn(side)}", P.ALUMINIUM_DARK),
        _leaf(_cyl(p, n, 19.0, 106.0), f"rocker_pin:{_sn(side)}", P.TITANIUM),
        _leaf(_cyl(p + n * 55.0, n, 23.0, 13.0),
              f"rocker_nut:{_sn(side)}0", P.BRONZE),
        _leaf(_cyl(p - n * 55.0, n, 23.0, 13.0),
              f"rocker_nut:{_sn(side)}1", P.BRONZE),
    ]


def _spring(start, axis, height, radius, wire_r, turns):
    """Coil spring swept along a real helix (falls back to stacked rings)."""
    try:
        path = _frame(start, axis) * Helix(
            pitch=height / turns, height=height, radius=radius
        )
        sec = Plane(origin=path @ 0, z_dir=path % 0) * Circle(wire_r)
        return sweep(sec, path=path, is_frenet=True)
    except Exception:                              # pragma: no cover
        out = None
        n = int(turns) + 1
        for i in range(n):
            c = _V(start) + _u(axis) * (height * (i + 0.5) / n)
            ring = _frame(c, axis) * Torus(
                major_radius=radius, minor_radius=wire_r
            )
            out = ring if out is None else out + ring
        return out


def _coilover(side):
    b, c = _mir(RK_B, side), _mir(DMP_C, side)
    _, n, _l = _rocker_plane(side)
    w = _u(c - b)
    L = (c - b).length
    up = _perp(w, (0, 0, 1))
    sn = _sn(side)

    def at(t):
        return b + w * t

    out = []

    # damper body + chassis eye
    dbody = _cyl(at(0.745 * L), w, 31.0, 0.49 * L)
    dbody = dbody + _cyl(at(0.50 * L), w, 36.0, 18.0)
    h1, bo1, ball1 = _rod_end(c, n, 23.0, 34.0, 14.0, hint=(0, 0, 1))
    dbody = dbody + h1 - bo1
    out.append(_leaf(dbody, f"damper_body:{sn}", P.ALUMINIUM_DARK))

    # shaft + rocker eye
    shaft = _cyl(at(0.30 * L), w, 11.0, 0.53 * L)
    h0, bo0, ball0 = _rod_end(b, n, 23.0, 34.0, 14.0, hint=(0, 0, 1))
    shaft = shaft + h0 - bo0
    out.append(_leaf(shaft, f"damper_shaft:{sn}", P.TITANIUM))
    out.append(_leaf(ball0, f"damper_joint:{sn}0", P.STEEL_DARK))
    out.append(_leaf(ball1, f"damper_joint:{sn}1", P.STEEL_DARK))

    # spring perches + threaded adjuster
    out.append(_leaf(_cyl(at(0.10 * L), w, 50.0, 13.0),
                     f"damper_perch:{sn}0", P.ALUMINIUM))
    out.append(_leaf(_cyl(at(0.505 * L), w, 50.0, 13.0),
                     f"damper_perch:{sn}1", P.ALUMINIUM))
    out.append(_leaf(_cyl(at(0.55 * L), w, 40.0, 26.0),
                     f"damper_adjuster:{sn}", P.BRONZE))

    out.append(
        _leaf(_spring(at(0.115 * L), w, 0.385 * L, 41.0, 8.5, 6.0),
              f"damper_spring:{sn}", P.BRONZE)
    )

    # remote reservoir clipped alongside the body
    roff = up * 46.0
    res = _cyl(at(0.75 * L) + roff, w, 15.0, 0.30 * L)
    res = res + _cyl(at(0.62 * L) + up * 24.0, up, 8.0, 46.0, hint=(1, 0, 0))
    out.append(_leaf(res, f"damper_reservoir:{sn}", P.ALUMINIUM_DARK))
    out.append(_leaf(_cyl(at(0.905 * L) + roff, w, 17.0, 14.0),
                     f"damper_reservoir_cap:{sn}", P.BRONZE_DARK))
    return out


def _toe_link(side):
    i, o = _mir(TOE_I, side), _mir(TOE_O, side)
    w = _u(o - i)
    yh = (0, side, 0)
    body = _strut(
        i + w * 12.0, o - w * 12.0,
        [54.0, 43.0, 36.0, 41.0, 50.0], ts=[0.0, 0.24, 0.52, 0.78, 1.0],
        thicks=[0.38, 0.33, 0.30, 0.32, 0.37], camber=0.06,
        crown_dir=(0, 0, 1), bow=11.0, bow_dir=(0, 0, 1),
    )
    h0, b0, ball0 = _rod_end(i, yh, 20.0, 28.0, 12.5, hint=(0, 0, 1))
    h1, b1, ball1 = _rod_end(o, yh, 20.0, 28.0, 12.5, hint=(0, 0, 1))
    body = body + [h0, h1] - [b0, b1]
    sn = _sn(side)
    return [
        _leaf(body, f"toe_link:{sn}", P.ALUMINIUM),
        _leaf(ball0, f"toe_link_joint:{sn}0", P.STEEL_DARK),
        _leaf(ball1, f"toe_link_joint:{sn}1", P.STEEL_DARK),
        _leaf(_cyl(i + w * 40.0, w, 24.0, 13.0), f"toe_link_collar:{sn}0", P.BRONZE),
        _leaf(_cyl(o - w * 40.0, w, 24.0, 13.0), f"toe_link_collar:{sn}1", P.BRONZE),
    ]


def _drop_link(side):
    top, bot = _mir(ARB_END, side), _mir(DL_BOT, side)
    w = _u(bot - top)
    # a blade, not a length of bar: waisted fore-aft section between the eyes
    body = _strut(
        top + w * 10.0, bot - w * 10.0,
        [34.0, 26.0, 21.0, 26.0, 34.0], ts=[0.0, 0.22, 0.5, 0.78, 1.0],
        thicks=[0.52, 0.60, 0.66, 0.60, 0.52], camber=0.0,
        bow=7.0, bow_dir=(1, 0, 0),
    )
    h0, b0, ball0 = _rod_end(top, (1, 0, 0), 19.0, 28.0, 12.0, hint=(0, 0, 1))
    h1, b1, ball1 = _rod_end(bot, (1, 0, 0), 19.0, 28.0, 12.0, hint=(0, 0, 1))
    body = body + [h0, h1] - [b0, b1]
    sn = _sn(side)
    return [
        _leaf(body, f"arb_drop_link:{sn}", P.TITANIUM),
        _leaf(ball0, f"arb_drop_joint:{sn}0", P.STEEL_DARK),
        _leaf(ball1, f"arb_drop_joint:{sn}1", P.STEEL_DARK),
        _leaf(_cyl(top + w * 36.0, w, 16.0, 12.0), f"arb_drop_collar:{sn}0", P.BRONZE),
        _leaf(_cyl(bot - w * 36.0, w, 16.0, 12.0), f"arb_drop_collar:{sn}1", P.BRONZE),
    ]


def _arb():
    """One-piece tubular anti-roll bar spanning the car."""
    pts = []
    for side in (-1, 1):
        seg = [
            (ARB_X, side * ARB_HALF_Y, ARB_Z),
            (-1672.0, side * 322.0, 548.0),
            (ARB_END[0], side * ARB_END[1], ARB_END[2]),
            (ARB_TIP[0], side * ARB_TIP[1], ARB_TIP[2]),
        ]
        pts = list(reversed(seg)) + pts if side < 0 else pts + seg
    pts = (
        pts[:4]
        + [(ARB_X, -150.0, ARB_Z + 2.0), (ARB_X, 0.0, ARB_Z + 3.0),
           (ARB_X, 150.0, ARB_Z + 2.0)]
        + pts[4:]
    )
    t0 = _u(Vector(*pts[1]) - Vector(*pts[0]))
    t1 = _u(Vector(*pts[-1]) - Vector(*pts[-2]))
    path = Spline(*pts, tangents=(t0, t1))

    # the torsion span is constant -- that is what a torsion bar IS -- but the
    # lever arms swell into the bends and then draw down to a slim tip, so the
    # bar is never a plain length of pipe
    law = [(0.00, 12.5), (0.055, 16.4), (0.17, 18.0), (0.34, 18.4),
           (0.50, 18.4), (0.66, 18.4), (0.83, 18.0), (0.945, 16.4),
           (1.00, 12.5)]
    secs = [Plane(origin=path @ t, z_dir=path % t) * Circle(r) for (t, r) in law]

    out = [_leaf(sweep(secs, path=path, multisection=True, is_frenet=True),
                 "arb_bar:centre", P.STEEL_DARK)]
    for side in (1, -1):
        sn = _sn(side)
        m = _cyl(Vector(ARB_X, side * 196.0, ARB_Z + 2.0), (0, 1, 0), 34.0, 50.0)
        m = m + _cyl(Vector(ARB_X, side * 196.0, ARB_Z + 44.0), (0, 1, 0),
                     22.0, 46.0)
        m = m - _cyl(Vector(ARB_X, side * 196.0, ARB_Z + 2.0), (0, 1, 0),
                     18.6, 60.0)
        out.append(_leaf(m, f"arb_mount:{sn}", P.ALUMINIUM_DARK))
        out.append(
            _leaf(_cyl(_mir(ARB_TIP, side), (1, 0, 0), 22.0, 16.0, hint=(0, 0, 1)),
                  f"arb_blade_collar:{sn}", P.BRONZE)
        )
    return out


# ---------------------------------------------------------------------------


def build():
    """Return ONE labelled group Compound for the whole rear suspension."""
    kids = []
    for side in (1, -1):
        kids += _lower_wishbone(side)
        kids += _upper_wishbone(side)
        kids += _upright(side)
        kids += _pushrod(side)
        kids += _rocker(side)
        kids += _coilover(side)
        kids += _toe_link(side)
        kids += _drop_link(side)
    kids += _arb()
    return group("suspension_rear", kids)
