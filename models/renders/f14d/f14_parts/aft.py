"""F-14D aft fuselage systems.

Everything that lives on the aft deck, the beavertail and the aft belly:

* the DORSAL speed brake between the fins and the two VENTRAL brake doors on
  the belly -- closed and flush, as they sit on a parked aeroplane, but built
  as real doors inside a real recess with hinges and actuator rams behind
  them, not as a scribed rectangle;
* the BEAVERTAIL detail -- fuel dump mast, ram-air scoops, deck panelling;
* the TAILHOOK, stowed up in its trough, with the pivot, damper, shoe, bay
  doors and the rub/bumper pads;
* the aft ventral fairings, the engine-bay access panels, and the panel and
  fastener detail that ties the whole aft body together.

Everything is placed by QUERYING ``sections.surfaces`` so a door, fairing or
panel line sits exactly on the skin and stays there when the surface is tuned.
Four solids are published as :data:`SKIN_CUTTERS` -- the two brake recesses and
the hook trough -- because a door needs a cavity behind it and a trough is a
cavity by definition; ``airframe.py`` subtracts them from the skin in one
batched operation.

Frame: waterline-relative like every other part module; :func:`stance` lifts the
finished group onto the gear at the end.
"""

from __future__ import annotations

import math

from build123d import (Box, Compound, Cone, Cylinder, Face, Line, Plane,
                       Sphere, Spline, Vector, Wire, extrude, loft)

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts.context import group, mirror_pair, place
from f14_parts import palette as P

M = G.M

# ---------------------------------------------------------------------------
# stations
# ---------------------------------------------------------------------------

# The dorsal brake does NOT start at X_SPEEDBRAKE_FWD.  The dorsal spine lobe is
# still 0.11 m proud on the centreline at 13.9 m and dies out at 14.2 m, so a
# door hinged across it would ride over a ridge and read as a crumpled panel
# instead of a flat door.  It starts where the deck is genuinely flat.
X_DORSAL_FWD = 14.230 * M
X_DORSAL_AFT = 15.720 * M
Y_DORSAL_FWD = 1.238 * M        # half width; the fin root inner face is 1.365
Y_DORSAL_AFT = 1.152 * M

X_VENTRAL_FWD = G.X_SPEEDBRAKE_FWD
X_VENTRAL_AFT = G.X_SPEEDBRAKE_AFT
Y_VENTRAL_IN = 0.128 * M        # the keel strip between the two doors
Y_VENTRAL_OUT = 1.148 * M

DOOR_T = 52.0                   # door skin/structure thickness
DOOR_SINK = 2.0                 # door face below the surrounding skin
DOOR_GAP = 15.0                 # perimeter gap: 1.5 px of black at 1 px/10 mm
RECESS_D = 190.0                # brake bay depth behind the door
HINGE_STRIP = 130.0             # the forward hinge fairing strip, in x

# tailhook.  The shank is STRAIGHT and the trough is cut around it, so the two
# cannot drift apart when the belly line moves.
# The shank line is SOLVED against the belly, not eyeballed: the keel rises
# 160 mm between 16.0 and 18.2 m and steps 70 mm where the forebody lobe ends
# at 16.15, so the obvious "constant offset below the pivot" line comes out
# flush with the skin over the middle metre and the hook reads as a bulge on
# the belly instead of a hook lying in a trough.  These two ends keep the
# shank 50 mm clear of the keel at its two tightest stations.
X_HOOK_PIVOT = 15.980 * M
Z_HOOK_PIVOT = -0.598 * M
X_HOOK_END = 18.150 * M         # where the shank ends and the shoe begins
Z_HOOK_END = -0.471 * M
X_TROUGH_FWD = 15.790 * M
X_TROUGH_AFT = 18.520 * M       # runs out through the beavertail aft face
Y_TROUGH = 0.186 * M
TROUGH_ROOF = 0.105 * M         # trough roof above the hook axis
SHANK_R0 = 0.074 * M
SHANK_R1 = 0.058 * M

X_BEAVER_AFT = SEC.X_SKIN_AFT   # 18.300 -- where the one-piece skin stops


# ---------------------------------------------------------------------------
# surface-following primitives
# ---------------------------------------------------------------------------

_X_LIMIT = G.X_BEAVER_TIP - 4.0


def _surf(x, y, sign=1):
    """Outer skin z at (x, y): ``sign`` +1 upper surface, -1 lower.

    Clamped rather than allowed to return None -- a panel that runs a
    millimetre past the end of the loft should hug the last real section, not
    collapse to z=0 and tear the loft that is built from it.
    """
    xq = min(max(x, 1.0), _X_LIMIT)
    top, bot = SEC.surfaces(xq, y)
    z = top if sign > 0 else bot
    if z is None:
        w = SEC.outer_half_width(xq)
        yq = math.copysign(max(w - 8.0, 0.0), y if y else 1.0)
        top, bot = SEC.surfaces(xq, yq)
        z = top if sign > 0 else bot
    return 0.0 if z is None else z


def _solid(part):
    """The one solid out of a loft or boolean, as a LEAF shape."""
    solids = part.solids() if hasattr(part, "solids") else [part]
    if len(solids) == 1:
        return solids[0]
    return Compound(obj=list(solids))


def _band_wire(outer, inner):
    """Closed planar wire round a band: outer curve, two ends, inner curve."""
    edges = [Spline(*outer).edge(),
             Line(outer[-1], inner[-1]).edge(),
             Spline(*inner).edge(),
             Line(inner[0], outer[0]).edge()]
    return Wire(edges)


def _corner_inset(x, x0, x1, corner):
    """Lateral inset that turns a square plan corner into a quarter round."""
    if corner <= 1e-6:
        return 0.0
    d = min(x - x0, x1 - x)
    if d >= corner:
        return 0.0
    d = max(d, 0.0)
    return corner - math.sqrt(max(corner * corner - (corner - d) ** 2, 0.0))


def _stations(x0, x1, corner, nx):
    """Panel stations: clustered through the rounded corners, even between."""
    xs = []
    if corner > 1e-6:
        for k in range(5):
            xs.append(x0 + corner * (1.0 - math.cos(0.5 * math.pi * k / 4)))
            xs.append(x1 - corner * (1.0 - math.cos(0.5 * math.pi * k / 4)))
    else:
        xs += [x0, x1]
    a, b = x0 + corner, x1 - corner
    for i in range(nx + 1):
        xs.append(a + (b - a) * i / nx)
    out = []
    for v in sorted(xs):
        if not out or v - out[-1] > 1.0:
            out.append(v)
    return out


def _panel(x0, x1, ylo, yhi, sign=1, depth=DOOR_T, drop=0.0, corner=0.0,
           nx=8, ny=17):
    """A thin panel whose OUTER face lies on the skin.

    ``drop`` offsets that face outward (negative sinks it into the skin) and
    ``depth`` is measured inward from it, so the same call builds a door, a
    raised access panel, or -- with a big depth and a positive drop -- the
    recess cutter that door drops into.
    """
    faces = []
    for x in _stations(x0, x1, corner, nx):
        ins = _corner_inset(x, x0, x1, corner)
        a, b = ylo(x) + ins, yhi(x) - ins
        if b - a < 4.0:
            mid = 0.5 * (a + b)
            a, b = mid - 2.0, mid + 2.0
        outer, inner = [], []
        for i in range(ny):
            y = a + (b - a) * i / (ny - 1)
            z = _surf(x, y, sign) + sign * drop
            outer.append(Vector(x, y, z))
            inner.append(Vector(x, y, z - sign * depth))
        faces.append(Face(_band_wire(outer, inner)))
    return _solid(loft(faces, ruled=True))


def _round_rect(x0, x1, ylo, yhi, corner, nx=6, arc=4):
    """Plan outline of a panel: a rectangle with quarter-round corners.

    ``ylo``/``yhi`` are callables of x, so the outline can taper.
    """
    def edge(a, b, n, at_lo):
        out = []
        for i in range(n + 1):
            x = a + (b - a) * i / n
            ins = _corner_inset(x, x0, x1, corner)
            out.append((x, (ylo(x) + ins) if at_lo else (yhi(x) - ins)))
        return out

    def corner_run(x_end, sgn, at_lo):
        out = []
        for k in range(arc + 1):
            d = corner * (1.0 - math.cos(0.5 * math.pi * k / arc))
            x = x_end + sgn * d
            ins = _corner_inset(x, x0, x1, corner)
            out.append((x, (ylo(x) + ins) if at_lo else (yhi(x) - ins)))
        return out

    a, b = x0 + corner, x1 - corner
    pts = corner_run(x0, +1, True) + edge(a, b, nx, True)[1:-1]
    pts += corner_run(x1, -1, True)[::-1]
    pts += corner_run(x1, -1, False)
    pts += edge(b, a, nx, False)[1:-1]
    pts += corner_run(x0, +1, False)[::-1]
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1.0:
            out.append(p)
    return out


def _prism(outline, z_lo, z_hi):
    """A vertical prism from a plan outline -- ALL PLANAR FACES.

    Recess cutters are built this way rather than as surface-following lofts.
    A spline-surfaced cutter has to be intersected BSpline-against-BSpline with
    the skin, which took minutes; a polyhedral prism cuts in seconds and gives
    the bay the flat floor and square walls a real bay has anyway.
    """
    pts = [Vector(x, y, z_lo) for x, y in outline]
    n = len(pts)
    face = Face(Wire([Line(pts[i], pts[(i + 1) % n]).edge() for i in range(n)]))
    return _solid(extrude(face, amount=z_hi - z_lo, dir=(0, 0, 1)))


def _surf_range(x0, x1, ylo, yhi, sign, nx=7, ny=9):
    """(min, max) of the skin surface over a panel footprint."""
    lo, hi = 1e9, -1e9
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        a, b = ylo(x), yhi(x)
        for j in range(ny + 1):
            z = _surf(x, a + (b - a) * j / ny, sign)
            lo, hi = min(lo, z), max(hi, z)
    return lo, hi


def _ribbon(path, sign=1, width=11.0, proud=3.0, sink=30.0, along="x"):
    """A panel-line rib: a narrow strip standing a few mm off the skin.

    A scribed groove is half a pixel at aircraft scale and cannot read by
    shading, but the edge overlay draws this rib's two long edges, which is
    what a panel line actually looks like on a render.  Cheaper and far safer
    than adding dozens of tools to the skin's boolean.
    """
    faces = []
    for x, y in path:
        z = _surf(x, y, sign)
        zo, zi = z + sign * proud, z - sign * sink
        if along == "x":
            pts = [Vector(x, y - 0.5 * width, zo), Vector(x, y + 0.5 * width, zo),
                   Vector(x, y + 0.5 * width, zi), Vector(x, y - 0.5 * width, zi)]
        else:
            pts = [Vector(x - 0.5 * width, y, zo), Vector(x + 0.5 * width, y, zo),
                   Vector(x + 0.5 * width, y, zi), Vector(x - 0.5 * width, y, zi)]
        faces.append(Face(Wire([Line(pts[i], pts[(i + 1) % 4]).edge()
                                for i in range(4)])))
    return _solid(loft(faces, ruled=True))


def _line_x(y, x0, x1, sign=1, n=12, **kw):
    return _ribbon([(x0 + (x1 - x0) * i / n, y) for i in range(n + 1)],
                   sign=sign, along="x", **kw)


def _line_y(x, y0, y1, sign=1, n=14, **kw):
    return _ribbon([(x, y0 + (y1 - y0) * i / n) for i in range(n + 1)],
                   sign=sign, along="y", **kw)


def _rod(p0, p1, r0, r1=None):
    """A straight rod or tapered strut between two points."""
    d = Vector(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    length = d.length
    mid = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5, (p0[2] + p1[2]) * 0.5)
    shape = Cylinder(r0, length) if r1 is None else Cone(r0, r1, length)
    return Plane(origin=Vector(*mid), z_dir=d) * shape


def _domes(points, sign=1, r=8.0, proud=2.6):
    """A fastener row as ONE leaf: N shallow domes sunk into the skin.

    Individual rivets are 0.4 px on the aircraft and only read in close-up part
    renders -- but they read there, and they cost nothing as a single compound
    of spheres.  Never model them as boolean cuts.
    """
    out = []
    for x, y in points:
        z = _surf(x, y, sign) + sign * (proud - r)
        out.append(place(Sphere(r), x, y, z))
    return Compound(obj=out)


def _row_x(y, x0, x1, pitch, sign=1):
    n = max(int(abs(x1 - x0) / pitch), 1)
    return [(x0 + (x1 - x0) * i / n, y) for i in range(n + 1)]


def _row_y(x, y0, y1, pitch, sign=1):
    n = max(int(abs(y1 - y0) / pitch), 1)
    return [(x, y0 + (y1 - y0) * i / n) for i in range(n + 1)]


def _perimeter(x0, x1, y0, y1, pitch, inset=26.0):
    """Fastener stations just inside a panel outline."""
    a, b = x0 + inset, x1 - inset
    c, d = y0 + inset, y1 - inset
    pts = _row_x(c, a, b, pitch) + _row_x(d, a, b, pitch)
    pts += _row_y(a, c, d, pitch)[1:-1] + _row_y(b, c, d, pitch)[1:-1]
    return pts


# ---------------------------------------------------------------------------
# speed brakes
# ---------------------------------------------------------------------------


def _dorsal_half(x):
    t = G.clamp((x - X_DORSAL_FWD) / (X_DORSAL_AFT - X_DORSAL_FWD), 0.0, 1.0)
    return G.lerp(Y_DORSAL_FWD, Y_DORSAL_AFT, t)


def _dorsal_span(grow=0.0):
    """(ylo, yhi) of the dorsal door; ``grow`` widens it into its recess."""
    return (lambda x: -_dorsal_half(x) - grow,
            lambda x: _dorsal_half(x) + grow)


def _v_out(x):
    t = G.clamp((x - X_VENTRAL_FWD) / (X_VENTRAL_AFT - X_VENTRAL_FWD), 0.0, 1.0)
    return G.lerp(Y_VENTRAL_OUT, Y_VENTRAL_OUT - 0.055 * M, t)


def _ventral_span(side, grow=0.0):
    """(ylo, yhi) of one ventral door.  ylo is always the smaller value."""
    if side > 0:
        return (lambda x: Y_VENTRAL_IN - grow, lambda x: _v_out(x) + grow)
    return (lambda x: -_v_out(x) - grow, lambda x: -Y_VENTRAL_IN + grow)


def _brake_bay(x0, x1, ylo, yhi, sign):
    """The recess the door closes into -- published as a skin cutter.

    Grown past the door all round by the perimeter gap, and run well PROUD of
    the skin, because a cutter face coplanar with the target's is a classic
    kernel failure.
    """
    a, b = x0 - DOOR_GAP, x1 + DOOR_GAP
    out = _round_rect(a, b, ylo, yhi, 90.0)
    lo, hi = _surf_range(a, b, ylo, yhi, sign)
    if sign > 0:
        return _prism(out, lo - RECESS_D, hi + 120.0)
    return _prism(out, lo - 120.0, hi + RECESS_D)


def _brake_doors(x0, x1, ylo, yhi, sign, label, colour=None):
    """Hinge strip + main door, with a gap between them: the hinge line."""
    colour = colour or P.GREY_MID
    hinge_aft = x0 + HINGE_STRIP
    door_fwd = hinge_aft + DOOR_GAP
    strip = _panel(x0, hinge_aft, ylo, yhi, sign=sign, depth=DOOR_T * 0.8,
                   drop=-DOOR_SINK - 1.0, corner=70.0, nx=3)
    door = _panel(door_fwd, x1, ylo, yhi, sign=sign, depth=DOOR_T,
                  drop=-DOOR_SINK, corner=90.0, nx=8)
    return [P.style(strip, f"{label}_hinge_fairing", P.PANEL_DARK),
            P.style(door, f"{label}_door", colour)]


def _brake_gear(x0, x1, ylo, yhi, sign, label):
    """Hinges and actuator rams on the bay floor, under the closed door.

    They are only seen through the perimeter gap and in a cutaway -- but a door
    with nothing behind it reads as a scribed rectangle the moment the eye
    finds the gap, and the bay is a real cavity here.
    """
    kids = []
    lo, hi = _surf_range(x0, x1, ylo, yhi, sign)
    floor_z = (lo - RECESS_D) if sign > 0 else (hi + RECESS_D)

    def bay_z(x, y):
        return floor_z

    hinge_x = x0 + 0.5 * HINGE_STRIP
    span = yhi(hinge_x) - ylo(hinge_x)
    for i in range(3):
        y = ylo(hinge_x) + span * (0.14 + 0.36 * i)
        z = bay_z(hinge_x, y)
        lug = place(Box(96.0, 20.0, 108.0), hinge_x, y, z + sign * 40.0)
        kids.append(P.style(lug, f"{label}_hinge_lug:{i}", P.ALUM_DARK))
        pin = _rod((hinge_x, y - 62.0, z + sign * 74.0),
                   (hinge_x, y + 62.0, z + sign * 74.0), 15.0)
        kids.append(P.style(pin, f"{label}_hinge_pin:{i}", P.STEEL_DARK))

    for i, f in enumerate((0.30, 0.70)):
        y = ylo(x1) + (yhi(x1) - ylo(x1)) * f
        xa, xb = x0 + 0.34 * (x1 - x0), x1 - 0.16 * (x1 - x0)
        za = bay_z(xa, y) + sign * 44.0
        zb = bay_z(xb, y) + sign * 96.0
        body = _rod((xa, y, za), (0.62 * xa + 0.38 * xb, y, 0.62 * za + 0.38 * zb),
                    38.0)
        kids.append(P.style(body, f"{label}_ram_body:{i}", P.HYDRAULIC))
        rod = _rod((0.62 * xa + 0.38 * xb, y, 0.62 * za + 0.38 * zb),
                   (xb, y, zb), 21.0)
        kids.append(P.style(rod, f"{label}_ram_piston:{i}", P.OLEO_CHROME))
        clevis = place(Box(56.0, 46.0, 40.0), xb, y, zb)
        kids.append(P.style(clevis, f"{label}_ram_clevis:{i}", P.ALUM_DARK))
    return kids


def _speedbrakes():
    kids = []
    dlo, dhi = _dorsal_span()
    kids += _brake_doors(X_DORSAL_FWD, X_DORSAL_AFT, dlo, dhi, +1,
                         "speedbrake_dorsal")
    kids += _brake_gear(X_DORSAL_FWD, X_DORSAL_AFT, dlo, dhi, +1,
                        "speedbrake_dorsal")
    for side in (1, -1):
        vlo, vhi = _ventral_span(side)
        tag = "port" if side > 0 else "stbd"
        kids += _brake_doors(X_VENTRAL_FWD, X_VENTRAL_AFT, vlo, vhi, -1,
                             f"speedbrake_ventral_{tag}")
        kids += _brake_gear(X_VENTRAL_FWD, X_VENTRAL_AFT, vlo, vhi, -1,
                            f"speedbrake_ventral_{tag}")
    return kids


# ---------------------------------------------------------------------------
# beavertail: dump mast, ram-air scoops
# ---------------------------------------------------------------------------


def _dump_mast():
    """Fuel dump mast on the centreline at the beavertail trailing tip."""
    x = X_BEAVER_AFT
    z = 0.5 * (_surf(x - 60.0, 0.0, +1) + _surf(x - 60.0, 0.0, -1)) + 0.055 * M
    root = _rod((x - 0.230 * M, 0.0, z), (x - 0.020 * M, 0.0, z), 74.0, 44.0)
    tube = _rod((x - 0.030 * M, 0.0, z), (G.X_BEAVER_TIP + 0.190 * M, 0.0, z),
                33.0, 27.0)
    tip = _rod((G.X_BEAVER_TIP + 0.150 * M, 0.0, z),
               (G.X_BEAVER_TIP + 0.196 * M, 0.0, z), 21.0, 14.0)
    return [P.style(root, "dump_mast_fairing", P.TITANIUM),
            P.style(tube, "dump_mast", P.TITANIUM),
            P.style(tip, "dump_mast_tip", P.STEEL_BURN)]


def _scoop(x0, length, y, radius, label):
    """A ram-air scoop: a tube half sunk into the deck, open forward.

    The buried half is left in place rather than trimmed -- it is inside the
    skin and therefore invisible, and an intersection against a keep-box here
    buys nothing but a boolean that can fail.
    """
    z = _surf(x0 + 0.5 * length, y, +1) - radius * 0.34
    body = _rod((x0 - 0.020 * M, y, z), (x0 + length, y, z),
                radius * 1.05, radius * 0.90)
    bore = _rod((x0 - 0.070 * M, y, z + 0.06 * radius),
                (x0 + 0.60 * length, y, z + 0.06 * radius),
                radius * 0.70, radius * 0.54)
    shell = _solid(body - bore)
    plug = _rod((x0 + 0.54 * length, y, z + 0.06 * radius),
                (x0 + 0.62 * length, y, z + 0.06 * radius), radius * 0.66)
    return [P.style(shell, f"{label}_shell", P.GREY_MID),
            P.style(_solid(plug), f"{label}_throat", P.PANEL_DARK)]


def _beavertail():
    kids = _dump_mast()
    kids += _scoop(16.420 * M, 0.330 * M, 0.0, 76.0, "ram_air_scoop_centre")
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        kids += _scoop(17.050 * M, 0.220 * M, side * 0.520 * M, 46.0,
                       f"ram_air_scoop_{tag}")
    # the aft deck access panel over the fuel dump plumbing
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        pan = _panel(16.880 * M, 17.860 * M,
                     lambda x, s=side: min(s * 0.130 * M, s * 0.560 * M),
                     lambda x, s=side: max(s * 0.130 * M, s * 0.560 * M),
                     sign=+1, depth=34.0, drop=3.0, corner=60.0, nx=5, ny=9)
        kids.append(P.style(pan, f"beavertail_access_panel:{tag}", P.PANEL_DARK))
    return kids


# ---------------------------------------------------------------------------
# tailhook
# ---------------------------------------------------------------------------


def _hook_axis(x):
    t = (x - X_HOOK_PIVOT) / (X_HOOK_END - X_HOOK_PIVOT)
    return G.lerp(Z_HOOK_PIVOT, Z_HOOK_END, t)


def _trough_roof(x):
    """Trough roof height.

    Dropped BELOW the keel at the forward end so the cut runs out to nothing
    there: the cutter takes everything under the roof, so a roof that is
    lifted at the front digs a DEEPER hole, not a shallower one.
    """
    t = G.clamp((x - X_TROUGH_FWD) / (0.420 * M), 0.0, 1.0)
    return _hook_axis(x) + TROUGH_ROOF - 0.340 * M * (1.0 - t) ** 2


def _hook_trough():
    """The hook well, published as a skin cutter.

    Cut around the STRAIGHT shank rather than offset from the belly line, so
    the hook cannot drift out of its own trough when the aft body is retuned.
    """
    faces = []
    # A short explicit station list: every face of the result is then planar
    # (two vertical walls, a ruled roof), which is what keeps the skin boolean
    # cheap.  Dense only through the forward roof ramp.
    xs = [X_TROUGH_FWD, X_TROUGH_FWD + 70.0, X_TROUGH_FWD + 150.0,
          X_TROUGH_FWD + 230.0, X_TROUGH_FWD + 310.0,
          16.700 * M, 17.500 * M, X_TROUGH_AFT]
    for x in xs:
        ins = _corner_inset(x, X_TROUGH_FWD, X_TROUGH_AFT, 90.0)
        w = max(Y_TROUGH - ins, 40.0)
        roof = _trough_roof(x)
        pts = [Vector(x, -w, roof), Vector(x, w, roof),
               Vector(x, w, roof - 0.900 * M), Vector(x, -w, roof - 0.900 * M)]
        faces.append(Face(Wire([Line(pts[i], pts[(i + 1) % 4]).edge()
                                for i in range(4)])))
    return _solid(loft(faces, ruled=True))


def _hook_shoe(x_root, z_root):
    """The flattened shoe: a forged claw with a wire throat under it."""
    prof = [(0.000, 0.062), (0.150, 0.076), (0.268, 0.058), (0.322, 0.006),
            (0.300, -0.062), (0.238, -0.098), (0.196, -0.052),
            (0.120, -0.030), (0.052, -0.048), (0.000, -0.060)]
    pts = [Vector(x_root + a * M, 0.0, z_root + b * M) for a, b in prof]
    half = 0.088 * M
    faces = []
    for y in (-half, half):
        ring = [Vector(p.X, y, p.Z) for p in pts]
        edges = [Line(ring[i], ring[(i + 1) % len(ring)]).edge()
                 for i in range(len(ring))]
        faces.append(Face(Wire(edges)))
    return _solid(loft(faces, ruled=True))


def _tailhook():
    kids = []
    shank = _rod((X_HOOK_PIVOT, 0.0, Z_HOOK_PIVOT),
                 (X_HOOK_END, 0.0, Z_HOOK_END), SHANK_R0, SHANK_R1)
    kids.append(P.style(shank, "tailhook_shank", P.GEAR_WHITE))

    # pivot: two lugs on the trough roof and the pin through them
    for i, side in enumerate((1, -1)):
        lug = place(Box(180.0, 26.0, 150.0), X_HOOK_PIVOT - 30.0,
                    side * 106.0, Z_HOOK_PIVOT + 40.0)
        kids.append(P.style(lug, f"tailhook_pivot_lug:{'port' if side > 0 else 'stbd'}",
                            P.ALUM_DARK))
    pin = _rod((X_HOOK_PIVOT, -0.132 * M, Z_HOOK_PIVOT),
               (X_HOOK_PIVOT, 0.132 * M, Z_HOOK_PIVOT), 30.0)
    kids.append(P.style(pin, "tailhook_pivot_pin", P.STEEL_DARK))
    boss = _rod((X_HOOK_PIVOT - 40.0, 0.0, Z_HOOK_PIVOT),
                (X_HOOK_PIVOT + 130.0, 0.0, Z_HOOK_PIVOT), 92.0, 78.0)
    kids.append(P.style(boss, "tailhook_pivot_boss", P.ALUM_DARK))

    # damper: body on the trough roof, rod down onto a collar on the shank
    d0 = (16.480 * M, 0.0, _trough_roof(16.480 * M) - 30.0)
    d1 = (16.980 * M, 0.0, _hook_axis(16.980 * M) + 30.0)
    mid = tuple(G.lerp(d0[i], d1[i], 0.55) for i in range(3))
    kids.append(P.style(_rod(d0, mid, 62.0), "tailhook_damper_body", P.HYDRAULIC))
    kids.append(P.style(_rod(mid, d1, 30.0), "tailhook_damper_rod", P.OLEO_CHROME))
    collar = _rod((17.010 * M, 0.0, _hook_axis(17.010 * M)),
                  (17.120 * M, 0.0, _hook_axis(17.120 * M)), 84.0)
    kids.append(P.style(collar, "tailhook_damper_collar", P.ALUM_DARK))

    # shoe
    kids.append(P.style(_hook_shoe(X_HOOK_END - 0.030 * M,
                                   Z_HOOK_END - 0.026 * M),
                        "tailhook_shoe", P.STEEL_DARK))

    # rub plate the stowed shoe beds against, in the trough roof
    plate = _panel(17.760 * M, 18.240 * M,
                   lambda x: -0.126 * M, lambda x: 0.126 * M,
                   sign=-1, depth=26.0,
                   drop=_surf(18.0 * M, 0.0, -1) - _trough_roof(18.0 * M),
                   corner=50.0, nx=3, ny=5)
    kids.append(P.style(plate, "tailhook_rub_plate", P.STEEL_BURN))

    # bay doors over the forward half of the well
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        lo = (lambda x, s=side: min(s * 14.0, s * (Y_TROUGH - 16.0)))
        hi = (lambda x, s=side: max(s * 14.0, s * (Y_TROUGH - 16.0)))
        door = _panel(16.080 * M, 16.860 * M, lo, hi, sign=-1, depth=34.0,
                      drop=-DOOR_SINK, corner=40.0, nx=5, ny=5)
        kids.append(P.style(door, f"tailhook_bay_door:{tag}", P.GEAR_WHITE))

    # arresting-hook bumpers under the beavertail tip
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        y = side * 0.325 * M
        z = _surf(18.180 * M, y, -1)
        pad = place(Sphere(0.115 * M), 18.180 * M, y, z + 0.086 * M)
        kids.append(P.style(pad, f"hook_bumper:{tag}", P.RUBBER))
    return kids


# ---------------------------------------------------------------------------
# ventral fairings and engine bay panels
# ---------------------------------------------------------------------------


def _fairing(x0, x1, y_mid, half_w, proud, sign=-1, nx=9, ny=13):
    """A long shallow blister on the skin, faded out at both ends."""
    faces = []
    xs = [x0 + (x1 - x0) * i / nx for i in range(nx + 1)]
    for x in xs:
        t = G.clamp(min(x - x0, x1 - x) / (0.240 * M), 0.0, 1.0)
        e = t * t * (3.0 - 2.0 * t)
        w = half_w * G.lerp(0.34, 1.0, e)
        h = proud * G.lerp(0.02, 1.0, e)
        outer, inner = [], []
        for i in range(ny):
            u = -1.0 + 2.0 * i / (ny - 1)
            y = y_mid + w * u
            z = _surf(x, y, sign)
            lift = h * math.sqrt(max(1.0 - u * u, 0.0))
            outer.append(Vector(x, y, z + sign * lift))
            inner.append(Vector(x, y, z - sign * 60.0))
        faces.append(Face(_band_wire(outer, inner)))
    return _solid(loft(faces, ruled=True))


def _ventral():
    kids = []
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        fair = _fairing(15.720 * M, 18.240 * M, side * 0.470 * M,
                        0.118 * M, 0.052 * M, sign=-1)
        kids.append(P.style(fair, f"ventral_fairing:{tag}", P.GREY_MID))
        # engine bay access panel, lower nacelle
        yn = G.nacelle(16.700 * M)[0]
        pan = _panel(15.760 * M, 17.560 * M,
                     lambda x, s=side: min(s * (G.nacelle(x)[0] - 0.360 * M),
                                           s * (G.nacelle(x)[0] + 0.360 * M)),
                     lambda x, s=side: max(s * (G.nacelle(x)[0] - 0.360 * M),
                                           s * (G.nacelle(x)[0] + 0.360 * M)),
                     sign=-1, depth=36.0, drop=3.5, corner=90.0, nx=8, ny=15)
        kids.append(P.style(pan, f"engine_bay_panel:{tag}", P.PANEL_DARK))
        rows = _perimeter(15.760 * M, 17.560 * M,
                          min(side * (yn - 0.360 * M), side * (yn + 0.360 * M)),
                          max(side * (yn - 0.360 * M), side * (yn + 0.360 * M)),
                          0.088 * M, inset=30.0)
        kids.append(P.style(_domes(rows, sign=-1),
                            f"engine_bay_fasteners:{tag}", P.GREY_MID))
    return kids


# ---------------------------------------------------------------------------
# panel and fastener detail
# ---------------------------------------------------------------------------


def _panel_lines():
    deck, belly = [], []
    # transverse frames, upper deck
    for x in (13.320 * M, 16.320 * M, 16.980 * M, 17.640 * M, 18.180 * M):
        w = 1.330 * M if x < 16.0 * M else 1.240 * M
        deck.append(_line_y(x, -w, w, sign=+1, n=18))
    # longitudinal seams: the fin-root line and the beavertail deck
    for side in (1, -1):
        deck.append(_line_x(side * 1.336 * M, 13.100 * M, 18.220 * M,
                            sign=+1, n=16))
        deck.append(_line_x(side * 0.128 * M, 16.240 * M, 18.240 * M,
                            sign=+1, n=8))
    # transverse frames, belly
    for x in (13.400 * M, 15.840 * M, 16.460 * M, 17.120 * M, 17.780 * M):
        w = 1.350 * M
        belly.append(_line_y(x, -w, w, sign=-1, n=18))
    for side in (1, -1):
        belly.append(_line_x(side * 1.196 * M, 13.100 * M, 18.220 * M,
                             sign=-1, n=16))
        belly.append(_line_x(side * 0.700 * M, 15.720 * M, 18.220 * M,
                             sign=-1, n=10))
    kids = [P.style(Compound(obj=deck), "panel_lines_deck", P.PANEL_DARK),
            P.style(Compound(obj=belly), "panel_lines_belly", P.PANEL_DARK)]

    rows = []
    for side in (1, -1):
        rows += _row_x(side * 1.336 * M, 13.200 * M, 18.180 * M, 0.104 * M)
    kids.append(P.style(_domes(rows, sign=+1), "deck_seam_fasteners", P.GREY_MID))
    rows = []
    for side in (1, -1):
        rows += _row_x(side * 1.196 * M, 13.200 * M, 18.180 * M, 0.104 * M)
    kids.append(P.style(_domes(rows, sign=-1), "belly_seam_fasteners", P.GREY_MID))
    return kids


# ---------------------------------------------------------------------------
# skin cutters -- built at IMPORT time: airframe.build() reads this list before
# our own build() has run.
# ---------------------------------------------------------------------------


def _build_cutters():
    out = []
    dlo, dhi = _dorsal_span(DOOR_GAP)
    out.append(_brake_bay(X_DORSAL_FWD, X_DORSAL_AFT, dlo, dhi, +1))
    for side in (1, -1):
        vlo, vhi = _ventral_span(side, DOOR_GAP)
        out.append(_brake_bay(X_VENTRAL_FWD, X_VENTRAL_AFT, vlo, vhi, -1))
    out.append(_hook_trough())
    return out


SKIN_CUTTERS = _build_cutters()


def build():
    """Return ONE labelled group Compound, already in world position."""
    kids = []
    kids += _speedbrakes()
    kids += _beavertail()
    kids += _tailhook()
    kids += _ventral()
    kids += _panel_lines()
    return stance(group("aft", kids))


if __name__ == "__main__":
    import time

    t0 = time.time()
    g = build()
    print(f"aft: {len(g.children)} leaves in {time.time() - t0:.1f}s")
    bb = g.bounding_box()
    print(f"bbox x {bb.min.X / M:7.3f}..{bb.max.X / M:7.3f}  "
          f"y {bb.min.Y / M:7.3f}..{bb.max.Y / M:7.3f}  "
          f"z {bb.min.Z / M:7.3f}..{bb.max.Z / M:7.3f}")
    for c in SKIN_CUTTERS:
        cb = c.bounding_box()
        print(f"cutter vol {c.volume / 1e9:7.4f} m^3  "
              f"x {cb.min.X / M:6.2f}..{cb.max.X / M:6.2f}")
