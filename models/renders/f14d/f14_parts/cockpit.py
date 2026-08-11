"""F-14D cockpit: the opening, the transparencies, and everything under them.

THE SURFACE ARGUMENT
--------------------
``body.py`` lofts the airframe skin THROUGH the canopy's own outer surface --
``geometry.canopy_lobe`` is a lobe of the section blend like any other, so the
body already carries the bubble as solid material.  This module therefore does
two halves of one job:

1. It CUTS the cockpit opening out of that bubble.  The cutter is exposed as
   :data:`SKIN_CUTTERS`, in the WATERLINE frame, before ``stance()``; the
   airframe module applies it to the skin.
2. It rebuilds the transparency FROM THE SAME FUNCTIONS -- every outer point of
   the canopy, the windscreen and every frame is ``sections.surfaces(x, y)``.
   The glass is literally the surface that was removed, so it sits exactly on
   the skin it came from and the canopy-to-spine fairing at the aft bow is
   continuous by construction rather than a gap that has to be fudged shut.

Nothing here hard-codes a canopy coordinate.  In particular the SILL and the
RAIL line are SOLVED against the surface, not assumed.  The first attempt put
the sill a fixed drop below the forebody crown line and the rail band came out
inverted: the bubble's flank is very nearly vertical at its foot -- at the apex
station the skin falls 140 mm in the 25 mm of half-width outboard of it -- so
the deck beside the canopy is already 120 mm BELOW the crown.  The sill is
therefore taken from the skin at the lobe silhouette, and the rail from a fixed
HEIGHT above that sill, which is what makes it a constant-looking band instead
of a fin that grows with the bubble.

IMPORT ORDER.  ``airframe`` imports this module for :data:`SKIN_CUTTERS`, so
this module must NOT import ``airframe`` at module level -- ``stance`` is
imported lazily inside :func:`build`.  The cycle then never closes at import
time whichever module is loaded first.
"""

from __future__ import annotations

import math
from functools import lru_cache

from build123d import (Compound, Edge, Face, Location, Plane, Pos, Rectangle,
                       RectangleRounded, Solid, Spline, Vector, Wire, extrude,
                       loft)

from f14_parts import geometry as G
from f14_parts import palette as P
from f14_parts import sections as SEC
from f14_parts.context import group, mirror_pair

# ---------------------------------------------------------------------------
# stations -- from geometry, never invented
# ---------------------------------------------------------------------------

X_OPEN_FWD = G.X_WINDSCREEN           # 3.870 m  windscreen base / opening front
X_JOINT = G.X_CANOPY_FWD              # 4.290 m  windscreen -> canopy
X_OPEN_AFT = G.X_CANOPY_AFT           # 7.190 m  aft arch / turtledeck

# frame bands in x; the transparencies fill what is left between them
X_WS_BOW = (X_OPEN_FWD + 2, X_OPEN_FWD + 78)
X_WS_GLASS = (X_OPEN_FWD + 72, X_JOINT - 46)
X_WS_ARCH = (X_JOINT - 50, X_JOINT + 10)
X_CAN_BOW_F = (X_JOINT + 8, X_JOINT + 122)
X_CAN_GLASS = (X_JOINT + 116, X_OPEN_AFT - 152)
X_CAN_BOW_A = (X_OPEN_AFT - 158, X_OPEN_AFT - 4)

# cockpit furniture
X_COAM_P = (X_OPEN_FWD + 76, 4218.0)  # pilot anti-glare shield / coaming
X_IP_PILOT = 4252.0                   # pilot instrument panel face
X_SEAT_PILOT = 4940.0
X_BULK_MID = 5462.0
X_COAM_R = (5516.0, 5606.0)
X_IP_RIO = 5636.0
X_SEAT_RIO = 6300.0
X_BULK_AFT = 6890.0

# ---------------------------------------------------------------------------
# the sill / rail / well scheme
# ---------------------------------------------------------------------------

CUT_MARGIN = 30.0        # opening rim, outboard of the lobe silhouette
SILL_DROP = 22.0         # rim cut below the skin, leaving a lip to seal against
RAIL_ARC = 96.0          # canopy rail width, MEASURED ALONG THE SURFACE
RAIL_PROUD = 12.0        # frames stand this far off the skin surface
TUB_INSET = 34.0         # well inboard of the rail foot -- leaves the ledge
TUB_HALF_MAX = 432.0

GLASS_T = 12.0           # canopy transparency
WS_T = 16.0              # windscreen quarter panels
WS_FLAT_T = 22.0         # armoured flat front panel
BOW_T = 62.0
POST_W = 27.0

Z_TOP = 2400.0           # cutter roof, safely above the crown
COAM_CAP_P = 1012.0      # pilot coaming top -- sets over-the-nose vision
COAM_CAP_R = 1040.0
COAM_GAP = 30.0          # coaming clearance under the skin

# interior colours the shared palette does not carry
SCOPE_FACE = "#2C3A34"       # unlit CRT / display glass
PANEL_GREY = "#4A4F55"       # sub-panels that break up the black
MIRROR_FACE = "#C4CBD1"

SEAT_BASE_Z = 200.0
SEAT_RECLINE = 15.0      # degrees, whole seat tilted aft


@lru_cache(maxsize=8192)
def SURF(x, y):
    """Top of the airframe skin -- the authoritative surface query."""
    t = SEC.surfaces(x, y)[0]
    return -1.0e6 if t is None else t


@lru_cache(maxsize=2048)
def HW(x):
    return G.canopy_lobe(x)[0]


@lru_cache(maxsize=2048)
def W_CUT(x):
    """Half-width of the skin opening: just outboard of the lobe silhouette."""
    return HW(x) + CUT_MARGIN


@lru_cache(maxsize=2048)
def SILL(x):
    """Opening rim height, taken FROM THE SKIN at the rim, not from a datum."""
    return SURF(x, W_CUT(x)) - SILL_DROP


@lru_cache(maxsize=2048)
def W_RAIL(x):
    """Half-width where the rail ends and the transparency starts.

    Measured as ARC LENGTH along the skin, walking inboard from the rim -- not
    as a height and not as a y inset.  Both of those were tried and both fail
    on this section: the bubble's flank runs at ~84 deg, so a band of fixed
    height has almost no width in y and lands the sample points either side of
    a 300 mm step, while a band of fixed y-width is a 250 mm slab.  Arc length
    is the only measure that gives the constant-looking rail the aircraft has,
    and it automatically widens under the windscreen where the surface lies
    down -- which is also what the aircraft does.
    """
    y, z, arc = W_CUT(x), SURF(x, W_CUT(x)), 0.0
    while y > 48.0 and arc < RAIL_ARC:
        y2 = y - 1.2
        z2 = SURF(x, y2)
        arc += math.hypot(1.2, z2 - z)
        y, z = y2, z2
    return y


@lru_cache(maxsize=2048)
def W_TUB(x):
    return min(W_RAIL(x) - TUB_INSET, TUB_HALF_MAX)


@lru_cache(maxsize=2048)
def FLOOR(x):
    """Well floor: deep through the tub, shallow at both ends so the cut sinks
    no pit into the avionics bay ahead or the turtledeck behind."""
    f = G.lerp(430.0, 100.0, G.smoothstep(X_OPEN_FWD, 4200.0, x))
    return G.lerp(f, 700.0, G.smoothstep(6820.0, 7150.0, x))


def W_DIV(x):
    """Half-width of the windscreen's flat armoured centre panel."""
    return 0.46 * W_RAIL(x)


# ---------------------------------------------------------------------------
# construction helpers
# ---------------------------------------------------------------------------


def _cos(a, b, n):
    """n samples from a to b, crowded at BOTH ends where curvature is worst."""
    return [a + (b - a) * 0.5 * (1.0 - math.cos(math.pi * i / (n - 1)))
            for i in range(n)]


def _lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _offset_in(pts, t):
    """Offset a (y, z) polyline by ``t`` along its inward normal.

    The run crosses a dome left to right, so rotating the tangent -90 deg gives
    the inward normal everywhere -- including the near-vertical flanks, where it
    turns horizontal and the wall thickness stays honest instead of collapsing.
    """
    n = len(pts)
    out = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        ty, tz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ty, tz) or 1.0
        out.append((pts[i][0] + t * tz / L, pts[i][1] - t * ty / L))
    return out


def _face(x, runs):
    """Closed planar face at station x from a list of (y, z) point runs.

    Two-point runs become lines, longer runs splines; runs are joined end to
    end and the loop closes.  Every station of one loft must produce the SAME
    edge count or the surface twists, so run structure is fixed per solid.
    """
    pts = [[Vector(x, y, z) for y, z in run] for run in runs]
    edges = []
    for k, run in enumerate(pts):
        edges.append(Edge.make_line(run[0], run[1]) if len(run) == 2
                     else Spline(*run).edge())
        nxt = pts[(k + 1) % len(pts)][0]
        if (nxt - run[-1]).length > 1e-7:
            edges.append(Edge.make_line(run[-1], nxt))
    return Face(Wire(edges))


def _poly_runs(pts):
    """Turn a point list into consecutive two-point runs -- an all-line loop.

    Used where a spline would overshoot: the rail crosses the shoulder where
    the surface turns 55 deg in 20 mm, and an interpolating spline through
    that loops back on itself and the face comes out invalid.
    """
    return [[pts[i], pts[i + 1]] for i in range(len(pts) - 1)]


def _band(x0, x1, y_lo, y_hi, thick, dz=0.0, nx=16, ny=26):
    """A sheet of constant thickness lying ON the skin surface.

    ``y_lo``/``y_hi`` are callables of x so a band can follow the rail line,
    the windscreen divider or the lobe silhouette as the section changes.
    """
    faces = []
    for x in _cos(x0, x1, nx):
        ys = _cos(y_lo(x), y_hi(x), ny)
        outer = [(y, SURF(x, y) + dz) for y in ys]
        inner = _offset_in(outer, thick)
        faces.append(_face(x, [outer, list(reversed(inner))]))
    return loft(faces)


def _plug(x0, x1, y_fn, z_bot, z_cap, gap, nx=9, ny=20):
    """A solid that fills the opening up to the lower of skin-minus-gap or a
    flat cap.  The pilot's coaming is exactly this: a deck under the
    windscreen whose height is set by the over-the-nose sight line."""
    faces = []
    for x in _cos(x0, x1, nx):
        w = y_fn(x)
        zb = z_bot(x)
        top = [(y, min(SURF(x, y) - gap, z_cap)) for y in _cos(-w, w, ny)]
        faces.append(_face(x, [top, [(w, zb), (-w, zb)]]))
    return loft(faces)


def _box(x0, x1, y0, y1, z0, z1, r=0.0, axis="z"):
    """Axis-aligned box, optionally with corners rounded in one plane.

    Roundness is authored in the 2D profile before extrusion -- never as a 3D
    fillet after a boolean, which OCC does not survive on this model.
    """
    # Bounds are normalised so a mirrored call -- ``side * a, side * b`` -- can
    # hand them over in either order without silently producing a negative
    # extent, which RectangleRounded rejects and Rectangle would accept.
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    c = (0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1))
    if axis == "z":
        sk = RectangleRounded(dx, dy, r) if r > 1e-6 else Rectangle(dx, dy)
        s = extrude(sk, amount=dz / 2, both=True)
    elif axis == "x":
        sk = RectangleRounded(dy, dz, r) if r > 1e-6 else Rectangle(dy, dz)
        s = extrude(Plane.YZ * sk, amount=dx / 2, both=True)
    else:
        sk = RectangleRounded(dz, dx, r) if r > 1e-6 else Rectangle(dz, dx)
        s = extrude(Plane.ZX * sk, amount=dy / 2, both=True)
    return Pos(*c) * s


def _rod(p0, p1, r):
    a, b = Vector(*p0), Vector(*p1)
    d = b - a
    return Solid.make_cylinder(r, d.length, Plane(origin=a, z_dir=d))


def _disc(centre, r, t, normal=(1, 0, 0)):
    c = Vector(*centre)
    n = Vector(*normal).normalized()
    return Solid.make_cylinder(r, t, Plane(origin=c - n * (t * 0.5), z_dir=n))


def _fuse(parts):
    """Fuse a list of solids into ONE shape.

    Fusing DISJOINT solids returns a ``ShapeList``, not a Shape -- and
    ``Location * ShapeList`` raises "other must be a list of Locations", which
    reads like a transform bug rather than a fuse that declined to merge.  The
    alternating segments of a striped handle never touch, so this is the normal
    case here, not the edge case.  Collapsing to a single ``Compound`` keeps the
    result one styleable leaf.
    """
    out = parts[0]
    for p in parts[1:]:
        out = out + p
    if isinstance(out, (list, tuple)) or type(out).__name__ == "ShapeList":
        return Compound(list(out))
    return out


def _striped(p0, p1, r, n=7):
    """A grab handle split into alternating segments.

    Returns (yellow, black).  Both halves straddle the centreline, so each
    solid keeps a mirror partner in the symmetry audit.
    """
    a, b = Vector(*p0), Vector(*p1)
    yel, blk = [], []
    for i in range(n):
        s = a + (b - a) * (i / n)
        e = a + (b - a) * ((i + 1) / n)
        (yel if i % 2 == 0 else blk).append(_rod(s, e, r))
    return _fuse(yel), (_fuse(blk) if blk else None)


# ---------------------------------------------------------------------------
# THE SKIN CUTTER -- the opening, and the well under it
# ---------------------------------------------------------------------------


def _cut_section(x):
    """Cockpit cavity section: a wide slot above the sill over a narrower well.

    Eight points every station so the loft matches index for index.  Above the
    sill the cut takes the whole bubble out to ``W_CUT``; below it the well
    steps inboard to ``W_TUB``, and the ledge that step leaves IS the sill the
    canopy rail and its seal sit on.
    """
    wc, wt, sz, fz = W_CUT(x), W_TUB(x), SILL(x), FLOOR(x)
    return [(-wt, fz), (wt, fz), (wt, sz), (wc, sz), (wc, Z_TOP),
            (-wc, Z_TOP), (-wc, sz), (-wt, sz)]


def build_skin_cutter():
    """One solid: everything the cockpit takes out of the airframe skin."""
    faces = []
    for x in _cos(X_OPEN_FWD, X_OPEN_AFT, 26):
        pts = _cut_section(x)
        runs = [[pts[i], pts[(i + 1) % len(pts)]] for i in range(len(pts))]
        faces.append(_face(x, runs))
    return loft(faces)


#: Cutter solids for the airframe skin, in the WATERLINE frame (pre-``stance``).
#: The airframe applies them as ONE batched subtract: ``skin - SKIN_CUTTERS``.
SKIN_CUTTERS = [build_skin_cutter()]


def cut_skin(skin):
    """Convenience for the airframe module: apply every cockpit cutter."""
    return skin - list(SKIN_CUTTERS)


# ---------------------------------------------------------------------------
# transparencies and frames
# ---------------------------------------------------------------------------


def _rail(side):
    """The canopy rail / sill bar, windscreen base to aft arch."""
    faces = []
    for x in _cos(X_OPEN_FWD + 1, X_OPEN_AFT - 1, 28):
        wi, wo, sz = W_RAIL(x), W_CUT(x), SILL(x)
        pts = [(side * y, SURF(x, y) + RAIL_PROUD) for y in _lin(wi, wo, 11)]
        pts += [(side * wo, sz), (side * wi, sz), pts[0]]
        if side < 0:
            pts = list(reversed(pts))
        faces.append(_face(x, _poly_runs(pts)))
    return loft(faces)


def _seal(side):
    """Canopy-to-fuselage seal, on the ledge the well step leaves."""
    faces = []
    for x in _cos(X_OPEN_FWD + 8, X_OPEN_AFT - 8, 18):
        wo = W_RAIL(x)
        wi = max(W_TUB(x), wo - 46)
        sz = SILL(x)
        pts = [(side * wi, sz + 2), (side * wo, sz + 2),
               (side * wo, sz + 22), (side * wi, sz + 22)]
        if side < 0:
            pts = list(reversed(pts))
        faces.append(_face(x, [[pts[i], pts[(i + 1) % 4]] for i in range(4)]))
    return loft(faces)


def _bow(x0, x1, thick, ny=24):
    """A transverse frame arch, landing its feet on the rails."""
    return _band(x0, x1, lambda x: -W_RAIL(x), W_RAIL, thick,
                 dz=RAIL_PROUD, nx=7, ny=ny)


def _ws_bow_solid():
    """The windscreen base frame.

    SOLID, not an arch: it is the top of the forward avionics bay on the real
    aircraft, and an arch there would leave a slot looking straight down into
    the well from a low front quarter.
    """
    faces = []
    for x in _cos(X_WS_BOW[0], X_WS_BOW[1], 8):
        w, sz = W_RAIL(x), SILL(x)
        top = [(y, SURF(x, y) + RAIL_PROUD) for y in _cos(-w, w, 20)]
        faces.append(_face(x, [top, [(w, sz), (-w, sz)]]))
    return loft(faces)


def _canopy_glass():
    return _band(*X_CAN_GLASS, lambda x: -W_RAIL(x), W_RAIL, GLASS_T,
                 nx=22, ny=30)


def _ws_quarter(side):
    if side > 0:
        return _band(*X_WS_GLASS, lambda x: W_DIV(x) + POST_W, W_RAIL,
                     WS_T, nx=8, ny=16)
    return _band(*X_WS_GLASS, lambda x: -W_RAIL(x),
                 lambda x: -(W_DIV(x) + POST_W), WS_T, nx=8, ny=16)


def _ws_post(side):
    if side > 0:
        return _band(*X_WS_GLASS, lambda x: W_DIV(x) - 6,
                     lambda x: W_DIV(x) + POST_W + 6, 46.0, dz=9.0,
                     nx=8, ny=8)
    return _band(*X_WS_GLASS, lambda x: -(W_DIV(x) + POST_W + 6),
                 lambda x: -(W_DIV(x) - 6), 46.0, dz=9.0, nx=8, ny=8)


def _ws_flat():
    """The flat bulletproof front panel.

    Its four corners are taken off the bubble at the divider line, so it is
    inscribed in the very surface the frame follows -- flat glass set into a
    curved frame, dipping only ~20 mm below the crown across its width, which
    is what the aircraft looks like.
    """
    xa, xb = X_WS_GLASS[0] + 6, X_WS_GLASS[1] - 4
    ya, yb = W_DIV(xa), W_DIV(xb)
    za, zb = SURF(xa, ya), SURF(xb, yb)
    a = Vector(xa, -ya, za)
    b = Vector(xa, ya, za)
    c = Vector(xb, yb, zb)
    d = Vector(xb, -yb, zb)
    face = Face(Wire([Edge.make_line(a, b), Edge.make_line(b, c),
                      Edge.make_line(c, d), Edge.make_line(d, a)]))
    n = (b - a).cross(c - b).normalized()
    if n.Z > 0:
        n = -n
    return extrude(face, amount=WS_FLAT_T, dir=n)


# ---------------------------------------------------------------------------
# cockpit well and furniture
# ---------------------------------------------------------------------------


def _tub_shell():
    """Floor and side walls of the well, as one lining."""
    def prism(inset, z0f, z1f):
        faces = []
        for x in _cos(X_OPEN_FWD + 12, X_BULK_AFT + 40, 22):
            w = max(W_TUB(x) - inset, 20.0)
            z0 = FLOOR(x) + z0f
            zt = SILL(x) + z1f
            pts = [(-w, z0), (w, z0), (w, zt), (-w, zt)]
            faces.append(_face(x, [[pts[i], pts[(i + 1) % 4]]
                                   for i in range(4)]))
        return loft(faces)
    return prism(3.0, 3.0, -2.0) - prism(30.0, 30.0, 60.0)


def _bulkhead(x0, x1, z_top, r=26):
    xm = 0.5 * (x0 + x1)
    w = W_TUB(xm) - 32
    return _box(x0, x1, -w, w, FLOOR(xm) + 30, z_top, r=r, axis="x")


def _console(side, x0, x1):
    """Side console: a tapered box following the well wall."""
    faces = []
    for x in _cos(x0, x1, 8):
        yo, yi = W_TUB(x) - 32, 186.0
        z1, z0 = SILL(x) - 75, FLOOR(x) + 26
        pts = [(side * yi, z0), (side * yo, z0), (side * yo, z1),
               (side * yi, z1)]
        if side < 0:
            pts = list(reversed(pts))
        faces.append(_face(x, [[pts[i], pts[(i + 1) % 4]] for i in range(4)]))
    return loft(faces)


def _console_panels(side, x0, x1, n=5):
    """Raised switch panels along a console top.

    Detail here is not decoration: a black trough under glass is the standard
    way a model cockpit dies, and these are what give the eye something to
    resolve through the transparency.
    """
    out = []
    step = (x1 - x0 - 120) / n
    for i in range(n):
        xa = x0 + 60 + i * step
        xb = xa + step * 0.78
        xm = 0.5 * (xa + xb)
        yo, yi = W_TUB(xm) - 44, 198.0
        z = SILL(xm) - 75
        out.append(_box(xa, xb, side * yi, side * yo, z - 8, z + 12,
                        r=9, axis="z"))
    return _fuse(out)


def _panel(x_face, half_w, z0, z1, rake=-12.0):
    """A raked instrument panel plate.

    Negative rake tips the top FORWARD, so the face looks up and aft at the
    crew the way a real panel does.
    """
    p = _box(-30, 30, -half_w, half_w, -0.5 * (z1 - z0), 0.5 * (z1 - z0),
             r=24, axis="x")
    return Location((x_face, 0, 0.5 * (z0 + z1)), (0, rake, 0)) * p


def _panel_faces(x_face, z_mid, items, rake=-12.0, depth=32.0):
    """Bezels and displays laid on the AFT face of a raked panel.

    ``items`` are (y, z, kind, size) in the panel's own plane, mirrored about
    y=0 so the fused leaf stays bilaterally symmetric.
    """
    loc = Location((x_face, 0, z_mid), (0, rake, 0))
    out = []
    for y, z, kind, s in items:
        if kind == "dial":
            out.append(loc * _disc((depth, y, z), s, 26, normal=(1, 0, 0)))
        else:
            out.append(loc * _box(depth - 13, depth + 13, y - s, y + s,
                                  z - s * 0.72, z + s * 0.72, r=6, axis="x"))
    return _fuse(out)


# ---------------------------------------------------------------------------
# Martin-Baker GRU-7A
# ---------------------------------------------------------------------------


def _seat(x_base, tag):
    """One GRU-7A, built in a reclined local frame and dropped into the well.

    Local origin is the seat base on the cockpit floor: +x aft, +y port, +z up
    the seat back.  The whole seat carries the recline, so pan, back, headbox
    and rails stay square to each other the way the real structure is.
    """
    loc = Location((x_base, 0, SEAT_BASE_Z), (0, SEAT_RECLINE, 0))
    out = []

    def add(shape, label, colour, alpha=1.0):
        out.append(P.style(loc * shape, f"{label}:{tag}", colour, alpha))

    def pair(make, label, colour):
        for s in (1, -1):
            add(make(s), f"{label}:{'port' if s > 0 else 'stbd'}", colour)

    # --- bucket, survival kit, pan ---------------------------------------
    add(_box(-268, 34, -206, 206, 44, 250, r=30), "seat_kit", P.SEAT_BODY)
    add(_box(-262, 30, -212, 212, 250, 292, r=26), "seat_pan", P.SEAT_BODY)
    add(_box(-250, 22, -186, 186, 292, 332, r=30), "seat_pan_cushion",
        P.SEAT_CUSHION)

    # --- back, bolsters, cushion -----------------------------------------
    add(_box(28, 128, -216, 216, 330, 1002, r=34, axis="x"), "seat_back",
        P.SEAT_BODY)
    add(_box(-14, 30, -182, 182, 352, 986, r=30, axis="x"),
        "seat_back_cushion", P.SEAT_CUSHION)
    pair(lambda s: _box(-26, 96, s * 182, s * 218, 330, 706, r=14, axis="x"),
         "seat_bolster", P.SEAT_BODY)

    # --- headbox and headrest --------------------------------------------
    add(_box(16, 178, -196, 196, 1000, 1252, r=40, axis="x"), "seat_headbox",
        P.SEAT_BODY)
    add(_box(-8, 20, -150, 150, 1032, 1186, r=30, axis="x"), "seat_headrest",
        P.SEAT_CUSHION)
    add(_box(150, 182, -120, 120, 1188, 1256, r=16, axis="x"), "seat_drogue",
        P.STEEL_DARK)

    # --- rails and catapult ----------------------------------------------
    pair(lambda s: _box(148, 208, s * 146, s * 196, 0, 1216, r=12),
         "seat_rail", P.ALUM_DARK)
    pair(lambda s: _box(120, 152, s * 150, s * 192, 300, 1010, r=8),
         "seat_roller_beam", P.STEEL_DARK)
    add(_rod((186, 0, 0), (186, 0, 1150), 62), "seat_catapult", P.ALUM_DARK)

    # --- face curtain handle, top of the headbox -------------------------
    yel, blk = _striped((22, -108, 1292), (22, 108, 1292), 15, 7)
    add(yel, "face_curtain_stripe", P.HANDLE_YELLOW)
    add(blk, "face_curtain_handle", P.HANDLE_BLACK)
    pair(lambda s: _rod((22, s * 104, 1250), (40, s * 104, 1292), 13),
         "face_curtain_arm", P.HANDLE_BLACK)

    # --- lower ejection handle, between the knees ------------------------
    yel, blk = _striped((-272, -74, 316), (-272, 74, 316), 14, 5)
    add(yel, "ejection_handle_stripe", P.HANDLE_YELLOW)
    add(blk, "ejection_handle", P.HANDLE_BLACK)
    pair(lambda s: _rod((-272, s * 70, 316), (-244, s * 70, 268), 12),
         "ejection_handle_arm", P.HANDLE_BLACK)

    # --- harness ----------------------------------------------------------
    pair(lambda s: _box(-18, 4, s * 74, s * 152, 546, 962, r=8, axis="x"),
         "harness_shoulder", P.HARNESS)
    pair(lambda s: _box(-196, -58, s * 118, s * 178, 320, 344, r=8),
         "harness_lap", P.HARNESS)
    pair(lambda s: _rod((-238, s * 150, 300), (-238, s * 150, 226), 16),
         "leg_restraint", P.HARNESS)
    add(_box(-92, -34, -66, 66, 316, 356, r=12), "harness_buckle", P.BRASS)
    pair(lambda s: _rod((-30, s * 206, 400), (-30, s * 206, 236), 22),
         "seat_hose", P.WIRE_LOOM)
    return out


# ---------------------------------------------------------------------------
# HUD, mirrors, canopy mechanism
# ---------------------------------------------------------------------------


def _hud():
    """AN/AVG-12 head-up display, sitting on the pilot's coaming.

    Everything here is squeezed between the coaming cap and the windscreen
    inner surface; the combiner top clears the glass by about 45 mm.
    """
    out = []
    x0, x1 = 4040.0, 4192.0
    out.append(P.style(_box(x0, x1, -150, 150, COAM_CAP_P - 4, 1096, r=24),
                       "hud_housing", P.COCKPIT_BLACK))
    out.append(P.style(_box(x0 + 16, x1 - 8, -128, 128, 1096, 1112, r=14),
                       "hud_hood", P.STEEL_DARK))
    comb = _box(-8, 8, -124, 124, -60, 60, r=14, axis="x")
    out.append(P.style(Location((4204, 0, 1146), (0, -24, 0)) * comb,
                       "hud_combiner", P.HUD_GLASS, P.HUD_ALPHA))
    for s in (1, -1):
        out.append(P.style(_box(4186, 4222, s * 118, s * 134, 1100, 1200,
                                r=6, axis="y"),
                           f"hud_post:{'port' if s > 0 else 'stbd'}",
                           P.STEEL_DARK))
    return out


def _mirror(x_mid, y, z, tag, yaw=0.0):
    """Rear-view mirror: housing plus its reflective face."""
    body = _box(-34, 10, -52, 52, -38, 38, r=14, axis="x")
    glass = _box(-40, -32, -44, 44, -30, 30, r=10, axis="x")
    loc = Location((x_mid, y, z), (0, -22, yaw))
    return [P.style(loc * body, f"mirror_housing:{tag}", P.CANOPY_FRAME),
            P.style(loc * glass, f"mirror_glass:{tag}", MIRROR_FACE)]


def _canopy_mechanism():
    """Aft hinge arms, the single lift actuator and the jettison hardware.

    The F-14's canopy hinges up at the rear on one large actuator; parked with
    the canopy CLOSED it is fully retracted into the turtledeck bay behind the
    RIO, where it reads through the aft glass.
    """
    out = []
    a = Vector(X_OPEN_AFT - 40, 0, 780)
    b = Vector(X_OPEN_AFT - 210, 0, 1220)
    d = (b - a).normalized()
    out.append(P.style(_rod(tuple(a), tuple(a + d * 300), 56),
                       "canopy_actuator_cylinder", P.ALUM_DARK))
    out.append(P.style(_rod(tuple(a + d * 290), tuple(b - d * 40), 27),
                       "canopy_actuator_rod", P.OLEO_CHROME))
    out.append(P.style(Pos(*(b - d * 22)) * _box(-38, 38, -32, 32, -32, 32,
                                                 r=10, axis="x"),
                       "canopy_actuator_clevis", P.STEEL_DARK))
    out.append(P.style(_box(X_OPEN_AFT - 96, X_OPEN_AFT - 10, -76, 76,
                            706, 800, r=18), "canopy_actuator_mount",
                       P.ALUM_DARK))
    for s in (1, -1):
        tag = "port" if s > 0 else "stbd"
        out.append(P.style(_rod((X_OPEN_AFT - 34, s * 230, 990),
                                (X_OPEN_AFT - 150, s * 230, 1170), 30),
                           f"canopy_hinge_arm:{tag}", P.ALUM_DARK))
        out.append(P.style(_box(X_OPEN_AFT - 66, X_OPEN_AFT - 12, s * 202,
                                s * 258, 940, 1024, r=14),
                           f"canopy_hinge_block:{tag}", P.STEEL_DARK))
        out.append(P.style(_rod((X_OPEN_AFT - 246, s * 258, 792),
                                (X_OPEN_AFT - 66, s * 258, 792), 62),
                           f"jettison_bottle:{tag}", P.STEEL_DARK))
        out.append(P.style(_rod((X_OPEN_AFT - 246, s * 258, 792),
                                (X_OPEN_AFT - 246, s * 120, 754), 13),
                           f"jettison_line:{tag}", P.HYDRAULIC))
        hooks = []
        for xh in (4620.0, 5320.0, 6060.0, 6740.0):
            w = W_RAIL(xh) - 22
            hooks.append(_box(xh - 44, xh + 44, s * (w - 44), s * w,
                              SILL(xh) + 26, SILL(xh) + 80, r=10))
        out.append(P.style(_fuse(hooks), f"canopy_latch:{tag}", P.ALUM_DARK))
    return out


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _transparencies():
    out = [P.style(_canopy_glass(), "canopy_glass", P.CANOPY_GLASS,
                   P.CANOPY_ALPHA)]
    for shape in mirror_pair(_ws_quarter, "windscreen_quarter"):
        shape.color = P.srgb(P.CANOPY_GLASS, P.CANOPY_ALPHA)
        out.append(shape)
    out.append(P.style(_ws_flat(), "windscreen_front_panel", P.CANOPY_GLASS,
                       P.CANOPY_ALPHA + 0.08))
    return out


def _frames():
    out = [P.style(_ws_bow_solid(), "windscreen_bow", P.CANOPY_FRAME),
           P.style(_bow(*X_WS_ARCH, 70.0, ny=18), "windscreen_arch",
                   P.CANOPY_FRAME),
           P.style(_bow(*X_CAN_BOW_F, BOW_T), "canopy_bow_fwd",
                   P.CANOPY_FRAME),
           P.style(_bow(*X_CAN_BOW_A, BOW_T + 10), "canopy_bow_aft",
                   P.CANOPY_FRAME)]
    for shape in mirror_pair(_ws_post, "windscreen_post"):
        shape.color = P.srgb(P.CANOPY_FRAME)
        out.append(shape)
    for shape in mirror_pair(_rail, "canopy_rail"):
        shape.color = P.srgb(P.CANOPY_FRAME)
        out.append(shape)
    for shape in mirror_pair(_seal, "canopy_seal"):
        shape.color = P.srgb(P.RUBBER)
        out.append(shape)
    return out


def _interior():
    out = [P.style(_tub_shell(), "cockpit_tub", P.COCKPIT_BLACK),
           P.style(_bulkhead(X_BULK_MID, X_BULK_MID + 52, 1010),
                   "bulkhead_mid", P.COCKPIT_BLACK),
           P.style(_bulkhead(X_BULK_AFT, X_BULK_AFT + 46, 980),
                   "bulkhead_aft", P.COCKPIT_BLACK),
           P.style(_box(X_BULK_AFT + 40, X_OPEN_AFT - 12, -300, 300,
                        700, 742, r=40), "aft_deck", P.PANEL_DARK)]

    # --- pilot station ----------------------------------------------------
    out.append(P.style(_plug(X_COAM_P[0], X_COAM_P[1], W_RAIL,
                             lambda x: SILL(x) + 26, COAM_CAP_P, COAM_GAP),
                       "glareshield_pilot", P.COCKPIT_BLACK))
    hw_p = W_TUB(X_IP_PILOT) - 46
    out.append(P.style(_panel(X_IP_PILOT, hw_p, 640, 1006), "ip_pilot",
                       P.COCKPIT_BLACK))
    out.append(P.style(_panel_faces(X_IP_PILOT, 823, [
        (0, 74, "mfd", 92), (-198, 78, "dial", 60), (198, 78, "dial", 60),
        (-136, -86, "dial", 50), (136, -86, "dial", 50),
        (-252, -74, "dial", 42), (252, -74, "dial", 42),
        (0, -110, "mfd", 70)]), "ip_pilot_instruments", P.STEEL_DARK))
    out.append(P.style(_panel_faces(X_IP_PILOT, 823, [
        (0, 74, "mfd", 78), (0, -110, "mfd", 58)], depth=44),
        "ip_pilot_displays", SCOPE_FACE))
    out.append(P.style(_box(4218, 4306, -hw_p - 16, hw_p + 16, 1000, 1052,
                            r=34), "ip_hood_pilot", P.COCKPIT_BLACK))

    # --- RIO station ------------------------------------------------------
    out.append(P.style(_plug(X_COAM_R[0], X_COAM_R[1], W_RAIL,
                             lambda x: SILL(x) + 26, COAM_CAP_R, COAM_GAP,
                             nx=6), "glareshield_rio", P.COCKPIT_BLACK))
    hw_r = W_TUB(X_IP_RIO) - 46
    out.append(P.style(_panel(X_IP_RIO, hw_r, 630, 1030), "ip_rio",
                       P.COCKPIT_BLACK))
    out.append(P.style(_panel_faces(X_IP_RIO, 830, [
        (0, -46, "dial", 124), (-236, 130, "dial", 72),
        (236, 130, "dial", 72), (-244, -60, "mfd", 56),
        (244, -60, "mfd", 56)]), "ip_rio_instruments", P.STEEL_DARK))
    out.append(P.style(_panel_faces(X_IP_RIO, 830, [
        (0, -46, "dial", 108), (-236, 130, "dial", 60),
        (236, 130, "dial", 60)], depth=44), "ip_rio_displays", SCOPE_FACE))
    out.append(P.style(_box(5602, 5690, -hw_r - 16, hw_r + 16, 1024, 1072,
                            r=34), "ip_hood_rio", P.COCKPIT_BLACK))

    # --- consoles, pedals -------------------------------------------------
    for s in (1, -1):
        tag = "port" if s > 0 else "stbd"
        out.append(P.style(_console(s, X_IP_PILOT + 66, X_BULK_MID - 6),
                           f"console_pilot:{tag}", P.COCKPIT_BLACK))
        out.append(P.style(_console_panels(s, X_IP_PILOT + 66, X_BULK_MID - 6),
                           f"console_pilot_panels:{tag}", PANEL_GREY))
        out.append(P.style(_console(s, X_IP_RIO + 96, X_BULK_AFT - 8),
                           f"console_rio:{tag}", P.COCKPIT_BLACK))
        out.append(P.style(_console_panels(s, X_IP_RIO + 96, X_BULK_AFT - 8,
                                           n=6), f"console_rio_panels:{tag}",
                           PANEL_GREY))
        out.append(P.style(_box(4296, 4412, s * 76, s * 174, 200, 336,
                                r=16, axis="y"), f"rudder_pedal:{tag}",
                           P.ALUM_DARK))
        out.append(P.style(_rod((4408, s * 126, 232), (4560, s * 126, 206), 17),
                           f"pedal_link:{tag}", P.STEEL_DARK))

    # --- stick, throttles, RIO hand controller ----------------------------
    out.append(P.style(_rod((4664, 0, 290), (4640, 0, 600), 26),
                       "control_stick_column", P.COCKPIT_BLACK))
    out.append(P.style(Location((4630, 0, 668), (0, -8, 0))
                       * _box(-42, 42, -36, 36, -70, 70, r=26),
                       "control_stick_grip", P.HANDLE_BLACK))
    out.append(P.style(_box(4356, 4606, 190, 300, 700, 762, r=18),
                       "throttle_quadrant:port", P.COCKPIT_BLACK))
    thr = []
    for i, dy in enumerate((214, 268)):
        thr.append(_rod((4430 + 16 * i, dy, 752), (4588, dy, 818), 18))
        thr.append(Pos(4588, dy, 824) * Solid.make_sphere(29))
    out.append(P.style(_fuse(thr), "throttle_levers:port", P.HANDLE_BLACK))
    out.append(P.style(_box(5820, 5990, -300, -190, 700, 762, r=18),
                       "rio_hand_controller:stbd", P.COCKPIT_BLACK))
    out.append(P.style(_rod((5926, -244, 756), (5910, -244, 852), 22),
                       "rio_controller_grip:stbd", P.HANDLE_BLACK))
    return out


def build():
    """Return ONE labelled group Compound, already in world position."""
    from f14_parts.airframe import stance

    kids = []
    kids += _transparencies()
    kids += _frames()
    kids += _interior()
    kids += _seat(X_SEAT_PILOT, "pilot")
    kids += _seat(X_SEAT_RIO, "rio")
    kids += _hud()
    kids += _canopy_mechanism()

    x_bow = 0.5 * (X_CAN_BOW_F[0] + X_CAN_BOW_F[1])
    z_bow = SURF(x_bow, 0.0) - BOW_T - 84
    kids += _mirror(x_bow, 0.0, z_bow, "pilot_centre")
    for s in (1, -1):
        tag = "port" if s > 0 else "stbd"
        y = s * 206.0
        kids += _mirror(x_bow, y, SURF(x_bow, abs(y)) - BOW_T - 74,
                        f"pilot_{tag}", yaw=s * 16.0)
        xr = 5700.0
        yr = s * (W_RAIL(xr) - 66)
        kids += _mirror(xr, yr, SURF(xr, abs(yr)) - 70, f"rio_{tag}",
                        yaw=s * 26.0)
    return stance(group("cockpit", kids))


if __name__ == "__main__":
    import time

    t0 = time.time()
    for x in (3880, 3950, 4290, 4800, 5400, 5960, 6600, 7180):
        print(f"x={x/G.M:5.2f}  hw={HW(x):6.1f}  rail={W_RAIL(x):6.1f}  "
              f"cut={W_CUT(x):6.1f}  tub={W_TUB(x):6.1f}  "
              f"sill={SILL(x):6.1f}  floor={FLOOR(x):6.1f}  "
              f"crown={SURF(x, 0.0):7.1f}")
    c = build()
    print(f"build {time.time()-t0:.1f}s   leaves {len(c.children)}")
    bb = c.bounding_box()
    print(f"bbox x {bb.min.X:8.1f}..{bb.max.X:8.1f}  "
          f"y {bb.min.Y:8.1f}..{bb.max.Y:8.1f}  "
          f"z {bb.min.Z:8.1f}..{bb.max.Z:8.1f}")
