"""F-14D inlets: boundary-layer diverter, raked cowls, ramps and ducts.

The rectangular inlet boxes -- splayed outboard, raked back at the lip, standing
130 mm clear of the fuselage on a boundary-layer diverter slot -- are the single
most recognisable thing about a Tomcat after the planform.  Everything here is
built in the WATERLINE frame; :func:`build` applies ``stance`` once at the end.

Two halves, and why
-------------------
The airframe skin is lofted with the diverter slot FILLED (see ``PANCAKE_TOP``
in ``geometry.py``): a station taken through an open slot is two disconnected
regions and cannot be lofted as one closed wire.  It is also lofted with a
rounded blob where the inlet mouth should be, because the nacelle lobe simply
switches on at ``X_INLET_LIP`` and the loft flares into it over one station
interval.  Neither can be fixed in the section maths.  So this module publishes

    SKIN_CUTTERS   -- solids, WATERLINE frame, for ``skin - SKIN_CUTTERS``
    cutters()      -- the same list

and the airframe module applies them.  One fused cutter per side carries three
jobs:

* the DIVERTER SLOT -- a flat-walled channel from the fuselage side
  (``Y_SPLITTER``) to the inner cowl wall (``Y_INLET_INNER``), roofed just under
  the glove and running aft until it fades into the belly.  Cutting it is also
  what gives the fuselage side and the inner cowl their crisp machined walls
  instead of the lofted blend.
* the NOSE CHOP -- everything in the nacelle envelope forward of the raked lip
  plane.  This deletes the loft's blob and leaves the nacelle starting on a
  clean 15 deg raked face, which is the real lip line.
* the DUCT -- the capture envelope driven aft and morphed toward the circular
  engine face, so the inlet reads as a deep hole rather than a dimple.

The visible bodies in :func:`build` then line that cavity: a rounded cowl lip,
a three-stage duct liner that darkens with depth, the three upper ramps with
their perforated bleed panel, the slot liner and splitter rail, and the cowl's
bypass doors, bleed louvres and fastener rows.

Ramps are RETRACTED (flush), which is the parked state.
"""

from __future__ import annotations

import math

from build123d import (Box, Location, Plane, Polygon, Rectangle,
                       RectangleRounded, Solid, Vector, extrude, loft)

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts.context import group, mirror_pair
from f14_parts import palette as P

try:  # instanced fastener/perforation rows; optional so the module still loads
    from cadgen import compound_from_instances
except Exception:  # noqa: BLE001
    compound_from_instances = None

M = G.M

# ---------------------------------------------------------------------------
# lip geometry
# ---------------------------------------------------------------------------
# The lip is RAKED with the top FORWARD.  That is not a styling choice: the
# F-14's compression ramps live on the UPPER duct wall, so the ramp shelf has to
# lead and the lower cowl lip has to sit far enough aft to swallow the shock off
# it.  Same reason the F-15 looks the way it does.

RAKE = G.INLET_RAKE                       # deg from vertical, side view
_TAN = math.tan(math.radians(RAKE))
_COS = math.cos(math.radians(RAKE))
_SIN = math.sin(math.radians(RAKE))

X_MOUTH_TOP = 6.400 * M     # station of the TOP lip edge.  Not X_INLET_LIP:
                            # the loft flares the nacelle on between stations
                            # 6.22 and 6.38 m, so the mouth has to start where
                            # the section is honestly the full nacelle.
T_COWL = 34.0               # cowl wall thickness at the lip
T_DUCT = 30.0               # duct liner wall
R_CORNER = 82.0             # capture corner radius

# capture plane: solved so the mouth's TOP edge lands on X_MOUTH_TOP once the
# rake is applied.  Iterated because the nacelle section itself depends on x.
_x = X_MOUTH_TOP
for _ in range(6):
    _yc, _rl, _rv, _zc = G.nacelle(_x)
    _x = X_MOUTH_TOP + (_rv - T_COWL) * _TAN
X_CAP = _x
Y_NAC_CAP, R_LAT_CAP, R_VER_CAP, Z_CAP = G.nacelle(X_CAP)

# Capture is bounded by the MEASURED walls, not by G.INLET_WIDTH: the outer
# cowl at 1.706 m and the inner at 0.950 m leave 756 mm of external box, so a
# 870 mm capture cannot physically fit between them.  The walls win -- they are
# what the eye reads -- and the mouth comes out 0.72 x 1.10 m.
Y_CAP_IN = G.Y_INLET_INNER + T_COWL
Y_CAP_OUT = (Y_NAC_CAP + R_LAT_CAP) - T_COWL
A_CAP = 0.5 * (Y_CAP_OUT - Y_CAP_IN)      # capture half-width
Y_CAP = 0.5 * (Y_CAP_OUT + Y_CAP_IN)      # capture centre, lateral
B_CAP = R_VER_CAP - T_COWL                # capture half-height
Z_HI = Z_CAP + B_CAP                      # top lip height
Z_LO = Z_CAP - B_CAP

DUCT_R = G.DUCT_RADIUS
S_MORPH = 3.90 * M          # rectangle -> circle over this run
S_UNRAKE = 0.95 * M         # the raked capture plane squares up over this run
S_DUCT = 3.50 * M           # how far aft the duct liner is modelled
Y_DUCT_KEEP = G.Y_INLET_INNER + 36.0   # duct stays outboard of the slot

# ---------------------------------------------------------------------------
# diverter slot
# ---------------------------------------------------------------------------

X_SLOT_FWD = 6.200 * M
Z_SLOT_ROOF = 0.075 * M     # just into the glove root; the glove underside sits
                            # at +0.034..+0.052 m through the slot's run
X_SLOT_TAPER = 8.300 * M    # roof starts dropping toward the belly here
X_SLOT_AFT = 9.400 * M      # ... and meets it here
Z_DEEP = -1.400 * M         # cutter floor, well clear of the belly


def rake_x(z):
    """Station of the raked lip plane at height ``z``."""
    return X_MOUTH_TOP + (Z_HI - z) * _TAN


def _nac(x):
    return G.nacelle(min(max(x, G.X_INLET_LIP), G.LENGTH))


def _nac_exp(x):
    """The nacelle section's superellipse exponent at station x (mirrors
    ``sections._nacelle`` so anything sat on the cowl sits on the real skin)."""
    return G.lerp(3.6, 2.0, G.smoothstep(G.X_INLET_LIP, G.X_NOZZLE_START, x))


def nacelle_y(x, z):
    """Outer cowl surface of the PURE nacelle lobe at (x, z), or None where the
    section does not reach that height.  Used to size the duct and the cutters;
    anything that has to SIT on the aircraft uses :func:`skin_y` instead."""
    y_c, r_lat, r_ver, z_c = _nac(x)
    t = abs(z - z_c) / r_ver
    if t >= 1.0:
        return None
    n = _nac_exp(x)
    return y_c + r_lat * (1.0 - t ** n) ** (1.0 / n)


def skin_y(x, z, y_hi=None):
    """Lateral position of the SKIN at (x, z), starboard-half magnitude.

    The blended section is up to ~45 mm outboard of the bare nacelle lobe where
    the glove and the pancake pile onto it, so a door placed on ``nacelle_y``
    sinks into the aeroplane and never renders.  Bisect ``sections.surfaces``
    instead -- that is the authoritative "where is the skin" query.

    The search is capped just outside the nacelle by default.  Without the cap
    it walks straight off the cowl and onto the GLOVE overhang wherever the two
    share a height, and a fastener row jumps 250 mm outboard mid-row.
    """
    def inside(y):
        t, b = SEC.surfaces(x, y)
        return t is not None and b - 1.0 <= z <= t + 1.0

    if y_hi is None:
        n_y = nacelle_y(x, z)
        y_hi = (n_y + 90.0) if n_y is not None else 2.60 * G.M
    lo = G.Y_INLET_INNER + 40.0
    if not inside(lo):
        return None
    if inside(y_hi):
        return y_hi
    hi = y_hi
    for _ in range(26):
        mid = 0.5 * (lo + hi)
        if inside(mid):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# duct spine
# ---------------------------------------------------------------------------


def duct_station(s):
    """(x, y, z, half_width, half_height, corner_r, rake_deg) at run ``s``."""
    t = G.smoothstep(0.0, S_MORPH, s)
    a = G.lerp(A_CAP, DUCT_R, t)
    b = G.lerp(B_CAP, DUCT_R, t)
    r = G.lerp(R_CORNER, DUCT_R, t)
    x = X_CAP + s
    y_c, r_lat, r_ver, z_c = _nac(x)
    # The duct grows faster than the nacelle splays, so left on the axis it
    # would eat into the diverter slot from about x = 8 m.  Walk it outboard
    # just enough to stay clear, then let it settle back on the axis once the
    # slot has closed -- the real duct swings outboard before it turns in to
    # the engine face anyway.
    keep = G.lerp(Y_DUCT_KEEP, 0.0,
                  G.smoothstep(X_SLOT_AFT - 0.30 * M, X_SLOT_AFT + 0.60 * M, x))
    inner = y_c - a
    if inner < keep:
        shift = keep - inner
        room = (y_c + r_lat - 30.0) - (y_c + shift + a)
        y_c += max(0.0, shift + min(0.0, room))
    rake = RAKE * (1.0 - G.smoothstep(0.0, S_UNRAKE, s))
    return x, y_c, z_c, a, b, r, rake


def _sec_face(st, off, side=1, off_h=None):
    """One duct cross-section as a face, offset ``off`` normal to itself.

    ``off_h`` overrides the vertical offset.  The lip needs it: the blended
    skin stands ~45 mm proud of the bare nacelle crown where the glove and the
    pancake pile onto it, so a lip rolled with one uniform offset leaves a flat
    band across the TOP of the mouth and only rounds the sides.
    """
    x, y, z, a, b, r, rake = st
    if off_h is None:
        off_h = off
    ang = math.radians(rake)
    pl = Plane(origin=Vector(x, side * y, z), x_dir=Vector(0, 1, 0),
               z_dir=Vector(math.cos(ang), 0.0, math.sin(ang)))
    w = 2.0 * (a + off)
    h = 2.0 * (b / math.cos(ang) + off_h)
    rr = max(1.0, min(r + min(off, off_h), 0.4995 * min(w, h)))
    return (pl.location * RectangleRounded(w, h, rr)).faces()[0]


def _duct_samples(s0, s1, n):
    return [duct_station(s0 + (s1 - s0) * i / (n - 1)) for i in range(n)]


def _duct_shell(s0, s1, n, off_out, off_in, side):
    sts = _duct_samples(s0, s1, n)
    outer = loft([_sec_face(st, off_out, side) for st in sts])
    inner = loft([_sec_face(st, off_in, side) for st in sts])
    return outer - inner


# ---------------------------------------------------------------------------
# SKIN CUTTERS
# ---------------------------------------------------------------------------


def _prism_y(pts, y0, y1):
    """Extrude an (x, z) polygon laterally from y0 to y1."""
    pl = Plane(origin=(0, y0, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    face = (pl.location * Polygon(*pts, align=None)).faces()[0]
    sol = extrude(face, amount=abs(y1 - y0))
    bb = sol.bounding_box()
    lo = min(y0, y1)
    return Location((0.0, lo - bb.min.Y, 0.0)) * sol


def _slot_outline():
    """Side-view outline of the diverter channel, (x, z) pairs.

    Roof flat just inside the glove root, then faded onto the belly so the
    channel closes as a tapering groove rather than a square hole.  The forward
    edge is raked PARALLEL TO THE LIP -- that edge is the splitter plate's
    leading edge and on the aircraft it lies in the same plane as the cowl.
    """
    pts = [(X_SLOT_FWD, Z_SLOT_ROOF), (X_SLOT_TAPER, Z_SLOT_ROOF)]
    n = 16
    for i in range(1, n + 1):
        t = i / n
        x = G.lerp(X_SLOT_TAPER, X_SLOT_AFT, t)
        pts.append((x, _cut_roof_z(x)))
    pts.append((X_SLOT_AFT + 30.0, Z_DEEP))
    pts.append((rake_x(Z_DEEP) - 40.0, Z_DEEP))
    return pts


def _slot_cutter(side):
    y0, y1 = G.Y_SPLITTER, G.Y_INLET_INNER
    return _prism_y(_slot_outline(), side * y0, side * y1)


def _superellipse(a, b, n, count=76):
    out = []
    for i in range(count):
        th = 2.0 * math.pi * i / count
        c, s = math.cos(th), math.sin(th)
        u = math.copysign(abs(c) ** (2.0 / n), c) if c else 0.0
        v = math.copysign(abs(s) ** (2.0 / n), s) if s else 0.0
        out.append((a * u, b * v))
    return out


def _nose_chop(side):
    """Everything in the nacelle envelope FORWARD of the raked lip plane.

    Inflated well past the section so it also swallows whatever the loft does
    between the last forebody-only station and the first full-nacelle one, and
    clipped inboard at the inner cowl wall so it never bites the forebody.
    """
    x_ref = 6.560 * M
    y_c, r_lat, r_ver, z_c = G.nacelle(x_ref)
    infl = 115.0
    pts = _superellipse(r_lat + infl, r_ver + infl, 3.6)
    pl = Plane(origin=(6.050 * M, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    face = (pl.location * Polygon(*[(y, z) for y, z in pts], align=None)).faces()[0]
    face = Location((0.0, side * y_c, z_c)) * face
    prism = extrude(face, amount=0.900 * M)
    bb = prism.bounding_box()
    prism = Location((6.050 * M - bb.min.X, 0, 0)) * prism
    # keep it outboard of the inner cowl wall
    keep = Box(1.400 * M, 1.400 * M, 2.000 * M)
    keep = Location((6.700 * M, side * (G.Y_INLET_INNER + 0.700 * M), z_c)) * keep
    prism = prism & keep
    # ... and forward of the lip plane
    ang = math.radians(RAKE)
    pl_r = Plane(origin=Vector(X_CAP, side * Y_CAP, Z_CAP), x_dir=Vector(0, 1, 0),
                 z_dir=Vector(math.cos(ang), 0.0, math.sin(ang)))
    aft = extrude((pl_r.location * Rectangle(6.0 * M, 6.0 * M)).faces()[0],
                  amount=4.0 * M)
    return prism - aft


def _duct_cavity(side):
    """The capture envelope, run aft and morphed toward the engine face."""
    sts = [duct_station(-60.0)] + _duct_samples(0.0, S_DUCT + 0.30 * M, 15)
    return loft([_sec_face(st, 0.0, side) for st in sts])


def _cowl_groove(x, side, z0, z1, width=11.0, depth=5.0, n=22):
    """A shallow transverse joint on the cowl flank, FOLLOWING THE SKIN.

    5 mm deep and 11 mm wide, per the scale rule: at 19 m across 1920 px a
    scribed line cannot read by shading, but the edge overlay draws the groove's
    two feature edges and it comes out as the fine dark line it should be.
    Sampled off ``skin_y`` rather than the bare nacelle superellipse -- the two
    differ by tens of millimetres wherever the glove piles onto the cowl, and a
    groove cut to the wrong surface either misses the skin or gouges it.
    """
    pts_out, pts_in = [], []
    for i in range(n + 1):
        z = G.lerp(z0, z1, i / n)
        y = skin_y(x, z)
        if y is None:
            continue
        pts_out.append((y + 60.0, z))
        pts_in.append((y - depth, z))
    if len(pts_out) < 3:
        return None
    poly = pts_out + list(reversed(pts_in))
    pl = Plane(origin=(x - 0.5 * width, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    face = (pl.location * Polygon(*[(side * y, z) for y, z in poly],
                                  align=None)).faces()[0]
    sol = extrude(face, amount=width)
    bb = sol.bounding_box()
    return Location((x - 0.5 * width - bb.min.X, 0, 0)) * sol


def _side_cutter(side):
    parts = [_nose_chop(side), _duct_cavity(side)]
    for x in (6.980 * M, 7.640 * M):
        g = _cowl_groove(x, side, -0.430 * M, 0.290 * M)
        if g is not None:
            parts.append(g)
    return _slot_cutter(side) + parts


def cutters():
    """Solids the airframe skin must be cut by, in the WATERLINE frame."""
    return list(SKIN_CUTTERS)


# ---------------------------------------------------------------------------
# visible bodies
# ---------------------------------------------------------------------------


def _lip(side):
    """The cowl lip: a quarter-round nose on the raked mouth edge.

    Not a knife edge and not a blunt slab -- a 17 mm radius rolled from the
    outer cowl surface round to the duct wall, which is what a thin supersonic
    lip actually is.
    """
    r = 0.5 * T_COWL
    rh = 1.40 * r               # taller roll top and bottom -- see _sec_face
    st0 = duct_station(0.0)
    outer, inner = [], []
    for u in (0.12, 0.34, 0.58, 0.80, 1.00):
        th = u * 0.5 * math.pi
        st = list(st0)
        st[0] = st0[0] - r * math.cos(th)
        outer.append(_sec_face(tuple(st), r + r * math.sin(th), side,
                               off_h=rh + rh * math.sin(th)))
        inner.append(_sec_face(tuple(st), r - r * math.sin(th), side,
                               off_h=rh - rh * math.sin(th)))
    st = list(st0)
    st[0] = st0[0] + 55.0
    outer.append(_sec_face(tuple(st), 2.0 * r, side, off_h=2.0 * rh))
    inner.append(_sec_face(tuple(st), -3.0, side))
    return loft(outer) - loft(inner)


def _duct_liner(side):
    """Three stages, each with a slightly wider bore than the one ahead of it.

    The step keeps neighbouring stages from sharing a face, and the colours
    walk from a light forward duct to near black at the far end, which is what
    actually sells the depth: an evenly lit tube reads as a shallow dimple.
    """
    fwd = _duct_shell(-8.0, 0.95 * M, 9, 3.0, -T_DUCT, side)
    mid = _duct_shell(0.95 * M, 2.05 * M, 6, 3.0, -T_DUCT + 7.0, side)
    aft = _duct_shell(2.05 * M, S_DUCT, 7, 3.0, -T_DUCT + 14.0, side)
    return fwd, mid, aft


def _duct_cap(side):
    st = duct_station(S_DUCT)
    face = _sec_face(st, -T_DUCT + 16.0, side)
    return extrude(face, amount=-40.0)


def _bore(x_or_s, off=0.0):
    """(y_axis, z_axis, half_width, half_height) of the duct BORE at run s."""
    x, y, z, a, b, r, rake = duct_station(x_or_s)
    return y, z, a - T_DUCT + off, b - T_DUCT + off, r - T_DUCT


def _ramp(side, s0, s1, drop, thick=36.0, inset=13.0):
    """One upper compression ramp, retracted flush against the duct roof."""
    sm = 0.5 * (s0 + s1)
    y, z, a, b, r = _bore(sm)
    x0 = duct_station(s0)[0]
    x1 = duct_station(s1)[0]
    w = 2.0 * max(60.0, a - r - inset)
    box = Box(x1 - x0, w, thick)
    return Location((0.5 * (x0 + x1), side * y, z + b - drop - 0.5 * thick)) * box


def _bleed_panel(side, s0, s1):
    y, z, a, b, r = _bore(0.5 * (s0 + s1))
    x0, x1 = duct_station(s0)[0], duct_station(s1)[0]
    w = 2.0 * max(50.0, a - r - 26.0)
    box = Box(x1 - x0, w, 22.0)
    return Location((0.5 * (x0 + x1), side * y, z + b - 44.0)) * box


def _perforations(side, s0, s1):
    if compound_from_instances is None:
        return None
    y, z, a, b, r = _bore(0.5 * (s0 + s1))
    x0, x1 = duct_station(s0)[0], duct_station(s1)[0]
    w = 2.0 * max(50.0, a - r - 34.0)
    proto = P.style(Solid.make_cylinder(7.0, 4.0), "bleed_hole", P.RUBBER)
    proto = Location((0, 0, 0), (0, 90, 0)) * proto
    cols, rows = 9, 6
    inst = []
    for i in range(cols):
        for j in range(rows):
            px = G.lerp(x0 + 26.0, x1 - 26.0, i / (cols - 1))
            py = G.lerp(-0.5 * w, 0.5 * w, j / (rows - 1))
            inst.append((proto, Location((px, side * y + py,
                                          z + b - 34.0)), f"h{i}_{j}"))
    return compound_from_instances(f"bleed_perf_{'p' if side > 0 else 's'}", inst)


def _cut_roof_z(x):
    """Roof of the diverter cut at station x (the outline's top edge)."""
    if x <= X_SLOT_TAPER:
        return Z_SLOT_ROOF
    t = G.clamp((x - X_SLOT_TAPER) / (X_SLOT_AFT - X_SLOT_TAPER), 0.0, 1.0)
    z_bel = SEC.surfaces(x, 0.885 * M)[1]
    if z_bel is None:
        return Z_SLOT_ROOF
    return G.lerp(Z_SLOT_ROOF, z_bel - 4.0, t * t * (3.0 - 2.0 * t))


def _wall_floor_z(x, y):
    """Belly line beside one wall of the channel, or None where there is no
    skin at that station."""
    t, b = SEC.surfaces(x, y)
    return b


def _channel_outline(y_probe, top_drop, floor_lift, n=46):
    """A closed (x, z) outline that fits INSIDE the diverter cut: roofed just
    under the cut roof, floored on the local belly line so nothing dangles
    below the aeroplane, and closed automatically wherever the channel is too
    shallow to line."""
    top, bot = [], []
    for i in range(n + 1):
        x = G.lerp(X_SLOT_FWD, X_SLOT_AFT, i / n)
        if x < rake_x(Z_SLOT_ROOF) + 8.0:
            continue                       # forward of the raked splitter edge
        zt = _cut_roof_z(x) - top_drop
        zb = _wall_floor_z(x, y_probe)
        if zb is None:
            continue
        zb += floor_lift
        if zt - zb < 30.0:
            continue
        top.append((x, zt))
        bot.append((x, zb))
    if len(top) < 3:
        return None
    return top + list(reversed(bot))


def _slot_liner(side):
    """Machined walls for the diverter channel.

    Each plate overlaps INTO the skin so it never shares a face with the cut
    wall it dresses; what shows in the channel is a 17 mm proud rail on each
    side and a roof panel, which is what turns the slot from a hole into a
    machined duct.
    """
    y_in, y_out = G.Y_SPLITTER, G.Y_INLET_INNER
    wall = 17.0
    a = b = c = None
    pi = _channel_outline(y_in + 6.0, 12.0, 2.0)
    if pi:
        a = _prism_y(pi, side * (y_in - 14.0), side * (y_in + wall))
    po = _channel_outline(y_out - 6.0, 12.0, 2.0)
    if po:
        b = _prism_y(po, side * (y_out - wall), side * (y_out + 14.0))
    pr = _channel_outline(0.885 * M, 8.0, 0.0)
    if pr:
        pr = [(x, max(z, _cut_roof_z(x) - 34.0)) for x, z in pr]
        c = _prism_y(pr, side * (y_in + wall - 2.0), side * (y_out - wall + 2.0))
    return a, b, c


def _surface_plate(side, x0, x1, z0, z1, out=2.5, thick=14.0):
    """A flush panel lying on the outer cowl between two stations."""
    zm = 0.5 * (z0 + z1)
    y0 = skin_y(x0, zm)
    y1 = skin_y(x1, zm)
    if y0 is None or y1 is None:
        return None
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy)
    nx, ny = side * (-dy / ln), side * (dx / ln)
    cx = 0.5 * (x0 + x1) + nx * out
    cy = side * 0.5 * (y0 + y1) + ny * out
    box = Box(ln, thick, abs(z1 - z0))
    return Location((cx, cy, zm), (0, 0, math.degrees(math.atan2(dy, dx)))) * box


def _louvres(side):
    out = []
    for i in range(5):
        x0 = 7.020 * M + i * 118.0
        pl = _surface_plate(side, x0, x0 + 82.0, -0.310 * M, -0.236 * M,
                            out=3.0, thick=13.0)
        if pl is not None:
            out.append(pl)
    return out


def _fasteners(side, x, z_lo, z_hi, count):
    if compound_from_instances is None:
        return None
    proto = P.style(Solid.make_sphere(8.5), "fastener", P.ALUM_DARK)
    inst = []
    for i in range(count):
        z = G.lerp(z_lo, z_hi, i / (count - 1))
        y = skin_y(x, z)
        if y is None:
            continue
        inst.append((proto, Location((x, side * (y - 3.0), z)), f"f{i}"))
    if len(inst) < 2:
        return None
    return compound_from_instances(
        f"cowl_fasteners_{'p' if side > 0 else 's'}_{int(x)}", inst)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

# ramp stations, as run along the duct from the capture plane
RAMP1 = (-30.0, 0.42 * M)          # fixed forward ramp
RAMP2 = (0.44 * M, 1.02 * M)       # first movable ramp, perforated forward
RAMP3 = (1.04 * M, 1.58 * M)       # second movable ramp, ends at the throat
BLEED = (0.46 * M, 0.70 * M)


def _side_parts(side):
    tag = "port" if side > 0 else "stbd"
    kids = []

    fwd, mid, aft = _duct_liner(side)
    kids.append(P.style(fwd, f"inlet_duct_fwd:{tag}", P.PANEL_LIGHT))
    kids.append(P.style(mid, f"inlet_duct_mid:{tag}", P.ALUM_DARK))
    kids.append(P.style(aft, f"inlet_duct_aft:{tag}", P.EXHAUST_SOOT))
    kids.append(P.style(_duct_cap(side), f"inlet_duct_face:{tag}", P.ENGINE_HOT))

    kids.append(P.style(_lip(side), f"inlet_lip:{tag}", P.PANEL_LIGHT))

    for i, (rng, drop) in enumerate(((RAMP1, 6.0), (RAMP2, 12.0), (RAMP3, 18.0)),
                                    start=1):
        kids.append(P.style(_ramp(side, rng[0], rng[1], drop),
                            f"inlet_ramp{i}:{tag}", P.GEAR_WHITE))
    kids.append(P.style(_bleed_panel(side, *BLEED), f"ramp_bleed_panel:{tag}",
                        P.PANEL_DARK))
    perf = _perforations(side, *BLEED)
    if perf is not None:
        kids.append(perf)

    a, b, c = _slot_liner(side)
    kids.append(P.style(a, f"diverter_wall_inbd:{tag}", P.ALUM_DARK))
    kids.append(P.style(b, f"diverter_wall_outbd:{tag}", P.ALUMINIUM))
    kids.append(P.style(c, f"diverter_roof:{tag}", P.PANEL_DARK))

    for i, (x0, x1, z0, z1) in enumerate(
            ((7.180 * M, 7.620 * M, -0.150 * M, 0.130 * M),
             (7.700 * M, 8.060 * M, -0.140 * M, 0.100 * M)), start=1):
        pl = _surface_plate(side, x0, x1, z0, z1)
        if pl is not None:
            kids.append(P.style(pl, f"bypass_door{i}:{tag}", P.PANEL_DARK))
    for i, pl in enumerate(_louvres(side), start=1):
        kids.append(P.style(pl, f"bleed_louvre:{tag}_{i:02d}", P.STEEL_DARK))

    # upper bypass door on the cowl crown, aft of the ramps: the F-14 dumps
    # excess duct air overboard here, and the panel is a landmark in top view
    y_c = _nac(7.900 * M)[0]
    z_top = SEC.surfaces(7.900 * M, side * y_c)[0]
    top = Box(0.560 * M, 0.300 * M, 18.0)
    top = Location((7.900 * M, side * y_c, z_top - 6.0)) * top
    kids.append(P.style(top, f"duct_bypass_door:{tag}", P.PANEL_DARK))

    for x in (6.980 * M, 7.640 * M):
        row = _fasteners(side, x + 26.0, -0.430 * M, 0.400 * M, 15)
        if row is not None:
            kids.append(row)
    return kids


def build():
    """Return ONE labelled group Compound, already in world position."""
    kids = []
    for side in (1, -1):
        kids.extend(_side_parts(side))
    return stance(group("inlets", kids))


# Built at import so the airframe module can pick them up without having to
# call anything: ``skin - inlets.SKIN_CUTTERS``.  WATERLINE frame -- apply
# ``stance`` AFTER cutting, exactly as ``airframe.build`` already does.
# Guarded: a cutter that fails to build must not take the whole module (and
# with it every visible inlet body) out of the aeroplane.
SKIN_CUTTERS = []
for _side in (1, -1):
    try:
        SKIN_CUTTERS.append(_side_cutter(_side))
    except Exception as _exc:  # noqa: BLE001
        import sys as _sys
        print(f"[inlets] skin cutter {_side:+d} failed: {_exc}", file=_sys.stderr)


if __name__ == "__main__":
    import time

    t0 = time.time()
    grp = build()
    t1 = time.time()
    print(f"cutters {len(SKIN_CUTTERS)}  build {t1 - t0:5.2f}s")
    print(f"leaves  {len(grp.leaves)}")
    bb = grp.bounding_box()
    print(f"bbox x {bb.min.X/M:6.3f}..{bb.max.X/M:6.3f}  "
          f"y {bb.min.Y/M:6.3f}..{bb.max.Y/M:6.3f}  "
          f"z {bb.min.Z/M:6.3f}..{bb.max.Z/M:6.3f}")
    print(f"capture {2*A_CAP/M:.3f} x {2*B_CAP/M:.3f} m at x={X_CAP/M:.3f}, "
          f"lip {X_MOUTH_TOP/M:.3f}..{rake_x(Z_LO)/M:.3f}")
