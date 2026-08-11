"""F-14D -- the detail layer: what makes it a USED CARRIER AIRCRAFT.

Everything here is small, and almost all of it is placed by QUERYING THE SKIN
(``sections.surfaces``) rather than by guessing a coordinate, so a fairing, a
scribe line or an antenna stays welded to the surface when the loft is retuned.
Three surface samplers do that work -- ``_flank`` (parameterised by station and
height), ``_deck`` and ``_belly`` (parameterised by station and lateral offset).
Each returns a point AND the outward surface normal, and every conformal thing
in this module -- blisters, panels, formation strips, panel-line grooves,
fastener rows -- is built from one of them.

What is here
------------
* The F-14D signature: the TWIN CHIN POD under the radome -- AN/AAS-42 IRST in
  the port lobe, AN/AXX-1 TCS in the starboard lobe -- as ONE faired housing
  with two optical windows.  An F-14A has a bare chin; this is the recognition
  feature and it is modelled as a blended twin-lobe loft, not two cylinders.
* The aircraft's real ASYMMETRY: M61A1 muzzle fairing, blast trough and gun-gas
  purge louvres on the PORT side only; the retractable refuelling probe bay on
  the STARBOARD side only.  Getting these on the wrong sides is the single
  cheapest way to make a Tomcat look wrong.
* Air data: AOA cone (port), pitot head (starboard), total temperature probe.
* Aerials: dorsal and ventral blades, dielectric panels, formation light strips,
  anti-collision beacons, glove position lights, port approach indexer.
* Service: NACA flush inlets, cooling scoops, ECS louvre exhausts, drains,
  boarding ladder door, kick steps and grab handles.
* Structure that READS: panel-line grooves cut into the skin in ONE batched
  multi-tool subtract (published as ``SKIN_CUTTERS``) and fastener domes placed
  as shared instances -- never as thousands of boolean cuts.

Scale discipline.  At 19 m over 1920 px one pixel is about 10 mm, so a scribed
line only reads because the edge overlay draws feature edges: grooves here are
11 mm wide and 4.5 mm deep, which is the narrowest that still produces an edge
pair.  Fastener domes are 2.6 mm proud spheres -- invisible at aircraft scale,
correct in a close-up, and free, because they are instanced, not cut.
"""

from __future__ import annotations

import math

from build123d import (Face, Line, Location, Plane, Solid, Spline, Vector,
                       Wire, loft, make_face)

from cadgen import compound_from_instances

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts.context import biconvex_points, group
from f14_parts import palette as P

M = G.M

# Panel-line geometry.  See the module docstring: these are the smallest values
# that still produce a readable edge pair at aircraft scale.
SCRIBE_W = 11.0
SCRIBE_D = 4.5
SCRIBE_OUT = 5.0                # overshoot outside the skin, per the boolean rule

FASTENER_R = 10.0
FASTENER_PROUD = 2.6


# ---------------------------------------------------------------------------
# surface samplers -- the only way anything in this module finds the skin
# ---------------------------------------------------------------------------


def _flank(x, z, side=1):
    """Point and outward normal on the skin FLANK at station ``x``, height ``z``.

    Solves for the lateral offset where the skin passes through ``z``: above the
    section's mid-height that is the top surface, below it the bottom, and the
    two branches are monotone in y so a bisection is exact and cheap.  Returns
    ``((x, y, z), (0, ny, nz))`` with the normal pointing out of the aircraft.

    If ``z`` is above the crown (or below the keel) the bisection collapses to
    the centreline and the caller gets the crown point with an upward normal --
    a graceful degradation rather than an exception, because a strip walked off
    the top of the fuselage should lie down on it, not vanish.
    """
    hw = SEC.outer_half_width(x)
    t0, b0 = SEC.surfaces(x, 0.0)
    if t0 is None:
        return (x, 0.0, z), (0.0, 0.0, 1.0)
    upper = z >= 0.5 * (t0 + b0)

    def f(y):
        t, b = SEC.surfaces(x, y)
        if t is None:
            return None
        return t if upper else b

    lo, hi = 0.0, hw
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        v = f(mid)
        if v is None:
            hi = mid
            continue
        if (v >= z) if upper else (v <= z):
            lo = mid
        else:
            hi = mid
    y = lo
    d = max(hw * 1.0e-3, 0.4)
    ya, yb = max(y - d, 0.0), min(y + d, hw)
    va, vb = f(ya), f(yb)
    if va is None or vb is None or yb - ya < 1e-9:
        slope = 0.0
    else:
        slope = (vb - va) / (yb - ya)
    ny, nz = (-slope, 1.0) if upper else (slope, -1.0)
    n = math.hypot(ny, nz) or 1.0
    return (x, side * y, z), (0.0, side * ny / n, nz / n)


def _deck(x, y):
    """Point and outward normal on the skin TOP at (x, y)."""
    hw = SEC.outer_half_width(x)
    y = G.clamp(y, -0.985 * hw, 0.985 * hw)
    t, _ = SEC.surfaces(x, y)
    if t is None:
        return (x, y, 0.0), (0.0, 0.0, 1.0)
    d = 3.0
    ta = SEC.surfaces(x, max(y - d, -0.99 * hw))[0]
    tb = SEC.surfaces(x, min(y + d, 0.99 * hw))[0]
    slope = 0.0 if (ta is None or tb is None) else (tb - ta) / (2.0 * d)
    ny, nz = -slope, 1.0
    n = math.hypot(ny, nz) or 1.0
    return (x, y, t), (0.0, ny / n, nz / n)


def _belly(x, y):
    """Point and outward normal on the skin BOTTOM at (x, y)."""
    hw = SEC.outer_half_width(x)
    y = G.clamp(y, -0.985 * hw, 0.985 * hw)
    b = SEC.surfaces(x, y)[1]
    if b is None:
        return (x, y, 0.0), (0.0, 0.0, -1.0)
    d = 3.0
    ba = SEC.surfaces(x, max(y - d, -0.99 * hw))[1]
    bb = SEC.surfaces(x, min(y + d, 0.99 * hw))[1]
    slope = 0.0 if (ba is None or bb is None) else (bb - ba) / (2.0 * d)
    ny, nz = slope, -1.0
    n = math.hypot(ny, nz) or 1.0
    return (x, y, b), (0.0, ny / n, nz / n)


def flank_sampler(side):
    return lambda u, v: _flank(u, v, side)


DECK = _deck
BELLY = _belly


# ---------------------------------------------------------------------------
# small build123d helpers
# ---------------------------------------------------------------------------


def _V(p):
    return p if isinstance(p, Vector) else Vector(*p)


def _face3(pts):
    """Planar face through a closed 3D polygon, duplicate points dropped.

    Consecutive coincident points are a real hazard here: aerofoil and section
    samplers legitimately return the same point twice at a knife edge, and a
    zero-length Line kills the wire.
    """
    vs = []
    for p in pts:
        v = _V(p)
        if vs and (v - vs[-1]).length < 1.0e-6:
            continue
        vs.append(v)
    while len(vs) > 3 and (vs[0] - vs[-1]).length < 1.0e-6:
        vs.pop()
    edges = [Line(vs[i], vs[(i + 1) % len(vs)]).edge() for i in range(len(vs))]
    wire = Wire(edges)
    # Face(), not make_face(): this build123d's make_face returns a Sketch
    # compound, which loft() tolerates but Solid.extrude() refuses outright.
    try:
        return Face(wire)
    except Exception:  # noqa: BLE001
        return make_face(wire)


def _call(v, *args):
    return v(*args) if callable(v) else v


def _rod(p0, p1, r):
    a, b = _V(p0), _V(p1)
    d = b - a
    return Solid.make_cylinder(r, d.length, Plane(origin=a, z_dir=d.normalized()))


def _cone(p0, p1, r0, r1):
    a, b = _V(p0), _V(p1)
    d = b - a
    return Solid.make_cone(r0, r1, d.length, Plane(origin=a, z_dir=d.normalized()))


def _scribe(sampler, path, w=SCRIBE_W, out=SCRIBE_OUT, inn=-SCRIBE_D):
    """A groove/rib solid following a path of (u, v) points on a sampler.

    At every sample the cross-section is a rectangle in the plane spanned by the
    surface normal and the path's binormal, so the groove keeps a constant width
    ON THE SURFACE and a constant depth INTO it however the skin curves.  With
    ``out`` positive and ``inn`` negative it is a skin cutter; with both positive
    it is a proud rib.
    """
    pts, norms = [], []
    for u, v in path:
        p, n = sampler(u, v)
        pts.append(_V(p))
        norms.append(_V(n))
    faces = []
    last = None
    for i, (p, n) in enumerate(zip(pts, norms)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = b - a
        if t.length < 1.0e-6:
            continue
        t = t.normalized()
        bi = t.cross(n)
        if bi.length < 1.0e-9:
            continue
        bi = bi.normalized()
        if last is not None and (p - last).length < 1.0e-6:
            continue
        last = p
        quad = [p + n * out + bi * (0.5 * w), p + n * out - bi * (0.5 * w),
                p + n * inn - bi * (0.5 * w), p + n * inn + bi * (0.5 * w)]
        faces.append(_face3(quad))
    if len(faces) < 2:
        return None
    return loft(faces, ruled=True)


def _patch(sampler, us, v0, v1, out, inn, nv=7):
    """A conformal skin patch: blister, flush panel, strip or shallow pocket.

    ``v0``/``v1`` may be callables of ``u`` (so a patch can taper in plan) and
    ``out``/``inn`` callables of ``(u_frac, v_frac)`` (so a blister can swell in
    the middle and die at its edges).  Sections are taken at each ``u`` as a
    ribbon -- surface points out, then the same points in, reversed -- which is
    what keeps the patch ON the surface instead of chording across it.
    """
    faces = []
    n_u = len(us)
    for i, u in enumerate(us):
        fu = i / (n_u - 1) if n_u > 1 else 0.0
        a, b = _call(v0, u), _call(v1, u)
        outer, inner = [], []
        for j in range(nv):
            fv = j / (nv - 1) if nv > 1 else 0.0
            p, nrm = sampler(u, a + (b - a) * fv)
            p, nrm = _V(p), _V(nrm)
            outer.append(p + nrm * _call(out, fu, fv))
            inner.append(p + nrm * _call(inn, fu, fv))
        faces.append(_face3(outer + list(reversed(inner))))
    if len(faces) < 2:
        return None
    return loft(faces, ruled=True)


def _ring_groove(x, w=SCRIBE_W, depth=SCRIBE_D, out=SCRIBE_OUT):
    """A groove all the way round the fuselage at one station.

    Built by offsetting the station's own section outline, so it lands exactly
    on the skin wherever the loft puts it.  Only used forward of the inlets,
    where the section is convex and an outward offset cannot self-intersect.
    """
    pts = [p for p in SEC.section_points(x, 64)]
    if len(pts) < 8:
        return None
    cy = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)
    outer, inner = [], []
    n = len(pts)
    for i in range(n):
        y0, z0 = pts[i - 1]
        y1, z1 = pts[(i + 1) % n]
        ty, tz = y1 - y0, z1 - z0
        ny, nz = tz, -ty
        if (pts[i][0] - cy) * ny + (pts[i][1] - cz) * nz < 0.0:
            ny, nz = -ny, -nz
        ln = math.hypot(ny, nz) or 1.0
        ny, nz = ny / ln, nz / ln
        outer.append((x, pts[i][0] + ny * out, pts[i][1] + nz * out))
        inner.append((x, pts[i][0] - ny * depth, pts[i][1] - nz * depth))
    try:
        so = Solid.extrude(_face3(outer), Vector(w, 0, 0))
        si = Solid.extrude(_face3(inner), Vector(w, 0, 0))
        ring = so - si
    except Exception:  # noqa: BLE001
        return None
    return Location((-0.5 * w, 0, 0)) * ring


def _rect_panel(sampler, u0, u1, v0, v1, w=SCRIBE_W, out=SCRIBE_OUT,
                inn=-SCRIBE_D, nu=9, nv=6):
    """A scribed rectangular hatch outline, fused into ONE cutter.

    Four separate segments meeting at four corners are four overlapping tools;
    fusing them here means the skin subtract sees one disjoint solid per hatch
    instead of a corner-tangency network to resolve.
    """
    du, dv = 0.5 * w, 0.5 * w
    legs = []
    for v in (v0, v1):
        legs.append(_scribe(sampler,
                            [(u0 - du + (u1 - u0 + 2 * du) * i / (nu - 1), v)
                             for i in range(nu)], w, out, inn))
    for u in (u0, u1):
        legs.append(_scribe(sampler,
                            [(u, v0 - dv + (v1 - v0 + 2 * dv) * i / (nv - 1))
                             for i in range(nv)], w, out, inn))
    legs = [s for s in legs if s is not None]
    if not legs:
        return []
    try:
        fused = legs[0] + legs[1:]
        return [fused]
    except Exception:  # noqa: BLE001
        return legs


def _fasteners(sampler, path, radius=FASTENER_R, proud=FASTENER_PROUD):
    """(Location, ...) list for a row of fastener domes along a surface path."""
    out = []
    for u, v in path:
        p, n = sampler(u, v)
        c = _V(p) - _V(n) * (radius - proud)
        out.append(Location((c.X, c.Y, c.Z)))
    return out


def _blade(chord, thick, tip_chord, tip_thick, height, sweep, root=-30.0):
    """A blade aerial: symmetric biconvex, swept, root buried below z=0."""
    b = biconvex_points(thick / chord, chord, n=20)
    t = biconvex_points(tip_thick / tip_chord, tip_chord, n=20)
    f0 = _face3([(px, py, root) for px, py in b])
    f1 = _face3([(px + sweep, py, height) for px, py in t])
    return loft([f0, f1], ruled=True)


def _dome(point, normal, radius, proud):
    """A sphere buried so exactly ``proud`` of it stands off the surface."""
    c = _V(point) - _V(normal) * (radius - proud)
    return Location((c.X, c.Y, c.Z)) * Solid.make_sphere(radius)


def _lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _lens(sampler, u, v, r_long, r_short, proud, depth=26.0):
    """A flush light lens / static port: a shallow conformal disc."""
    p, n = sampler(u, v)
    p, n = _V(p), _V(n)
    ref = Vector(0, 0, 1) if abs(n.Z) < 0.9 else Vector(1, 0, 0)
    e1 = n.cross(ref).normalized()
    e2 = n.cross(e1).normalized()
    base = p - n * depth
    poly = []
    for i in range(24):
        a = 2.0 * math.pi * i / 24
        poly.append(base + e1 * (r_long * math.cos(a)) + e2 * (r_short * math.sin(a)))
    return Solid.extrude(_face3(poly), n * (depth + proud))


# ===========================================================================
# 1.  THE TWIN CHIN POD  --  AN/AAS-42 IRST (port) + AN/AXX-1 TCS (starboard)
# ===========================================================================
#
# One faired housing with two lobes, NOT two pods bolted under a plate.  Both
# the depth and the width are driven from one shape parameter s(x), so the
# fairing grows out of the keel at the front, carries two distinct lobes at its
# widest, and dies back into the keel aft -- there is no station where the
# housing is wider than the radome it hangs off, which is what a lobe ending on
# the silhouette would give.

POD_X0, POD_X1 = 1.020 * M, 2.980 * M
POD_S = [(1020.0, 0.0), (1075.0, 0.40), (1150.0, 0.68), (1300.0, 0.88),
         (1560.0, 0.985), (2100.0, 0.98), (2440.0, 0.79), (2740.0, 0.40),
         (2980.0, 0.0)]
POD_YP = 180.0                  # lobe axis offset at full size
POD_RL = 172.0                  # lobe half-width at full size
POD_H = 345.0                   # depth below the keel at full size
POD_UP = 62.0                   # overlap up INTO the skin
POD_WEB = 0.72                  # depth of the valley between the lobes

X_TCS_WINDOW = 1.205 * M


def _pod_scale(x):
    s = G._curve(POD_S, x)
    return s, 0.20 + 0.80 * s


def _pod_lobe_axis(x):
    """(y_offset, keel_z, depth) of one lobe at station ``x``."""
    s, k = _pod_scale(x)
    yp = POD_YP * k
    z = SEC.surfaces(x, yp)[1]
    return yp, z, POD_H * s


def _pod_section(x, n=37):
    s, k = _pod_scale(x)
    yp, rl, w = POD_YP * k, POD_RL * k, (POD_YP + POD_RL) * k
    h = POD_H * s

    def depth(y):
        g = []
        for yc in (yp, -yp):
            u = (y - yc) / rl
            g.append(math.sqrt(max(0.0, 1.0 - u * u)))
        uw = y / (yp + 0.45 * rl)
        g.append(POD_WEB * math.sqrt(max(0.0, 1.0 - min(uw * uw, 1.0))))
        return G.smax_all(g, 0.30)

    top, bot = [], []
    for i in range(n):
        y = -w + 2.0 * w * i / (n - 1)
        skin = SEC.surfaces(x, y)[1]
        if skin is None:
            skin = SEC.surfaces(x, 0.0)[1]
        top.append(Vector(x, y, skin + POD_UP))
        bot.append(Vector(x, y, skin - h * depth(y)))
    wire = Wire([Spline(*top).edge(), Line(top[-1], bot[-1]).edge(),
                 Spline(*list(reversed(bot))).edge(), Line(bot[0], top[0]).edge()])
    return Face(wire)


def _chin_housing():
    xs = _lin(POD_X0, POD_X1, 24)
    return loft([_pod_section(x) for x in xs], ruled=False)


def _pod_window(side, kind):
    """One sensor window: glass, bezel and hood, on the front of a lobe.

    The two are deliberately NOT identical -- the IRST's germanium window is a
    small deep-set circle, the TCS's is a wider, shallower optical port -- so
    the chin reads as two different sensors rather than one part mirrored.
    """
    x = X_TCS_WINDOW
    yp, keel, h = _pod_lobe_axis(x)
    z = keel - 0.55 * h
    tilt = math.radians(24.0)
    axis = Vector(-math.cos(tilt), 0.0, -math.sin(tilt))
    c = Vector(x, side * yp, z)
    r_glass, r_bezel = (74.0, 96.0) if kind == "irst" else (92.0, 112.0)
    glass = Solid.make_cylinder(
        r_glass, 46.0, Plane(origin=c - axis * 6.0, z_dir=axis))
    bezel = Solid.make_cone(
        r_bezel, r_bezel - 10.0, 54.0, Plane(origin=c - axis * 40.0, z_dir=axis))
    return glass, bezel


def chin_pods():
    kids = []
    kids.append(P.style(_chin_housing(), "chin_pod_fairing", P.GREY_LIGHT))
    for side, tag, kind in ((1, "port", "irst"), (-1, "stbd", "tcs")):
        glass, bezel = _pod_window(side, kind)
        kids.append(P.style(bezel, f"chin_pod_bezel:{tag}", P.ALUM_DARK))
        kids.append(P.style(glass, f"chin_pod_window_{kind}:{tag}",
                            P.COCKPIT_BLACK))
    # the joint ring where the pod fairing bolts to the radome underside
    for x in (2.560 * M,):
        for side, tag in ((1, "port"), (-1, "stbd")):
            yp, keel, h = _pod_lobe_axis(x)
            ring = _rod((x - 6.0, side * yp, keel - 0.5 * h),
                        (x + 6.0, side * yp, keel - 0.5 * h), 0.62 * h)
            kids.append(P.style(ring, f"chin_pod_joint:{tag}", P.PANEL_DARK))
    return kids


# ===========================================================================
# 2.  IN-FLIGHT REFUELLING PROBE  --  STARBOARD SHOULDER, RETRACTED
# ===========================================================================
#
# On the aircraft the probe lives in a fairing on the RIGHT shoulder of the
# nose, just forward of and below the windscreen, and retracts fully behind a
# door.  Parked it shows as a fairing, a door outline, and the probe head
# sitting in its recess -- so all three are modelled and the recess is a real
# pocket, not a painted-on rectangle.

PROBE_X0, PROBE_X1 = 3.060 * M, 4.140 * M
PROBE_Z = 0.700 * M
PROBE_HALF = 0.135 * M
PROBE_BULGE = 92.0


def refuel_probe():
    side = -1                                   # STARBOARD
    smp = flank_sampler(side)
    xs = _lin(PROBE_X0, PROBE_X1, 15)

    def swell(fu, fv):
        a = max(0.0, 1.0 - (2.0 * fu - 1.0) ** 2) ** 0.55
        b = max(0.0, 1.0 - (2.0 * fv - 1.0) ** 2) ** 0.45
        return PROBE_BULGE * a * b

    fairing = _patch(smp, xs, PROBE_Z - PROBE_HALF, PROBE_Z + PROBE_HALF,
                     swell, -24.0, nv=9)
    kids = [P.style(fairing, "refuel_probe_fairing:stbd", P.GREY_DARK)]

    # The bay door: a slightly proud plate over the aft two thirds of the
    # fairing, riding on the fairing's own outer surface.
    dxs = _lin(PROBE_X0 + 190.0, PROBE_X1 - 90.0, 9)

    def door_out(fu, fv):
        u = (dxs[0] + (dxs[-1] - dxs[0]) * fu - PROBE_X0) / (PROBE_X1 - PROBE_X0)
        v = 0.5 * (fv + 0.28)
        return swell(u, v) + 5.0

    door = _patch(smp, dxs, PROBE_Z - 0.085 * M, PROBE_Z + 0.088 * M,
                  door_out, 6.0, nv=7)
    kids.append(P.style(door, "refuel_probe_door:stbd", P.GREY_MID))

    # The recess and the retracted probe head inside it.
    p0, n0 = _flank(PROBE_X0 + 155.0, PROBE_Z + 0.012 * M, side)
    p0, n0 = _V(p0), _V(n0)
    mouth = p0 + n0 * (swell(0.14, 0.55) - 16.0)
    recess = _rod(mouth - Vector(70.0, 0, 0), mouth + Vector(150.0, 0, 0), 58.0)
    kids.append(P.style(recess, "refuel_probe_recess:stbd", P.WIRE_LOOM))
    head = _cone(mouth + Vector(96.0, 0, 0), mouth + Vector(-8.0, 0, 0), 40.0, 30.0)
    kids.append(P.style(head, "refuel_probe_head:stbd", P.STEEL_DARK))
    nozzle = _rod(mouth + Vector(6.0, 0, 0), mouth + Vector(-34.0, 0, 0), 17.0)
    kids.append(P.style(nozzle, "refuel_probe_nozzle:stbd", P.OLEO_CHROME))
    return kids


# ===========================================================================
# 3.  M61A1 VULCAN INSTALLATION  --  PORT SIDE ONLY
# ===========================================================================
#
# The gun lives in the lower LEFT forward fuselage.  What shows outside is a
# shallow streamwise fairing over the barrel cluster, the muzzle port with its
# blast trough, the gun-gas purge louvres immediately aft of it, and a gas
# purge port further aft.  The trough and the skin behind it carry the gun-gas
# staining that is the most obvious "this aircraft is used" cue on a Tomcat.

GUN_X0, GUN_X1 = 3.290 * M, 4.640 * M
GUN_Z = 0.345 * M
GUN_HALF = 0.150 * M
GUN_BULGE = 58.0
X_MUZZLE = 3.470 * M


def _gun_swell(fu, fv):
    a = max(0.0, 1.0 - (2.0 * fu - 1.0) ** 2) ** 0.42
    b = max(0.0, 1.0 - (2.0 * fv - 1.0) ** 2) ** 0.45
    return GUN_BULGE * a * b


def gun():
    side = 1                                    # PORT
    smp = flank_sampler(side)
    kids = []
    xs = _lin(GUN_X0, GUN_X1, 15)
    fairing = _patch(smp, xs, GUN_Z - GUN_HALF, GUN_Z + GUN_HALF,
                     _gun_swell, -22.0, nv=9)
    kids.append(P.style(fairing, "gun_fairing:port", P.GREY_MID))

    # muzzle port: a dark trough floor set INTO the fairing, with the barrel
    # cluster sitting in it
    p, n = _flank(X_MUZZLE, GUN_Z, side)
    p, n = _V(p), _V(n)
    face = p + n * (_gun_swell(0.14, 0.5) - 10.0)
    trough = _patch(smp, _lin(X_MUZZLE - 120.0, X_MUZZLE + 620.0, 9),
                    GUN_Z - 62.0, GUN_Z + 62.0,
                    lambda fu, fv: _gun_swell(0.10 + 0.42 * fu, 0.5 * (fv + 0.5)) - 26.0,
                    -46.0, nv=5)
    kids.append(P.style(trough, "gun_blast_trough:port", P.EXHAUST_SOOT))
    muzzle = _rod(face + Vector(-40.0, 0, 0), face + Vector(210.0, 0, 0), 62.0)
    kids.append(P.style(muzzle, "gun_muzzle_port:port", P.WIRE_LOOM))
    barrels = _rod(face + Vector(-6.0, 0, 0), face + Vector(180.0, 0, 0), 46.0)
    kids.append(P.style(barrels, "gun_barrel_cluster:port", P.STEEL_DARK))

    # gun-gas purge louvres: a dark slot with proud slats over it
    lx0, lx1 = 4.060 * M, 4.520 * M
    slot = _patch(smp, _lin(lx0 - 30.0, lx1 + 30.0, 7),
                  GUN_Z - 74.0, GUN_Z + 74.0,
                  lambda fu, fv: _gun_swell(0.55 + 0.35 * fu, 0.5 * (fv + 0.5)) - 20.0,
                  -34.0, nv=5)
    kids.append(P.style(slot, "gun_purge_slot:port", P.WIRE_LOOM))
    for i in range(5):
        lx = lx0 + (lx1 - lx0) * i / 4.0
        slat = _scribe(smp, [(lx, GUN_Z - 72.0 + 36.0 * k) for k in range(5)],
                       w=16.0,
                       out=_gun_swell(0.6 + 0.3 * (i / 4.0), 0.5) - 4.0,
                       inn=-26.0)
        if slat is not None:
            kids.append(P.style(slat, f"gun_purge_louvre:port_{i:02d}",
                                P.PANEL_DARK))

    # gas purge port, and the two blow-out discs above the ammunition drum
    kids.append(P.style(_lens(smp, 4.810 * M, 0.210 * M, 52.0, 52.0, 3.0),
                        "gun_gas_port:port", P.STEEL_BURN))
    for i, (bx, bz) in enumerate(((4.180 * M, 0.640 * M), (4.520 * M, 0.640 * M))):
        kids.append(P.style(_lens(smp, bx, bz, 46.0, 46.0, 4.0),
                            f"gun_blowout_disc:port_{i:02d}", P.PANEL_LIGHT))
    return kids


# ===========================================================================
# 4.  AIR DATA  --  AOA cone (port), pitot head (starboard), temperature probe
# ===========================================================================

X_AOA = 1.310 * M
Z_AOA = 0.120 * M
X_PITOT = 1.310 * M
Z_PITOT = 0.120 * M
X_TAT = 2.240 * M
Z_TAT = 0.300 * M


def air_data():
    kids = []

    # AOA cone, PORT.  A truncated cone standing off the skin with the vane
    # slot cut across its tip.
    p, n = _flank(X_AOA, Z_AOA, 1)
    p, n = _V(p), _V(n)
    kids.append(P.style(_cone(p - n * 22.0, p + n * 46.0, 40.0, 33.0),
                        "aoa_probe_base:port", P.ALUM_DARK))
    kids.append(P.style(_cone(p + n * 40.0, p + n * 106.0, 33.0, 20.0),
                        "aoa_probe_cone:port", P.ALUMINIUM))
    vane = _rod(p + n * 96.0 + Vector(-52.0, 0, 0), p + n * 96.0 + Vector(30.0, 0, 0),
                8.0)
    kids.append(P.style(vane, "aoa_probe_vane:port", P.STEEL_DARK))

    # Pitot head, STARBOARD: strut out of the skin, tube forward.
    p, n = _flank(X_PITOT, Z_PITOT, -1)
    p, n = _V(p), _V(n)
    kids.append(P.style(_cone(p - n * 20.0, p + n * 74.0, 34.0, 22.0),
                        "pitot_strut:stbd", P.ALUM_DARK))
    tip = p + n * 74.0
    kids.append(P.style(_cone(tip + Vector(120.0, 0, 0), tip + Vector(-190.0, 0, 0),
                              22.0, 15.0),
                        "pitot_head:stbd", P.OLEO_CHROME))

    # Total temperature probe, STARBOARD, aft of the pitot: an L, mast then
    # forward-facing intake.
    p, n = _flank(X_TAT, Z_TAT, -1)
    p, n = _V(p), _V(n)
    kids.append(P.style(_cone(p - n * 18.0, p + n * 88.0, 26.0, 18.0),
                        "tat_probe_mast:stbd", P.ALUM_DARK))
    head = p + n * 84.0
    kids.append(P.style(_rod(head + Vector(52.0, 0, 0), head + Vector(-86.0, 0, 0),
                             17.0),
                        "tat_probe_head:stbd", P.OLEO_CHROME))

    # flush static port pairs, both sides
    for side, tag in ((1, "port"), (-1, "stbd")):
        smp = flank_sampler(side)
        for i, sx in enumerate((2.180 * M, 2.330 * M)):
            kids.append(P.style(_lens(smp, sx, 0.010 * M, 30.0, 30.0, 2.0),
                                f"static_port:{tag}_{i:02d}", P.ALUM_DARK))
    return kids


# ===========================================================================
# 5.  AERIALS, BLADES AND DIELECTRIC PANELS
# ===========================================================================

BLADES = (
    # (label,      x,        y,     surface, chord, thick, tipc, tipt, h,   sweep)
    ("uhf_fwd",    7.960 * M, 0.0,  "deck",  340.0, 44.0, 190.0, 17.0, 250.0, 128.0),
    ("uhf_aft",   13.420 * M, 0.0,  "deck",  300.0, 40.0, 165.0, 15.0, 215.0, 112.0),
    ("iff_upper", 10.150 * M, 0.0,  "deck",  240.0, 34.0, 140.0, 13.0, 165.0,  86.0),
    ("iff_lower",  5.280 * M, 0.0,  "belly", 265.0, 36.0, 150.0, 14.0, 185.0,  96.0),
    ("tacan_low", 12.480 * M, 0.320 * M, "belly", 240.0, 34.0, 138.0, 13.0,
     168.0, 88.0),
)


def aerials():
    kids = []
    for (name, x, y, surf, c, t, tc, tt, h, sw) in BLADES:
        p, _ = (DECK(x, y) if surf == "deck" else BELLY(x, y))
        blade = _blade(c, t, tc, tt, h, sw)
        if surf == "deck":
            loc = Location((p[0] - 0.5 * c, p[1], p[2]))
        else:
            loc = Location((p[0] - 0.5 * c, p[1], p[2]), (180.0, 0.0, 0.0))
        kids.append(P.style(loc * blade, f"blade_aerial_{name}", P.DIELECTRIC))

    # Flush dielectric panels: the UHF/IFF apertures.  Flat 5 mm-proud plates so
    # the edge overlay draws their outline the way a real dielectric insert
    # shows against paint.
    spine = _patch(DECK, _lin(8.900 * M, 9.780 * M, 7),
                   -0.215 * M, 0.215 * M, 5.0, -14.0, nv=7)
    kids.append(P.style(spine, "dielectric_panel_spine", P.DIELECTRIC))
    for side, tag in ((1, "port"), (-1, "stbd")):
        smp = flank_sampler(side)
        panel = _patch(smp, _lin(5.150 * M, 5.900 * M, 7),
                       0.140 * M, 0.500 * M, 5.0, -14.0, nv=7)
        kids.append(P.style(panel, f"dielectric_panel_fwd:{tag}", P.DIELECTRIC))
        vent = _patch(BELLY, _lin(6.750 * M, 7.400 * M, 7),
                      side * 0.140 * M, side * 0.470 * M, 5.0, -14.0, nv=7)
        kids.append(P.style(vent, f"dielectric_panel_low:{tag}", P.DIELECTRIC))
    return kids


# ===========================================================================
# 6.  LIGHTS  --  formation strips, beacons, position lights, indexer
# ===========================================================================


def lights():
    kids = []

    # Electroluminescent formation strips.  Flat panels, 6 mm proud, following
    # the skin: forward fuselage sides, glove upper surface, nacelle sides.
    for side, tag in ((1, "port"), (-1, "stbd")):
        smp = flank_sampler(side)
        strip = _patch(smp, _lin(3.620 * M, 5.020 * M, 11),
                       0.596 * M, 0.664 * M, 6.0, -10.0, nv=4)
        kids.append(P.style(strip, f"formation_strip_fwd:{tag}", P.FORMATION))

        glove = _patch(DECK, _lin(7.700 * M, 11.300 * M, 11),
                       side * 2.018 * M, side * 2.082 * M, 6.0, -10.0, nv=4)
        kids.append(P.style(glove, f"formation_strip_glove:{tag}", P.FORMATION))

        nac = _patch(smp, _lin(13.700 * M, 16.400 * M, 9),
                     -0.034 * M, 0.034 * M, 6.0, -10.0, nv=4)
        kids.append(P.style(nac, f"formation_strip_nacelle:{tag}", P.FORMATION))

    # Anti-collision beacons, top and bottom.
    p, n = DECK(7.640 * M, 0.0)
    kids.append(P.style(_dome(p, n, 78.0, 46.0), "beacon_upper", P.BEACON_RED))
    kids.append(P.style(_lens(DECK, 7.640 * M, 0.0, 86.0, 86.0, 8.0),
                        "beacon_upper_base", P.ALUM_DARK))
    p, n = BELLY(8.350 * M, 0.0)
    kids.append(P.style(_dome(p, n, 78.0, 46.0), "beacon_lower", P.BEACON_RED))
    kids.append(P.style(_lens(BELLY, 8.350 * M, 0.0, 86.0, 86.0, 8.0),
                        "beacon_lower_base", P.ALUM_DARK))

    # Position lights on the glove leading edge: red to port, green to
    # starboard, sitting ON the LE line the glove sweep publishes.
    for side, tag, colour in ((1, "port", P.LIGHT_RED), (-1, "stbd", P.LIGHT_GREEN)):
        y = 2.100 * M
        x = G.glove_le_x(y) + 46.0
        z = G.glove_camber_z(x, y)
        lens = _cone((x - 118.0, side * y, z), (x + 58.0, side * y, z), 20.0, 46.0)
        kids.append(P.style(lens, f"position_light_glove:{tag}", colour))

    # Approach indexer, PORT nose only: the three-lamp AOA repeater the LSO
    # reads on the ball.
    smp = flank_sampler(1)
    for i, (z, colour, nm) in enumerate(((0.735 * M, P.LIGHT_GREEN, "green"),
                                         (0.648 * M, P.HANDLE_YELLOW, "amber"),
                                         (0.560 * M, P.LIGHT_RED, "red"))):
        kids.append(P.style(_lens(smp, 3.330 * M, z, 30.0, 22.0, 5.0),
                            f"approach_indexer_{nm}:port", colour))
    return kids


# ===========================================================================
# 7.  VENTS  --  NACA flush inlets, cooling scoops, ECS louvre exhausts, drains
# ===========================================================================

NACA_DUCTS = (
    # (name,       surface, x0,        x1,        y_centre,   half,  depth)
    ("ecs_fwd",    "deck",  11.620 * M, 12.180 * M,  0.520 * M, 92.0, 48.0),
    ("ecs_aft",    "deck",  15.150 * M, 15.780 * M,  0.430 * M, 88.0, 46.0),
    ("gen_cool",   "belly",  9.050 * M,  9.560 * M,  0.640 * M, 78.0, 40.0),
)


def _naca_cut(surface, x0, x1, yc, half, depth, side):
    smp = DECK if surface == "deck" else BELLY
    xs = _lin(x0, x1, 9)

    def v0(x):
        f = (x - x0) / (x1 - x0)
        return side * (yc - half * (0.18 + 0.82 * f ** 0.7))

    def v1(x):
        f = (x - x0) / (x1 - x0)
        return side * (yc + half * (0.18 + 0.82 * f ** 0.7))

    def inn(fu, fv):
        ramp = fu ** 1.35
        return -depth * ramp * (1.0 - 0.35 * abs(2.0 * fv - 1.0) ** 2)

    return _patch(smp, xs, v0, v1, SCRIBE_OUT, inn, nv=7)


def _naca_throat(surface, x1, yc, half, depth, side):
    smp = DECK if surface == "deck" else BELLY
    return _patch(smp, _lin(x1 - 60.0, x1 + 6.0, 3),
                  side * (yc - half), side * (yc + half),
                  lambda fu, fv: -depth * (0.55 + 0.45 * fu),
                  lambda fu, fv: -depth - 34.0, nv=5)


def vent_cutters():
    out = []
    for (_name, surf, x0, x1, yc, half, depth) in NACA_DUCTS:
        for side in (1, -1):
            c = _naca_cut(surf, x0, x1, yc, half, depth, side)
            if c is not None:
                out.append(c)
    return out


def vents():
    kids = []
    for (name, surf, x0, x1, yc, half, depth) in NACA_DUCTS:
        for side, tag in ((1, "port"), (-1, "stbd")):
            t = _naca_throat(surf, x1, yc, half, depth, side)
            if t is not None:
                kids.append(P.style(t, f"naca_throat_{name}:{tag}", P.WIRE_LOOM))

    # Proud cooling scoops on the fuselage flanks: a swelling with a dark mouth
    # cut across its forward face.
    for side, tag in ((1, "port"), (-1, "stbd")):
        smp = flank_sampler(side)
        for i, (sx, sz, ln, ht) in enumerate((
                (12.650 * M, 0.330 * M, 420.0, 88.0),
                (14.950 * M, 0.280 * M, 360.0, 76.0))):
            scoop = _patch(smp, _lin(sx, sx + ln, 7), sz - ht, sz + ht,
                           lambda fu, fv, ht=ht: 46.0 * (fu ** 0.5)
                           * max(0.0, 1.0 - (2.0 * fv - 1.0) ** 2) ** 0.5,
                           -18.0, nv=7)
            if scoop is not None:
                kids.append(P.style(scoop, f"cooling_scoop:{tag}_{i:02d}",
                                    P.GREY_MID))
            mouth = _patch(smp, _lin(sx - 6.0, sx + 44.0, 3), sz - 0.72 * ht,
                           sz + 0.72 * ht,
                           lambda fu, fv: 12.0 * fu, -14.0, nv=5)
            if mouth is not None:
                kids.append(P.style(mouth, f"cooling_scoop_mouth:{tag}_{i:02d}",
                                    P.WIRE_LOOM))

        # ECS louvre exhaust: a dark recess with four proud slats over it.
        ex0, ex1, ez = 16.150 * M, 16.740 * M, 0.180 * M
        rec = _patch(smp, _lin(ex0, ex1, 5), ez - 88.0, ez + 88.0,
                     2.0, -40.0, nv=5)
        if rec is not None:
            kids.append(P.style(rec, f"ecs_exhaust:{tag}", P.WIRE_LOOM))
        for i in range(4):
            lx = ex0 + 70.0 + (ex1 - ex0 - 140.0) * i / 3.0
            slat = _scribe(smp, [(lx, ez - 84.0 + 42.0 * k) for k in range(5)],
                           w=20.0, out=6.0, inn=-30.0)
            if slat is not None:
                kids.append(P.style(slat, f"ecs_louvre:{tag}_{i:02d}",
                                    P.PANEL_DARK))

        # fuel vents and drain masts under the fuselage
        for i, dx in enumerate((6.900 * M, 8.700 * M)):
            p, n = BELLY(dx, side * 0.760 * M)
            mast = _cone(_V(p) + _V(n) * 8.0, _V(p) + _V(n) * 64.0, 22.0, 12.0)
            kids.append(P.style(mast, f"drain_mast:{tag}_{i:02d}", P.ALUM_DARK))
        kids.append(P.style(_lens(BELLY, 5.700 * M, side * 0.330 * M,
                                  34.0, 34.0, 3.0),
                            f"vent_flush:{tag}", P.ALUM_DARK))
    return kids


# ===========================================================================
# 8.  BOARDING  --  integral ladder door, kick steps, grab handles (PORT)
# ===========================================================================

LADDER_X0, LADDER_X1 = 4.360 * M, 5.360 * M
LADDER_Z0, LADDER_Z1 = 0.170 * M, 0.520 * M
STEPS = ((5.560 * M, 0.300 * M), (5.960 * M, 0.430 * M))


def boarding_cutters():
    """Kick-step recesses: real pockets, because a painted step reads as paint."""
    smp = flank_sampler(1)
    out = []
    for sx, sz in STEPS:
        c = _patch(smp, _lin(sx - 88.0, sx + 88.0, 5), sz - 56.0, sz + 56.0,
                   SCRIBE_OUT, -52.0, nv=5)
        if c is not None:
            out.append(c)
    return out


def boarding():
    smp = flank_sampler(1)
    kids = []
    door = _patch(smp, _lin(LADDER_X0, LADDER_X1, 9), LADDER_Z0, LADDER_Z1,
                  4.0, -16.0, nv=7)
    kids.append(P.style(door, "boarding_ladder_door:port", P.PANEL_DARK))
    for i, (sx, sz) in enumerate(STEPS):
        floor = _patch(smp, _lin(sx - 80.0, sx + 80.0, 5), sz - 48.0, sz + 48.0,
                       -44.0, -60.0, nv=5)
        if floor is not None:
            kids.append(P.style(floor, f"kick_step:port_{i:02d}", P.WALKWAY))
    # grab handles under the canopy sill
    for i, hx in enumerate((4.680 * M, 5.180 * M)):
        p, n = _flank(hx, 0.845 * M, 1)
        p, n = _V(p), _V(n)
        bar = _rod(p + n * 34.0 + Vector(-95.0, 0, 0),
                   p + n * 34.0 + Vector(95.0, 0, 0), 13.0)
        kids.append(P.style(bar, f"grab_handle:port_{i:02d}", P.ALUM_DARK))
        for k, dx in enumerate((-92.0, 92.0)):
            post = _rod(p - n * 12.0 + Vector(dx, 0, 0),
                        p + n * 34.0 + Vector(dx, 0, 0), 12.0)
            kids.append(P.style(post, f"grab_handle_post:port_{i:02d}{k}",
                                P.ALUM_DARK))
    return kids


# ===========================================================================
# 9.  STATIC DISCHARGE WICKS
# ===========================================================================
#
# Placed only where geometry.py fixes the trailing edge without ambiguity: the
# fin tips (root station, height, cant and tip chord are all published), and the
# wing panel trailing edge, which falls out of the published tip position at
# SWEEP plus the root/tip chords.  Each wick starts 150 mm FORWARD of the
# nominal edge and is buried in it, so a wing or fin built a little differently
# still swallows the root instead of leaving the rod hanging in air.
#
# Deliberately NOT on the stabilator: its published root chord, LE sweep and
# pivot station do not close on one trailing edge (they put the tip TE a metre
# aft of the published overall length), so any wick there would be a guess.

WICK_LEN = 235.0
WICK_BURY = 150.0


def _wick_proto(drop):
    return _cone((-WICK_BURY, 0.0, 0.0), (WICK_LEN, 0.0, drop), 8.0, 2.6)


def _wing_te(y_abs):
    """(x, z) of the wing panel trailing edge at |y|, wings at G.SWEEP."""
    tip_x, tip_y = G.wing_tip_xy(G.SWEEP, 1)
    root_y = G.Y_WING_ROOT
    t = G.clamp((y_abs - root_y) / (tip_y - root_y), 0.0, 1.0)
    le = tip_x - (tip_y - y_abs) * math.tan(math.radians(G.SWEEP))
    chord = G.lerp(G.WING_ROOT_CHORD, G.WING_TIP_CHORD, t)
    return le + chord, G.glove_camber_z(le + chord, root_y)


def wicks():
    items = []
    proto_wing = P.style(_wick_proto(-46.0), "static_wick", P.STEEL_DARK)
    for side, tag in ((1, "port"), (-1, "stbd")):
        tip_y = abs(G.wing_tip_xy(G.SWEEP, 1)[1])
        for i, f in enumerate((0.44, 0.57, 0.69, 0.80, 0.89, 0.960)):
            y = G.lerp(G.Y_WING_ROOT, tip_y, f)
            x, z = _wing_te(y)
            items.append((proto_wing,
                          Location((x, side * y, z), (0.0, 0.0, side * -7.0)),
                          f"static_wick_wing:{tag}_{i:02d}"))
    proto_fin = P.style(_wick_proto(64.0), "static_wick_fin", P.STEEL_DARK)
    tip_y = G.Y_FIN + G.FIN_HEIGHT * math.sin(math.radians(G.FIN_CANT))
    tip_z = G.FIN_ROOT_Z + G.FIN_HEIGHT * math.cos(math.radians(G.FIN_CANT))
    tip_te = G.X_FIN_TIP_LE + G.FIN_TIP_CHORD
    for side, tag in ((1, "port"), (-1, "stbd")):
        for i, dx in enumerate((0.0, -340.0)):
            items.append((proto_fin,
                          Location((tip_te + dx, side * tip_y, tip_z),
                                   (0.0, 0.0, side * -5.0)),
                          f"static_wick_fin:{tag}_{i:02d}"))
    return compound_from_instances("static_wicks", items)


# ===========================================================================
# 10.  PANEL LINES AND FASTENERS
# ===========================================================================
#
# Put where the structure is.  Rings at the radome joint and the forward
# avionics bulkhead; a stringer line down each flank; hatch outlines around the
# things that actually open -- avionics bays, the gun bay, the ammunition drum,
# the probe bay, the boarding ladder; and a frame-by-frame ladder across the
# turtledeck.  All of it goes out through SKIN_CUTTERS as one batch.

FLANK_PANELS = (
    # (name,             side, x0,        x1,        z0,        z1)
    ("avionics_fwd",      0,  2.600 * M, 3.520 * M, 0.300 * M, 0.740 * M),
    ("avionics_low",      0,  2.600 * M, 3.300 * M, -0.140 * M, 0.180 * M),
    ("equip_mid",         0,  5.320 * M, 6.060 * M, -0.120 * M, 0.300 * M),
    ("gun_bay",           1,  3.880 * M, 5.060 * M, 0.070 * M, 0.610 * M),
    ("ammo_drum",         1,  5.120 * M, 6.020 * M, 0.360 * M, 0.760 * M),
    ("probe_bay",        -1,  3.040 * M, 4.180 * M, 0.520 * M, 0.870 * M),
    ("ladder_door",       1,  4.360 * M, 5.360 * M, 0.170 * M, 0.520 * M),
    ("avionics_aft",     -1,  4.400 * M, 5.300 * M, 0.560 * M, 0.840 * M),
)

SPINE_FRAMES = (7.560 * M, 8.360 * M, 9.180 * M, 10.180 * M, 11.400 * M,
                12.600 * M, 13.780 * M)
SPINE_HALF = 0.640 * M
SPINE_RAIL = 0.560 * M

BELLY_FRAMES = (7.150 * M, 8.100 * M, 12.900 * M)
BELLY_HALF = 0.860 * M

STRINGER_Z = 0.095 * M
STRINGER_X0, STRINGER_X1 = 2.560 * M, 6.120 * M


def panel_cutters():
    out = []

    def add(shape):
        if shape is not None:
            out.append(shape)

    # rings: radome joint, and the forward equipment bulkhead
    for rx in (G.X_RADOME_AFT, 3.640 * M):
        add(_ring_groove(rx))

    for side in (1, -1):
        smp = flank_sampler(side)
        # the long stringer line down each flank
        add(_scribe(smp, [(x, STRINGER_Z)
                          for x in _lin(STRINGER_X0, STRINGER_X1, 17)]))
        # the cockpit sill / upper longeron line
        add(_scribe(smp, [(x, 0.790 * M)
                          for x in _lin(3.480 * M, 6.100 * M, 13)]))

    for (name, only, x0, x1, z0, z1) in FLANK_PANELS:
        sides = (1, -1) if only == 0 else (only,)
        for side in sides:
            out.extend(_rect_panel(flank_sampler(side), x0, x1, z0, z1))

    # turtledeck frames and the two spine rails
    for fx in SPINE_FRAMES:
        add(_scribe(DECK, [(fx, y) for y in _lin(-SPINE_HALF, SPINE_HALF, 13)]))
    for sgn in (1, -1):
        add(_scribe(DECK, [(x, sgn * SPINE_RAIL)
                           for x in _lin(SPINE_FRAMES[0] - 120.0,
                                         SPINE_FRAMES[-1] + 120.0, 15)]))

    # belly frames
    for fx in BELLY_FRAMES:
        add(_scribe(BELLY, [(fx, y) for y in _lin(-BELLY_HALF, BELLY_HALF, 11)]))

    return out


def fasteners():
    rows = []
    # around the radome joint ring
    x = G.X_RADOME_AFT
    pts = SEC.section_points(x, 40)
    for i, (y, z) in enumerate(pts):
        if i % 2:
            continue
        yy = G.clamp(y, -0.96 * SEC.outer_half_width(x), 0.96 * SEC.outer_half_width(x))
        t, b = SEC.surfaces(x, yy)
        if t is None:
            continue
        smp = DECK if z >= 0.5 * (t + b) else BELLY
        rows.append((smp, [(x - 26.0, yy)]))

    for side in (1, -1):
        smp = flank_sampler(side)
        rows.append((smp, [(sx, STRINGER_Z + 26.0)
                           for sx in _lin(STRINGER_X0, STRINGER_X1, 28)]))
        rows.append((smp, [(sx, 0.790 * M - 26.0)
                           for sx in _lin(3.480 * M, 6.100 * M, 22)]))
        for (_n, only, x0, x1, z0, z1) in FLANK_PANELS:
            if only not in (0, side):
                continue
            n = max(4, int((x1 - x0) / 150.0))
            rows.append((smp, [(sx, z0 - 26.0) for sx in _lin(x0, x1, n)]))
            rows.append((smp, [(sx, z1 + 26.0) for sx in _lin(x0, x1, n)]))
            m = max(3, int((z1 - z0) / 150.0))
            rows.append((smp, [(x0 - 26.0, sz) for sz in _lin(z0, z1, m)]))
            rows.append((smp, [(x1 + 26.0, sz) for sz in _lin(z0, z1, m)]))

    for fx in SPINE_FRAMES:
        rows.append((DECK, [(fx - 26.0, y)
                            for y in _lin(-SPINE_HALF, SPINE_HALF, 9)]))
    for fx in BELLY_FRAMES:
        rows.append((BELLY, [(fx - 26.0, y)
                             for y in _lin(-BELLY_HALF, BELLY_HALF, 9)]))

    proto = P.style(Solid.make_sphere(FASTENER_R), "fastener", P.PANEL_DARK)
    items = []
    for smp, path in rows:
        for loc in _fasteners(smp, path):
            items.append((proto, loc, f"fastener_{len(items):04d}"))
    return compound_from_instances("fasteners", items)


# ===========================================================================
# skin cutters -- collected by airframe.py and applied in ONE subtract
# ===========================================================================


def _build_cutters():
    out = []
    for fn in (panel_cutters, vent_cutters, boarding_cutters):
        try:
            out.extend([c for c in fn() if c is not None])
        except Exception as exc:  # noqa: BLE001
            import sys
            print(f"[details] cutter group {fn.__name__} failed: {exc}",
                  file=sys.stderr)
    return out


SKIN_CUTTERS = _build_cutters()


# ===========================================================================


def build():
    """Return ONE labelled group Compound, already in world position."""
    kids = []
    for fn in (chin_pods, refuel_probe, gun, air_data, aerials, lights, vents,
               boarding):
        kids.extend([k for k in fn() if k is not None])
    kids.append(wicks())
    kids.append(fasteners())
    return stance(group("details", kids))


if __name__ == "__main__":
    import time

    t0 = time.time()
    grp = build()
    print(f"build {time.time() - t0:5.2f}s   children {len(grp.children)}  "
          f"cutters {len(SKIN_CUTTERS)}")
    bb = grp.bounding_box()
    print(f"bbox x {bb.min.X/M:7.3f}..{bb.max.X/M:7.3f}  "
          f"y {bb.min.Y/M:7.3f}..{bb.max.Y/M:7.3f}  "
          f"z {bb.min.Z/M:7.3f}..{bb.max.Z/M:7.3f}")
