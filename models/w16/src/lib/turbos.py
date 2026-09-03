"""Four turbochargers (two per bank, outboard and low, axes along X).

STATIONS come from `spec.turbo(bank, pos)`: centre, axis, turbine end direction,
turbine/compressor planes, turbine-inlet flange, compressor outlet, downpipe
flange.  Nothing here re-derives them.

HANDEDNESS.  One turbo is authored in a LOCAL frame centred on the turbo axis:
  +X  toward the TURBINE end          (engine +X * turbine_dir)
  +Z  up (engine +Z)
  out the bank's OUTBOARD direction   (engine +Y for bank 1)
A point is written `_p(x, out, up)`; the module-level sign `q` maps `out` onto
local +Y, so the mirrored bank is a genuinely re-authored part (a sign, not a
reflection) and every label, thread and scroll wrap keeps its hand.

Only TWO prototypes are built (q = +1 and q = -1).  Each is placed twice: once
as itself (turbine_dir = +1, i.e. the REAR turbo of its bank) and once rotated
180 deg about Z (turbine_dir = -1, the FRONT turbo of the OTHER bank, because
that rotation flips both x and y).  So four stations cost two builds.

THE VOLUTES are lofts through circles/ellipses whose centres spiral about the
axis at a constant inner radius (the wheel tip) while the section grows toward
the inlet — which is what a real scroll does, and gives a smooth surface with
no faceting.  The casting is built as OUTER (fused fat bodies) minus CAVITY
(the same bodies at gas-path size, fused into ONE tool first).

MOVING PARTS.  `turbine_wheel:*` and `compressor_wheel:*` are separate solids
centred on the turbo axis, clear of their housings by >= 3 mm all round, so the
animation can spin them about `axis` through `centre`.

The museum cut (x > SECTION_X, y > 12, z > -95) reaches the bank-1 FRONT
turbo (centre x 130): even sectioned, its centre/compressor half stood right in
front of the opened crankcase and hid the piston-rod-crank profile the display
exists to show.  So, as a cutaway exhibit would, that turbo is LIFTED OFF when
`sectioned`: its collector flange stays on the manifold, its downpipe goes with
it (exhaust.py), and its charge pipe is cut at the section plane (induction.py).
"""

from __future__ import annotations

import math
import sys

from cadgen import build123d as bd, srgb

from lib import fasteners as F, geo, palette as P, spec as S
from lib.castings import edges_at, fuse_all, machined_skin, safe_fillet

# Mid-way zone of the turbine housing's heat gradient: hot-side cast iron runs
# HEAT_TINT (brown) in the cool zone, through this bronze, to HEAT_TINT_BLUE
# where the gas enters at the inlet flange.  Local to this module — the rest of
# the engine has no bronze in it.
BRONZE = srgb("#8a6a4a")

# ---------------------------------------------------------------------------
# Local-frame sizes (mm).  x is along the turbo axis, +X toward the turbine.
# ---------------------------------------------------------------------------

# Centre (bearing) housing
CH_BARREL_D = 56.0
CH_FIN_D = 68.0
CH_FLANGE_D = 74.0
CH_T_FACE = 43.0                          # turbine-side V-band joint plane
CH_C_FACE = -43.0                         # compressor-side V-band joint plane

# V-band clamp
VB_ID = 70.0
VB_OD = 86.0
VB_W = 17.0

# Turbine
T_BORE_R = 32.0                           # wheel chamber bore radius (3 mm tip clearance)
T_SCROLL_X = 64.0                         # scroll plane
T_PSI0, T_PSI1 = 60.0, 370.0              # wrap: big end (inlet) -> tongue
T_R0, T_R1 = 18.0, 7.0                    # section radius, inlet -> tongue
T_WALL = 6.0
T_AX, T_RAD = 0.78, 1.12                  # section ellipse: axial / radial factors
T_CHAMBER_X = (44.0, 86.0)
T_INLET_BORE_R = 20.0
T_FLANGE = (100.0, 50.0, 14.0)            # x-length, y-width, thickness
T_STUD_D = 8.0

# Downpipe (outlet) duct, down to the flange at local z = -90
T_DUCT_Z = -90.0
T_DP_OD = 82.0

# Compressor
C_BORE_R = 34.0
C_SCROLL_X = -62.0
C_PSI0, C_PSI1 = -20.0, 300.0             # wrap: tongue -> big end (discharge)
C_R0, C_R1 = 7.0, 15.0
C_WALL = 5.0
C_AX = 0.80
C_RIN = 31.5
C_INLET_X = -98.0                         # bell mouth
C_INLET_BORE_R = 29.5           # 2.1 mm clear of the inducer tip
C_OUT_D = 55.0                            # outlet stub OD

# Wastegate
WG_CAN_D = 60.0
WG_CAN_T = 26.0
# The can rides ABOVE the centre housing, outboard: the only pocket with
# 30 mm of clear radius that also stays inside |y| <= 470.
WG_CAN = (-6.0, 34.0, 62.0)               # can centre (x, out, up)
WG_SHAFT = (48.0, 24.0)                   # (out, up) of the wastegate shaft


# ---------------------------------------------------------------------------
# Local-frame helpers.  `q` = +1 when the prototype's outboard is local +Y.
# ---------------------------------------------------------------------------

def _p(x, out, up, q):
    """Local point from (axis station, outboard offset, height)."""
    return (x, q * out, up)


def _rev_x(pts, arc: float = 360.0, spline=None, tangents=None):
    """Revolve a closed (x, radius) profile about the local X axis.

    `spline=(lo, hi)` joins `pts[lo:hi+1]` with ONE spline instead of straight
    segments.  A run of straight segments revolves into a stack of cone faces
    that renders as facets, and collinear runs additionally make the solid fail
    OCC's self-intersection check, so every contour that should read as smooth
    (wheel hubs, the compressor inlet bell) goes through the spline.
    """
    n = len(pts)
    lo, hi = spline if spline else (-1, -1)
    edges = []
    k = 0
    while k < n:
        if k == lo:
            edges += bd.Spline(*pts[lo:hi + 1], tangents=tangents).edges()
            k = hi
            continue
        edges += bd.Line(pts[k], pts[(k + 1) % n]).edges()
        k += 1
    return bd.revolve(bd.Plane.XZ * bd.make_face(edges), bd.Axis.X, arc)


def _prism_x(pts, x0: float, x1: float, q: float):
    """Extrude a closed (out, up) polygon along X between x0 and x1."""
    poly = [(q * o, z) for o, z in pts]
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
               for i in range(n))
    if area < 0:
        poly = poly[::-1]
    face = bd.make_face(bd.Polyline(*poly, close=True).edges())
    return bd.extrude(geo.yz_plane(x0) * face, amount=x1 - x0)


def _strap(p0, p1, width: float):
    """Rectangular (out, up) footprint of a flat strap between two points."""
    dy, dz = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dy, dz)
    ny, nz = -dz / L * width / 2.0, dy / L * width / 2.0
    return [(p0[0] + ny, p0[1] + nz), (p1[0] + ny, p1[1] + nz),
            (p1[0] - ny, p1[1] - nz), (p0[0] - ny, p0[1] - nz)]


def _fuse(parts):
    """Accumulate a fuse operand by operand.

    `castings.fuse_all` tries ONE multi-operand fuse first, which is the right
    default — but on these lofted housings OCC returns an unsound result for
    ONE of the two hands (pure mirrors, same operand count), and the failed
    multi-fuse leaves its operands modified, so fuse_all's own pairwise retry
    then drops good bodies and quietly ships a housing with no outlet duct.
    Accumulating from the start is stable for both hands and, at eight
    operands, costs less than the failed attempt did.
    """
    items = [p for p in parts if p is not None]
    body = items[0]
    for piece in items[1:]:
        body = body + piece
    return body


def _cyl(p0, p1, d):
    return geo.cyl_along(p0, p1, d)


def _spiral_frame(psi_deg: float, R: float, x_c: float, q: float, reverse: bool):
    """Section origin and normal for a scroll station.

    The section centre sits at radius R and angle psi about the axis (psi = 0 is
    straight up, increasing psi moves INBOARD); the section plane is normal to
    the wrap tangent and contains the axis direction.
    """
    psi = math.radians(psi_deg)
    out, up = -R * math.sin(psi), R * math.cos(psi)
    t_out, t_up = -math.cos(psi), -math.sin(psi)
    if reverse:
        t_out, t_up = -t_out, -t_up
    return _p(x_c, out, up, q), (0.0, q * t_out, t_up)


def _scroll(x_c, psi0, psi1, r_in, r0, r1, q, n=15, wall=0.0, ax=1.0, rad=1.0):
    """Loft a volute: sections spiral about the axis with a constant inner
    radius `r_in` while the section radius grows from r0 to r1."""
    secs = []
    reverse = psi1 < psi0
    for i in range(n):
        t = i / (n - 1)
        psi = psi0 + (psi1 - psi0) * t
        r = r0 + (r1 - r0) * t
        origin, normal = _spiral_frame(psi, r_in + r, x_c, q, reverse)
        plane = geo.plane(origin, normal, (1.0, 0.0, 0.0))
        secs.append(plane * bd.Ellipse(ax * (r + wall), rad * (r + wall)))
    return bd.loft(secs), secs[0], secs[-1]


def _blade(hub, shroud, twists, thicks, q, twist_sign=-1.0, split=None):
    """One blade as a loft of thin sections along the meridional passage.

    The blade is described by its HUB and SHROUD contours in the meridional
    (x, radius) plane — station i spans from `hub[i]` to `shroud[i]` — and by a
    per-station backsweep `twists[i]` about the axis.  The section plane is
    normal to the flow (perpendicular to the span), which is what makes the
    loft behave: describing the blade by a mid-span path instead lets a section
    plane end up nearly PARALLEL to the loft direction at the leading edge,
    where OCC quietly returns an inverted, self-intersecting solid.

    `twist_sign` flips the sweep for a compressor (outflow) against a turbine
    (inflow); `q` carries it onto the mirrored bank.  `split` lofts the blade as
    two runs meeting on that station and fuses them: a single smooth loft
    through the compressor's whole exducer overshoots into itself, and the one
    crease this leaves sits where the blade is already nearly straight.
    """
    secs = []
    for (hx, hr), (sx, sr), tw, thick in zip(hub, shroud, twists, thicks):
        mx, mr = (hx + sx) / 2.0, (hr + sr) / 2.0
        dx, dr = sx - hx, sr - hr
        span = math.hypot(dx, dr)
        nx, nr = dr / span, -dx / span          # flow normal = span rotated -90
        a = math.radians(q * twist_sign * tw)
        ca, sa = math.cos(a), math.sin(a)
        origin = (mx, mr * ca, mr * sa)
        normal = (nx, nr * ca, nr * sa)
        e_t = (0.0, -sa, ca)                    # tangential unit vector
        span_dir = (normal[1] * e_t[2] - normal[2] * e_t[1],
                    normal[2] * e_t[0] - normal[0] * e_t[2],
                    normal[0] * e_t[1] - normal[1] * e_t[0])
        plane = geo.plane(origin, normal, span_dir)
        secs.append(plane * bd.RectangleRounded(span, thick, thick * 0.45))
    if split is None:
        return bd.loft(secs)
    return fuse_all([bd.loft(secs[:split + 1]), bd.loft(secs[split:])])


def _wheel(hub_pts, blade, count, start_deg=0.0, spline=None, tangents=None):
    """Hub of revolution + `count` copies of one blade, evenly clocked."""
    parts = [_rev_x(hub_pts, spline=spline, tangents=tangents)]
    for i in range(count):
        parts.append(blade.moved(bd.Location((0, 0, 0), (start_deg + 360.0 * i / count, 0, 0))))
    return _fuse(parts)


# ---------------------------------------------------------------------------
# Turbine wheel / compressor wheel
# ---------------------------------------------------------------------------

T_HUB = [(40.0, 0.0), (40.0, 11.0), (54.0, 11.0), (54.0, 29.0),
         (64.0, 29.0), (70.0, 24.5), (76.0, 18.5), (81.0, 12.5), (84.6, 5.5),
         (85.0, 0.0)]
T_HUB_SPLINE = (4, 8)
T_HUB_TAN = ((1.0, 0.0), (0.55, -1.0))

# Turbine blade: radial inflow at the tip -> axial exducer.
T_BLADE_HUB = [(62.0, 27.5), (65.5, 21.5), (72.0, 16.0), (79.0, 11.0)]
T_BLADE_SHROUD = [(69.0, 27.5), (75.0, 26.5), (79.5, 24.5), (82.5, 21.5)]
T_BLADE_TWIST = [0.0, 12.0, 24.0, 36.0]
T_BLADE_THICK = [2.6, 2.3, 1.8, 1.2]

C_HUB = [(-88.0, 0.0), (-87.4, 4.0), (-84.0, 9.0), (-79.0, 12.5), (-73.0, 17.0),
         (-68.0, 23.0), (-64.5, 28.5), (-62.5, 30.0), (-61.0, 30.0),
         (-61.0, 11.0), (-52.0, 11.0), (-52.0, 0.0)]
C_HUB_SPLINE = (1, 7)
C_HUB_TAN = ((1.0, 0.55), (0.0, 1.0))

# Compressor blade: axial inducer -> radial exducer.
# Stations are spaced so BOTH contours advance at every step: letting one end
# stall while the other sweeps rotates the section ~70 deg over a few mm and
# OCC lofts that into a self-intersecting solid.
C_BLADE_HUB = [(-84.0, 8.0), (-80.0, 10.0), (-75.0, 13.5), (-70.0, 19.0),
               (-65.5, 24.8), (-63.0, 28.5)]
C_BLADE_SHROUD = [(-84.0, 27.0), (-81.0, 27.4), (-78.0, 28.0), (-75.5, 28.4),
                  (-73.5, 28.5), (-72.0, 28.5)]
C_BLADE_TWIST = [0.0, 5.0, 13.0, 25.0, 40.0, 52.0]
C_BLADE_THICK = [1.4, 1.5, 1.7, 1.9, 2.1, 2.3]


def turbine_wheel(q: float):
    """11 backswept blades on a full-diameter backdisc; tip circle 58 mm in the
    64 mm chamber bore, so the wheel turns 3 mm clear of the housing."""
    blade = _blade(T_BLADE_HUB, T_BLADE_SHROUD, T_BLADE_TWIST, T_BLADE_THICK,
                   q, twist_sign=-1.0)
    return _wheel(T_HUB, blade, 11, spline=T_HUB_SPLINE, tangents=T_HUB_TAN)


def compressor_wheel(q: float):
    """6 full blades + 6 splitters (12), splitters starting mid-passage; tip
    circle 60 mm in the 68 mm chamber bore."""
    full = _blade(C_BLADE_HUB, C_BLADE_SHROUD, C_BLADE_TWIST, C_BLADE_THICK,
                  q, twist_sign=+1.0, split=4)
    split = _blade(C_BLADE_HUB[2:], C_BLADE_SHROUD[2:], C_BLADE_TWIST[2:],
                   C_BLADE_THICK[2:], q, twist_sign=+1.0, split=2)
    parts = [_rev_x(C_HUB, spline=C_HUB_SPLINE, tangents=C_HUB_TAN)]
    for i in range(6):
        a = 60.0 * i
        parts.append(full.moved(bd.Location((0, 0, 0), (a, 0, 0))))
        parts.append(split.moved(bd.Location((0, 0, 0), (a + 30.0, 0, 0))))
    return _fuse(parts)


# ---------------------------------------------------------------------------
# Turbine housing
# ---------------------------------------------------------------------------

def _turbine_housing(q: float):
    """Returns (housing, heat_band_blue, heat_band_bronze, parting_bead,
    flange_face, stud_points).

    The housing is ONE casting, but a hot turbine housing is not one colour:
    the gas is hottest where it enters, so the tint runs blue at the inlet,
    through bronze on the duct, to brown over the scroll and the outlet.  The
    renderer has one material per solid, so the gradient is cut OUT of the
    body as disjoint zones (`body & tool`, then `body - tool`) that share
    faces with it and never overlap it.
    """
    x0, x1 = T_CHAMBER_X

    outer = []
    cavity = []

    # wheel chamber + the collar the V-band clamp grips
    outer.append(_cyl(_p(x0 - 2, 0, 0, q), _p(x1 + 2, 0, 0, q), 2 * (T_BORE_R + 8)))
    outer.append(_rev_x([(CH_T_FACE, 0.0), (CH_T_FACE, CH_FLANGE_D / 2 - 2.0),
                         (CH_T_FACE + 2.0, CH_FLANGE_D / 2), (x0 + 4.0, CH_FLANGE_D / 2),
                         (x0 + 6.0, T_BORE_R + 7.0), (x0 + 6.0, 0.0)]))
    cavity.append(_cyl(_p(x0, 0, 0, q), _p(x1, 0, 0, q), 2 * T_BORE_R))
    # shaft clearance through the back wall
    cavity.append(_cyl(_p(CH_T_FACE - 4, 0, 0, q), _p(x0 + 1, 0, 0, q), 30.0))

    # volute
    scroll_in, in_first, _ = _scroll(T_SCROLL_X, T_PSI0, T_PSI1, T_BORE_R - 1.0,
                                     T_R0, T_R1, q, wall=0.0, ax=T_AX, rad=T_RAD)
    scroll_out, out_first, _ = _scroll(T_SCROLL_X, T_PSI0, T_PSI1, T_BORE_R - 1.0,
                                       T_R0, T_R1, q, wall=T_WALL, ax=T_AX, rad=T_RAD)
    outer.append(scroll_out)
    cavity.append(scroll_in)

    # inlet duct: scroll big end -> flange face, plus the rectangular flange
    fx, fout, fz = T_SCROLL_X - 4.0, -30.0, 95.0
    flange_face = geo.plane(_p(fx, fout, fz, q), (0, 0, 1), (1, 0, 0))
    mid = geo.plane(_p(fx + 2, fout - 6, fz - 34, q), (0.0, q * -0.25, 1.0), (1, 0, 0))
    outer.append(bd.loft([out_first, mid * bd.Circle(T_INLET_BORE_R + 7.0),
                          flange_face * bd.Circle(T_INLET_BORE_R + 6.0)]))
    cavity.append(bd.loft([in_first, mid * bd.Circle(T_INLET_BORE_R + 1.0),
                           flange_face * bd.Circle(T_INLET_BORE_R)]))
    fw, fd, ft = T_FLANGE
    slab = bd.extrude(geo.plane(_p(fx, fout, fz - ft, q), (0, 0, 1), (1, 0, 0))
                      * bd.RectangleRounded(fw, fd, 12.0), amount=ft)
    outer.append(slab)
    cavity.append(_cyl(_p(fx, fout, fz - ft - 6, q), _p(fx, fout, fz + 4, q),
                       2 * T_INLET_BORE_R + 1.2))

    # down-turned outlet: chamber -> V-band flange under the housing
    duct_sec = [(-8.0, 66.0, 23.0, 38.5), (-46.0, 63.0, 26.0, 37.0),
                (T_DUCT_Z + 2.0, T_SCROLL_X - 4.0, 32.5, 32.5)]
    o_secs, i_secs = [], []
    for z, xc, hx, hy in duct_sec:
        pl = geo.plane(_p(xc, 0, z, q), (0, 0, 1), (1, 0, 0))
        o_secs.append(pl * bd.Ellipse(hx, hy))
        i_secs.append(pl * bd.Ellipse(hx - 7.0, hy - 7.0))
    outer.append(bd.loft(o_secs))
    cavity.append(bd.loft(i_secs))
    cavity.append(_cyl(_p(T_SCROLL_X - 4.0, 0, T_DUCT_Z - 8, q),
                       _p(T_SCROLL_X - 4.0, 0, T_DUCT_Z + 20, q), 52.0))

    # wastegate: cast port boss on the outboard wall + its shaft bore
    wg_out, wg_up = WG_SHAFT
    boss_a = _p(x0 + 6.0, wg_out - 4.0, wg_up + 8.0, q)
    boss_b = _p(x0 + 22.0, wg_out - 4.0, wg_up + 8.0, q)
    outer.append(_cyl(boss_a, boss_b, 34.0))
    outer.append(_cyl(_p(CH_T_FACE - 6.0, wg_out, wg_up, q),
                      _p(x0 + 12.0, wg_out, wg_up, q), 22.0))
    cavity.append(_cyl(_p(CH_T_FACE - 10.0, wg_out, wg_up, q),
                       _p(x0 + 10.0, wg_out, wg_up, q), 11.0))

    body = _fuse(outer) - _fuse(cavity)

    # heat-tint band hugging the inlet duct just under the flange
    bz0, bz1 = fz - ft - 20.0, fz - ft - 8.0
    band = (_cyl(_p(fx, fout, bz0, q), _p(fx, fout, bz1, q), 2 * (T_INLET_BORE_R + 8.4))
            - _cyl(_p(fx, fout, bz0 - 2, q), _p(fx, fout, bz1 + 2, q),
                   2 * (T_INLET_BORE_R + 6.6)))

    # Cast parting line in the scroll's mid-plane (x = the scroll station).
    # `parting_line` fuses the bead into the part; subtracting the raw body
    # back off leaves ONLY the proud flash, which ships as its own solid and
    # is therefore disjoint from every zone cut out of the body below.  Clip
    # it under the inlet duct so the bead wraps the scroll and the outlet,
    # not the machined flange.
    #
    # `castings.parting_line` cannot make this one: its 3D `bd.offset` of the
    # slice fails on this housing for BOTH hands and at every plane and width
    # tried (OCC "BRep_API: command not done"), and so does a 2D offset of the
    # section's outer wires — the scroll and outlet walls are lofted spline
    # faces and the slice comes out as five separate solids.  A uniform SCALE
    # about the turbo axis does the same job with no offsetter: it grows the
    # slice radially by factor-1 times the local radius, ~0.4 mm out at the
    # scroll, and the part subtracted back off leaves only the proud flash.
    #
    slab = bd.Box(1.4, 400.0, 400.0).moved(bd.Location(_p(T_SCROLL_X, 0, 0, q)))
    grow = 1.008
    slice_ = body & slab
    bead = None
    if geo.sound(slice_):
        grown = slice_.scale(grow).moved(bd.Location((-T_SCROLL_X * (grow - 1.0), 0.0, 0.0)))
        bead = grown - body
        if geo.sound(bead):
            # clip under the inlet duct: the bead wraps the scroll and the
            # outlet, not the machined flange above it
            bead = bead & bd.Box(400.0, 400.0, 136.0).moved(bd.Location((0.0, 0.0, -16.0)))
        if not geo.sound(bead):
            bead = None

    # bronze mid-zone: a concentric slice of the inlet duct between the scroll
    # and the blue band.  Nothing but the duct lives inside this cylinder at
    # this height, so the zone reads as a band around the duct.
    zone = _cyl(_p(fx, fout, 44.0, q), _p(fx, fout, bz0 - 1.0, q), 80.0)
    bronze = body & zone
    if geo.sound(bronze):
        trimmed = body - zone
        if geo.sound(trimmed):
            body = trimmed
        else:
            bronze = None
    else:
        bronze = None

    # bright machined skin on the inlet flange face
    face = machined_skin(body, geo.plane(_p(fx, fout, fz, q), (0, 0, 1), (1, 0, 0)), t=0.8)
    if face is not None and geo.sound(face):
        trimmed = body - face
        if geo.sound(trimmed):
            body = trimmed
        else:
            face = None
    else:
        face = None

    # ONE bounded fillet attempt on the scroll-tongue crease: the sharp seam
    # right at the volute's tongue (small, psi1) end, where it feeds the
    # down-turned outlet duct.  A tight proximity pick keeps this to the
    # handful of true seam edges (5-6) rather than the ~30 a looser
    # tolerance also catches (mostly unrelated long edges elsewhere on the
    # housing); a single try at r=3, no ladder (min_r == r) -- if OCC can't
    # take a 3 mm blend there the crease is left sharp and the caller says so.
    tongue_pt, _ = _spiral_frame(T_PSI1, (T_BORE_R - 1.0) + T_R1, T_SCROLL_X, q, False)
    crease = edges_at(body, near=tongue_pt, tol=6.0)
    body, tongue_r = safe_fillet(body, crease, 3.0, min_r=3.0)
    if crease and tongue_r is None:
        print(f"[turbos] scroll-tongue/duct crease fillet FAILED at r=3 (q={q}); "
              "left sharp", file=sys.stderr)
    elif not crease:
        print(f"[turbos] scroll-tongue/duct crease: no candidate edges found "
              f"(q={q}); left sharp", file=sys.stderr)

    studs = [_p(fx + sx, fout + so, fz, q) for sx in (-38.0, 38.0) for so in (-16.0, 16.0)]
    return body, band, bronze, bead, face, studs


# ---------------------------------------------------------------------------
# Centre (bearing) housing
# ---------------------------------------------------------------------------

def _centre_housing(q: float):
    parts = [_rev_x([
        (CH_C_FACE, 0.0),
        (CH_C_FACE, CH_FLANGE_D / 2 - 2.0),
        (CH_C_FACE + 2.0, CH_FLANGE_D / 2),
        (CH_C_FACE + 9.0, CH_FLANGE_D / 2),
        (CH_C_FACE + 12.0, CH_BARREL_D / 2 + 3.0),
        (-8.0, CH_BARREL_D / 2 + 6.0),
        (10.0, CH_BARREL_D / 2 + 6.0),
        (CH_T_FACE - 12.0, CH_BARREL_D / 2 + 2.0),
        (CH_T_FACE - 9.0, CH_FLANGE_D / 2),
        (CH_T_FACE - 2.0, CH_FLANGE_D / 2),
        (CH_T_FACE, CH_FLANGE_D / 2 - 2.0),
        (CH_T_FACE, 0.0),
    ])]
    # heat-shield fins
    for fx in (16.0, 24.0, 32.0):
        parts.append(_rev_x([(fx - 2.5, 0.0), (fx - 2.5, CH_FIN_D / 2 - 1.5),
                             (fx - 1.0, CH_FIN_D / 2), (fx + 1.0, CH_FIN_D / 2),
                             (fx + 2.5, CH_FIN_D / 2 - 1.5), (fx + 2.5, 0.0)]))
    # coolant hose bosses (the jacket bulge is in the barrel profile itself)
    for so in (1.0, -1.0):
        b = _p(-2.0, so * 27.0, 18.0, q)
        parts.append(_cyl(_p(-2.0, so * 10.0, 7.0, q), b, 18.0))
        parts.append(_cyl(b, _p(-2.0, so * 32.0, 24.0, q), 14.0))
    # oil feed boss (top) and drain flange (bottom)
    parts.append(_cyl(_p(20.0, 0, 12.0, q), _p(20.0, 0, 39.0, q), 26.0))
    parts.append(_cyl(_p(-6.0, 0, -12.0, q), _p(-6.0, 0, -37.0, q), 30.0))
    parts.append(bd.extrude(geo.plane(_p(-6.0, 0, -37.0, q), (0, 0, 1), (1, 0, 0))
                            * bd.RectangleRounded(44.0, 30.0, 7.0), amount=7.0))

    # the three bores all cross the shaft bore, so they are fused into one
    # tool before cutting rather than handed to the cut as overlapping tools
    body = _fuse(parts) - _fuse([
        _cyl(_p(CH_C_FACE - 4, 0, 0, q), _p(CH_T_FACE + 4, 0, 0, q), 22.0),
        _cyl(_p(20.0, 0, 41.0, q), _p(20.0, 0, 6.0, q), 12.0),
        _cyl(_p(-6.0, 0, -40.0, q), _p(-6.0, 0, -6.0, q), 18.0),
    ])
    body, _ = safe_fillet(body, [e for e in body.edges() if e.length > 40.0], 2.0, min_r=0.5)

    # As-cast foundry pad on the compressor-side barrel, top-outboard at 45 deg
    # (clear of the coolant bosses at x = -2 and the oil feed at x = 20).  The
    # pad seats INSIDE the barrel and the barrel is then subtracted from it, so
    # the flat pad meets the round casting exactly and the two stay disjoint.
    d = (0.0, q * 0.7071, 0.7071)
    seat = (-24.0, d[1] * 31.0, d[2] * 31.0)
    pad = geo.locate(F.id_pad(18.0, 11.0, 4.5), seat, d)
    pad = pad - body
    if not geo.sound(pad):
        pad = None
    return body, pad


def _vband_clamp(x_joint: float, q: float):
    """V-band clamp ring (a 340 deg band) with its T-bolt lugs."""
    ring = _rev_x([
        (x_joint - VB_W / 2, VB_ID / 2 + 1.0),
        (x_joint - VB_W / 2 + 1.5, VB_ID / 2),
        (x_joint, VB_ID / 2 + 4.5),
        (x_joint + VB_W / 2 - 1.5, VB_ID / 2),
        (x_joint + VB_W / 2, VB_ID / 2 + 1.0),
        (x_joint + VB_W / 2, VB_OD / 2 - 1.0),
        (x_joint + VB_W / 2 - 1.0, VB_OD / 2),
        (x_joint - VB_W / 2 + 1.0, VB_OD / 2),
        (x_joint - VB_W / 2, VB_OD / 2 - 1.0),
    ], arc=336.0)
    # the ring is revolved from +Z; clock the gap to the outboard-low quadrant
    ring = ring.moved(bd.Location((0, 0, 0), (q * 130.0, 0, 0)))
    lugs = [_prism_x(_lug_outline(math.radians(q * (130.0 + side * 12.0))),
                     x_joint - 5.0, x_joint + 5.0, 1.0)
            for side in (-1.0, 1.0)]
    return _fuse([ring] + lugs)


def _lug_outline(a: float):
    """Rectangular lug footprint in (local y, z) at ring angle `a`, which
    already carries the bank sign."""
    cy, cz = math.cos(a), math.sin(a)
    # radial band from the ring OD out to the T-bolt line
    r0, r1, half = VB_OD / 2 - 4.0, VB_OD / 2 + 11.0, 5.0
    ty, tz = -cz, cy
    return [(r0 * cy - half * ty, r0 * cz - half * tz),
            (r1 * cy - half * ty, r1 * cz - half * tz),
            (r1 * cy + half * ty, r1 * cz + half * tz),
            (r0 * cy + half * ty, r0 * cz + half * tz)]


# ---------------------------------------------------------------------------
# Compressor housing
# ---------------------------------------------------------------------------

def _compressor_housing(q: float):
    outer, cavity = [], []

    # backplate / chamber around the wheel
    outer.append(_rev_x([
        (CH_C_FACE, 0.0), (CH_C_FACE, CH_FLANGE_D / 2 - 2.0),
        (CH_C_FACE - 2.0, CH_FLANGE_D / 2), (-52.0, CH_FLANGE_D / 2),
        (-56.0, C_BORE_R + 10.0), (-70.0, C_BORE_R + 9.0), (-70.0, 0.0),
    ]))
    cavity.append(_rev_x([
        (CH_C_FACE + 2.0, 0.0), (CH_C_FACE + 2.0, 12.0), (-56.0, 12.0),
        (-58.0, C_BORE_R), (-80.0, C_BORE_R), (-80.0, 0.0),
    ]))

    # inlet bell: bore with a radiused lip facing outward along -X
    outer.append(_rev_x([
        (C_INLET_X, 0.0), (C_INLET_X, C_INLET_BORE_R + 1.0),
        (C_INLET_X + 1.4, C_INLET_BORE_R + 5.0), (C_INLET_X + 5.0, C_INLET_BORE_R + 7.6),
        (C_INLET_X + 12.0, C_INLET_BORE_R + 8.4), (-73.0, C_BORE_R + 10.0),
        (-73.0, 0.0),
    ], spline=(1, 5), tangents=((0.0, 1.0), (1.0, 0.35))))
    cavity.append(_rev_x([
        (C_INLET_X - 2.0, 0.0), (C_INLET_X - 2.0, C_INLET_BORE_R + 4.5),
        (C_INLET_X + 1.0, C_INLET_BORE_R + 1.4), (C_INLET_X + 4.5, C_INLET_BORE_R),
        (-76.0, C_INLET_BORE_R), (-76.0, 0.0),
    ], spline=(1, 4), tangents=((0.0, -1.0), (1.0, 0.0))))

    # volute
    scroll_in, _, in_last = _scroll(C_SCROLL_X, C_PSI0, C_PSI1, C_RIN,
                                    C_R0, C_R1, q, wall=0.0, ax=C_AX)
    scroll_out, _, out_last = _scroll(C_SCROLL_X, C_PSI0, C_PSI1, C_RIN,
                                      C_R0, C_R1, q, wall=C_WALL, ax=C_AX)
    outer.append(scroll_out)
    cavity.append(scroll_in)

    # discharge neck -> outlet stub (Ø55) at the compressor_outlet station
    ox, oout, oz = C_SCROLL_X, 10.0, 100.0
    stub_face = geo.plane(_p(ox, oout, oz, q), (0, 0, 1), (1, 0, 0))
    neck_mid = geo.plane(_p(ox, oout + 16.0, oz - 42.0, q), (0.0, q * -0.42, 1.0), (1, 0, 0))
    outer.append(bd.loft([out_last, neck_mid * bd.Circle(C_OUT_D / 2 - 1.0),
                          stub_face * bd.Circle(C_OUT_D / 2)]))
    cavity.append(bd.loft([in_last, neck_mid * bd.Circle(C_OUT_D / 2 - 5.0),
                           stub_face * bd.Circle(C_OUT_D / 2 - 3.0)]))
    cavity.append(_cyl(_p(ox, oout, oz - 30.0, q), _p(ox, oout, oz + 4.0, q),
                       C_OUT_D - 7.0))

    # actuator-bracket pad
    outer.append(_prism_x([(28.0, 4.0), (52.0, 4.0), (52.0, 32.0), (28.0, 32.0)],
                          -52.0, -44.0, q))

    return _fuse(outer) - _fuse(cavity)


def _outlet_bead(q: float):
    """Rolled hose bead near the top of the compressor outlet stub.

    The stub leans inboard as it rises, so the bead sits on the neck's own
    centre at that height, not on the outlet station's.
    """
    ox, oout, oz = C_SCROLL_X, 10.0, 100.0
    z = oz - 7.0
    lean = oout + (oz - z) / 42.0 * 16.0
    return bd.Torus(C_OUT_D / 2 + 0.5, 3.0).moved(bd.Location(_p(ox, lean, z, q)))


# ---------------------------------------------------------------------------
# Wastegate actuator
# ---------------------------------------------------------------------------

def _wastegate(q: float):
    """Diaphragm can + pushrod + clevis + arm on a shaft into the turbine
    housing, and the bracket that ties the can back to the compressor pad."""
    cx, cout, cz = WG_CAN
    half = WG_CAN_T / 2.0
    can = _rev_x([
        (cx - half, 0.0), (cx - half, WG_CAN_D / 2 - 4.0),
        (cx - half + 2.0, WG_CAN_D / 2 - 1.0), (cx - 1.5, WG_CAN_D / 2),
        (cx + 1.5, WG_CAN_D / 2), (cx + half - 2.0, WG_CAN_D / 2 - 1.0),
        (cx + half, WG_CAN_D / 2 - 4.0), (cx + half, 0.0),
    ])
    crimp = _rev_x([(cx - 2.0, WG_CAN_D / 2 - 0.5), (cx - 2.0, WG_CAN_D / 2 + 2.0),
                    (cx + 2.0, WG_CAN_D / 2 + 2.0), (cx + 2.0, WG_CAN_D / 2 - 0.5)])
    can = _fuse([can, crimp]).moved(bd.Location((0.0, q * cout, cz)))

    rod = _cyl(_p(cx + half - 1.0, cout, cz, q), _p(34.0, cout, cz, q), 8.0)

    wg_out, wg_up = WG_SHAFT
    shaft = _cyl(_p(28.0, wg_out, wg_up, q), _p(52.0, wg_out, wg_up, q), 10.0)
    arm = _prism_x(_strap((wg_out, wg_up), (cout, cz), 13.0), 29.0, 38.0, q)
    clevis = (_cyl(_p(29.0, cout, cz, q), _p(39.0, cout, cz, q), 15.0)
              - _cyl(_p(28.0, cout, cz, q), _p(40.0, cout, cz, q), 8.4))

    bracket = _fuse([
        _prism_x(_strap((42.0, 14.0), (cout, cz), 17.0), -45.0, -38.0, q),
        _cyl(_p(-44.0, cout, cz, q), _p(cx - half + 1.0, cout, cz, q), 18.0),
    ])
    return can, rod, shaft, arm, clevis, bracket


# ---------------------------------------------------------------------------
# One prototype
# ---------------------------------------------------------------------------

def _prototype(q: float):
    """A complete turbo authored about the origin, +X toward the turbine.

    Returns a list of (name, solid, colour).
    """
    out = []

    housing, band, bronze, bead, face, studs = _turbine_housing(q)
    out.append(("turbine_housing", housing, P.HEAT_TINT))
    out.append(("turbine_heat_band", band, P.HEAT_TINT_BLUE))
    if bronze is not None:
        out.append(("turbine_heat_band2", bronze, BRONZE))
    if bead is not None:
        out.append(("turbine_parting", bead, BRONZE))
    if face is not None:
        out.append(("turbine_flange_face", face, P.MACHINED))
    out.append(("turbine_wheel", turbine_wheel(q), P.INCONEL))

    stud = F.stud(T_STUD_D, 16.0, 16.0)
    nut = F.flange_nut(T_STUD_D)
    for i, pt in enumerate(studs, start=1):
        out.append((f"turbine_inlet_stud_{i}", F.place(stud, pt, (0, 0, 1)), P.STEEL_DARK))
        out.append((f"turbine_inlet_nut_{i}",
                    F.place(nut, (pt[0], pt[1], pt[2] + 8.0), (0, 0, 1)), P.STEEL_DARK))

    # downpipe V-band flange ring under the outlet
    fc = _p(T_SCROLL_X - 4.0, 0, T_DUCT_Z, q)
    ring = (bd.Cylinder(T_DP_OD / 2, 13.0, align=(None, None, None)).moved(bd.Location(fc))
            - bd.Cylinder(27.0, 40.0, align=(None, None, None)).moved(bd.Location(fc)))
    ring, _ = safe_fillet(ring, [e for e in ring.edges()
                                 if abs(e.length - math.pi * T_DP_OD) < 1.0], 2.0, min_r=0.5)
    out.append(("downpipe_flange", ring, P.MACHINED))

    centre, pad = _centre_housing(q)
    out.append(("centre_housing", centre, P.CAST))
    if pad is not None:
        out.append(("centre_pad", pad, P.CAST_DARK))
    out.append(("oil_feed_banjo", F.place(F.banjo_bolt(12.0), _p(20.0, 0, 47.0, q), (0, 0, 1)),
                P.TITANIUM))
    eye = (_cyl(_p(20.0, 0, 39.0, q), _p(20.0, 0, 47.0, q), 30.0)
           - _cyl(_p(20.0, 0, 37.0, q), _p(20.0, 0, 49.0, q), 13.0))
    eye = _fuse([eye, _cyl(_p(20.0, 0, 43.0, q), _p(20.0, -28.0, 52.0, q), 12.0)])
    out.append(("oil_feed_eye", eye, P.MACHINED_STEEL))
    drain_bolt = F.hex_flange_bolt(8.0, 22.0)
    for i, so in enumerate((-15.0, 15.0), start=1):
        out.append((f"oil_drain_bolt_{i}",
                    F.place(drain_bolt, _p(-6.0, so, -37.0, q), (0, 0, -1)), P.TITANIUM))

    for name, xj in (("turbine", CH_T_FACE), ("compressor", CH_C_FACE)):
        clamp = _vband_clamp(xj, q)
        out.append((f"vband_clamp_{name}", clamp, P.MACHINED))
        a = math.radians(q * 130.0)
        r = VB_OD / 2 + 6.5
        pt = (xj, r * math.cos(a) * 0.0 + 0.0, 0.0)
        # T-bolt across the two lugs, its axis tangential at the gap
        p0 = ((VB_OD / 2 + 6.5) * math.cos(a), (VB_OD / 2 + 6.5) * math.sin(a))
        tan = (-math.sin(a), math.cos(a))
        bolt_a = (xj, p0[0] - tan[0] * 15.0, p0[1] - tan[1] * 15.0)
        bolt_b = (xj, p0[0] + tan[0] * 15.0, p0[1] + tan[1] * 15.0)
        out.append((f"vband_tbolt_{name}", _cyl(bolt_a, bolt_b, 7.0), P.STEEL_DARK))
        out.append((f"vband_nut_{name}",
                    F.place(F.hex_nut(6.0), (xj, p0[0] + tan[0] * 10.0, p0[1] + tan[1] * 10.0),
                            tan and (0.0, tan[0], tan[1])), P.STEEL_DARK))

    out.append(("compressor_housing", _compressor_housing(q), P.MACHINED))
    out.append(("compressor_outlet_bead", _outlet_bead(q), P.MACHINED))
    out.append(("compressor_wheel", compressor_wheel(q), P.MACHINED))
    out.append(("compressor_shaft_nut",
                F.place(F.hex_nut(10.0), (-88.0, 0.0, 0.0), (-1, 0, 0)), P.MACHINED_STEEL))

    can, rod, shaft, arm, clevis, bracket = _wastegate(q)
    out.append(("wastegate_can", can, P.MACHINED_STEEL))
    out.append(("wastegate_rod", rod, P.MACHINED_STEEL))
    out.append(("wastegate_shaft", shaft, P.STEEL_DARK))
    out.append(("wastegate_arm", arm, P.MACHINED_STEEL))
    out.append(("wastegate_clevis", clevis, P.MACHINED_STEEL))
    out.append(("wastegate_bracket", bracket, P.MACHINED))
    bb = F.hex_flange_bolt(8.0, 20.0)
    for i, (bo, bz) in enumerate(((36.0, 10.0), (47.0, 22.0)), start=1):
        out.append((f"wastegate_bracket_bolt_{i}",
                    F.place(bb, _p(-38.0, bo, bz, q), (1, 0, 0)), P.TITANIUM))
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(sectioned: bool = True):
    """Four turbochargers; the bank-1 front one is cut by the museum section (see module doc)."""
    protos: dict[float, list] = {}
    parts = []
    for t in S.TURBOS:
        s = S.sign_of_bank(t["bank"])
        tdir = t["turbine_dir"]
        q = s if tdir > 0 else -s
        if q not in protos:
            protos[q] = _prototype(q)
        rot = (0.0, 0.0, 0.0) if tdir > 0 else (0.0, 0.0, 180.0)
        loc = bd.Location(t["centre"], rot)
        tag = f"{t['bank']}_{t['pos']}"
        if sectioned and t["bank"] == S.SECTION_BANK and t["centre"][0] > S.SECTION_X:
            continue                               # the museum void: this turbo is lifted off for the display
        for name, shape, colour in protos[q]:
            parts.append(P.style(shape.moved(loc), f"{name}:{tag}", colour))
    return parts


if __name__ == "__main__":
    import sys
    import time

    t0 = time.time()
    solids = build()
    bad = [s.label for s in solids if not geo.sound(s)]
    xs = [s.bounding_box() for s in solids]
    print(f"{len(solids)} solids in {time.time() - t0:.1f}s")
    print("y range", min(b.min.Y for b in xs), max(b.max.Y for b in xs))
    print("z range", min(b.min.Z for b in xs), max(b.max.Z for b in xs))
    print("x range", min(b.min.X for b in xs), max(b.max.X for b in xs))
    if bad:
        print("UNSOUND:", bad)
        sys.exit(1)
    print("all sound")
