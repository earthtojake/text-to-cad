"""F-14D variable-sweep OUTER WING PANELS, commanded to 20 degrees.

Everything outboard of the fixed glove: the wing box, the fixed leading-edge
structure, the full-span slats with their tracks and actuator fairings, the
trailing edge flaps with their track fairings, the four upper-surface spoiler
panels, and the wingtip light cluster.  Both sides.

Planform
--------
The panel is defined by exactly three numbers out of ``geometry.py`` -- the tip
position ``G.wing_tip_xy(G.SWEEP, side)``, the seal station ``G.Y_WING_ROOT``
and the sweep -- so the planform cannot drift away from the solved pivot
geometry.  The leading edge is the straight 20 deg line through the tip; chord,
thickness and twist are LINEAR in y between root and tip.

That linearity is load-bearing, not laziness.  Every ordinate of a NACA section
scales linearly with (chord, absolute thickness) once the thickness is carried
in millimetres, so a RULED loft between the root and tip sections passes
exactly through the true section at every intermediate station.  Which means a
spoiler panel lofted between its own two end stations shares its top face with
the wing surface EXACTLY -- the panels sit flush by construction rather than by
tolerance, and no station list has to be kept in sync.

How the control surfaces are made
---------------------------------
The wing is lofted once as a complete aerofoil.  The slats, flaps and spoilers
are then built as their own bodies from the SAME section maths, and the
material they occupy is removed from the panel with cutters grown by the gap
width.  Every gap line is therefore a real gap between two real bodies.  The
three cutter families occupy disjoint chordwise bands (nose / mid-upper /
tail), which is what lets them go into ONE batched multi-tool subtract.

Cutting the whole nose strip off in one piece leaves the gaps BETWEEN slat
segments as holes straight through the wing -- from underneath you see sky.  So
the fixed leading-edge structure is modelled as its own body: the same section
at 48 mm less thickness, shifted aft, running the length of the slat.  It fills
the segment gaps, gives the tracks something to be attached to, and turns the
chordwise slat gap from a slot into a proper shadowed cove.

The root
--------
The glove closes to a knife edge exactly at the seal, so a panel that started
at the seal would hang in space.  The panel root therefore runs a little way
INBOARD of the seal, where the glove slab is at full thickness -- overlapped
and buried, per the "do not butt a lobe against a body" rule, and the glove
module's seal fairing covers the junction.
"""

from __future__ import annotations

import math

from build123d import (Face, Line, Location, Solid, Spline, Vector, Vertex,
                       Wire, loft)

from cadgen import compound_from_instances

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts.context import group, mirror_pair, naca4_points, section_frame
from f14_parts import palette as P

# ---------------------------------------------------------------------------
# planform, solved off geometry.py -- never re-typed
# ---------------------------------------------------------------------------

Y_ROOT = G.Y_WING_ROOT
TIP_X, TIP_Y = G.wing_tip_xy(G.SWEEP, 1)
Y_TIP = TIP_Y
SEMI = Y_TIP - Y_ROOT
TAN_SWEEP = math.tan(math.radians(G.SWEEP))
X_LE_ROOT = TIP_X - SEMI * TAN_SWEEP

# Where the panel's root SECTION actually sits.  Not a round number and not the
# seal: aft of x = 12.1 m the glove edge pulls in toward the nacelle silhouette,
# so by the root trailing edge it has already left the seal line.  Ask the glove
# where its narrowest point along the root chord is and go 110 mm inboard of
# THAT, and the whole root rib is buried in the glove slab at every station
# instead of the trailing corner hanging in clear air.
Y_STUB = min(G.glove_outer_y(X_LE_ROOT + f * 0.05 * G.WING_ROOT_CHORD)
             for f in range(21)) - 110.0

# Chord-line height above the waterline.  The glove mid-surface at the seal is
# the datum; the offset puts the CAMBERED mean line -- not the chord itself --
# on that datum, so the wing root and the glove sheet are one slab.
CAMBER = 0.008
CAMBER_POS = 0.42
Z_CHORD = (G.glove_camber_z(X_LE_ROOT + 0.5 * G.WING_ROOT_CHORD, Y_ROOT)
           - 0.5 * CAMBER * G.WING_ROOT_CHORD)

TWIST_TIP = -1.0               # deg washout at the tip, 0 at the root
SECT_N = 52                    # cosine-spaced chordwise samples per surface
NOSE_K = 6                     # samples wrapped into the leading-edge spline
TE_HALF = 4.0                  # mm: real trailing edges are not knife edges

# chordwise fractions
SLAT_FRAC = G.SLAT_CHORD_FRAC                       # 0.17 -- slat/panel cut
FLAP_FRAC = 1.0 - G.FLAP_CHORD_FRAC                 # 0.72 -- flap hinge line
SPOIL_AFT = FLAP_FRAC - 0.017
SPOIL_FWD = SPOIL_AFT - G.SPOILER_CHORD_FRAC
# Spars are STRAIGHT LINES in plan, not constant chord fractions: at a 3.5:1
# taper a constant fraction converges on the slat gap and the outer wing turns
# into a pile of parallel lines 60 mm apart.
FRONT_SPAR = (0.232, 0.315)
MID_SPAR = (0.468, 0.545)
OUTER_JOINT = (0.620, 0.640)

GAP = 24.0                     # control-surface gap, mm
SPOIL_DEEP = 34.0              # spoiler panel thickness / pocket depth
CORE_INSET = 2.0 * GAP         # LE structure sits this far inside the skin
CORE_SHIFT = 1.6 * GAP         # ... and this far aft of the slat's inner nose

# spanwise runs
SLAT_Y0 = Y_ROOT + 0.021 * SEMI
SLAT_Y1 = Y_TIP - 300.0
FLAP_Y0 = Y_ROOT + 0.024 * SEMI
FLAP_Y1 = Y_ROOT + 0.686 * SEMI
SPOIL_Y0 = Y_ROOT + 0.132 * SEMI
SPOIL_Y1 = Y_ROOT + 0.662 * SEMI
N_SLAT = 4
N_FLAP = 2
N_SPOIL = 4

# wingtip light housing
TIP_CAP = 104.0                # spanwise depth of the tip cap
TIP_BLUNT = 0.84               # thickness scale at the very tip
TIP_LENS_AFT = 0.215           # nav light lens: LE .. 0.215c
TIP_WHITE_FWD = 0.870          # aft-facing white light: 0.870c .. TE

# panel-line grooves: 4 mm deep, 10 mm wide -- see the brief.  Anything
# shallower is sub-pixel; these read because the edge overlay draws them.
GROOVE_D = 4.0
GROOVE_W = 10.0
GROOVE_OUT = 90.0              # cutter overshoot clear of the skin

# fasteners
RIVET_R = 13.0
RIVET_H = 3.6
RIVET_PITCH = 128.0

# --- local paint tones (subtle: control surfaces are the same paint, but they
# are separate panels and must not vanish into the wing) --------------------
WING_GREY = P.GREY_DARK
SLAT_GREY = "#868D94"
FLAP_GREY = "#838A91"
SPOILER_GREY = "#767D84"
CORE_GREY = "#5F666C"          # shadowed slat cove / fixed LE structure
TRACK_GREY = P.ALUM_DARK
FAIRING_GREY = "#8C939A"
RIVET_GREY = "#8A9198"


def _sd(side):
    return "port" if side > 0 else "stbd"


# ---------------------------------------------------------------------------
# spanwise laws -- all linear, which is what makes ruled lofts exact
# ---------------------------------------------------------------------------


def _t(y):
    return (y - Y_ROOT) / SEMI


def _chord(y):
    return G.lerp(G.WING_ROOT_CHORD, G.WING_TIP_CHORD, _t(y))


def _thick(y):
    return G.lerp(G.WING_THICK_ROOT, G.WING_THICK_TIP, _t(y))


def _twist(y):
    return G.lerp(0.0, TWIST_TIP, _t(y))


def _le_x(y):
    return X_LE_ROOT + (y - Y_ROOT) * TAN_SWEEP


def _chord_z(y):
    """Chord-line height.  ``G.WING_DIHEDRAL`` is zero -- the glove carries the
    dihedral -- but the term is written out so the panel follows if it ever
    stops being zero, and it stays linear in y either way."""
    return Z_CHORD + (y - Y_ROOT) * math.tan(math.radians(G.WING_DIHEDRAL))


def _frac(y, f):
    return f * _chord(y)


def _straight(y0, y1, fracs):
    """A structural line that is STRAIGHT in plan: chord fraction ``fracs[0]``
    at ``y0``, ``fracs[1]`` at ``y1``, linear in y in between."""
    u0, u1 = _frac(y0, fracs[0]), _frac(y1, fracs[1])
    return lambda y: u0 + (u1 - u0) * (y - y0) / (y1 - y0)


def _frame(y, side):
    """Section frame at spanwise station y.

    Sweep is ZERO here on purpose: the planform is defined at constant-y
    stations with the chord running aft, so the sections are streamwise.  A
    frame yawed by the sweep would put the root trailing edge 1.5 m inboard of
    its own station, deep inside the fuselage.
    """
    return section_frame((_le_x(y), side * y, _chord_z(y)), 0.0, _twist(y), side)


def _to3d(pts, y, side):
    pl = _frame(y, side)
    origin, chordwise = pl.origin, pl.x_dir
    up = pl.y_dir * (-side)          # (0,0,1) at zero twist, BOTH sides
    return [origin + chordwise * float(u) + up * float(v) for u, v in pts]


def _up_dir(y, side):
    pl = _frame(y, side)
    return pl.y_dir * (-side)


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------


def _airfoil(y, tscale=1.0, tdelta=0.0):
    """(upper, lower) point lists, each LE -> TE, as (chordwise, normal) mm.

    NACA 64A-series-like: a 4-digit thickness form on a low camber line, which
    at 7 % thickness is visually indistinguishable from the real 64A209 mod and
    is exactly linear in (chord, thickness) -- see the module docstring.
    ``tdelta`` shifts the absolute thickness, which keeps that linearity and is
    how the leading-edge structure is inset from the skin.
    """
    chord = _chord(y)
    tfrac = max(_thick(y) * tscale + tdelta, 12.0) / chord
    pts = naca4_points(tfrac, chord, n=SECT_N, camber=CAMBER,
                       camber_pos=CAMBER_POS, sharp_te=True)
    upper = list(pts[:SECT_N])
    lower = [upper[0]] + list(reversed(pts[SECT_N:])) + [(chord, 0.0)]
    out = []
    for surf, sign in ((upper, 1.0), (lower, -1.0)):
        blunt = []
        for u, v in surf:
            f = G.clamp(u / chord, 0.0, 1.0) ** 3
            blunt.append((u, v + sign * TE_HALF * f))
        out.append(blunt)
    return out[0], out[1]


def _v_at(pts, u):
    if u <= pts[0][0]:
        return pts[0][1]
    for i in range(1, len(pts)):
        if pts[i][0] >= u:
            a, b = pts[i - 1], pts[i]
            f = (u - a[0]) / max(b[0] - a[0], 1e-9)
            return a[1] + f * (b[1] - a[1])
    return pts[-1][1]


def _slice(pts, u0=None, u1=None):
    """Chordwise sub-run of a surface, with interpolated end points.

    Cut positions are chord fractions and every ordinate is linear in y, so the
    same samples survive at every station -- which is what keeps a loft
    matching index for index."""
    lo = pts[0][0] if u0 is None else u0
    hi = pts[-1][0] if u1 is None else u1
    out = [(lo, _v_at(pts, lo))]
    out += [p for p in pts if lo + 1e-6 < p[0] < hi - 1e-6]
    out.append((hi, _v_at(pts, hi)))
    return out


def _wire(upper, lower, y, side, nose=True):
    """Closed section wire: a leading-edge spline, two surface splines and the
    blunt trailing edge (or the two cut faces).

    Splines, not polylines: a polyline section makes the ruled loft emit one
    face per chordwise sample, and the edge overlay then draws a hundred
    spanwise lines down the wing."""
    to3 = lambda pts: _to3d(pts, y, side)                          # noqa: E731
    edges = []
    if nose:
        k = NOSE_K
        edges.append(Spline(*to3(list(reversed(lower[:k + 1]))
                                 + upper[1:k + 1])).edge())
        up_tail, lo_tail = upper[k:], lower[k:]
    else:
        a, b = to3([lower[0], upper[0]])
        edges.append(Line(a, b).edge())
        up_tail, lo_tail = upper, lower
    edges.append(Spline(*to3(up_tail)).edge())
    a, b = to3([upper[-1], lower[-1]])
    edges.append(Line(a, b).edge())
    edges.append(Spline(*to3(list(reversed(lo_tail)))).edge())
    return Wire(edges)


def _face(upper, lower, y, side, nose=True):
    return Face(_wire(upper, lower, y, side, nose))


def _panel_face(y, side, u0=None, u1=None, tscale=1.0):
    upper, lower = _airfoil(y, tscale)
    return _face(_slice(upper, u0, u1), _slice(lower, u0, u1), y, side,
                 nose=u0 is None)


# ---------------------------------------------------------------------------
# primitive builders in the section frame
# ---------------------------------------------------------------------------


def _poly_face(y, side, pts):
    p3 = _to3d(pts, y, side)
    edges = [Line(p3[i], p3[(i + 1) % len(p3)]).edge() for i in range(len(p3))]
    return Face(Wire(edges))


def _rect_face(y, side, u0, u1, v0, v1):
    return _poly_face(y, side, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])


def _val(z, y):
    return z(y) if callable(z) else z


def _box_loft(y0, y1, side, u0, u1, v0, v1):
    """A prism between two stations; any bound may be a function of y."""
    def at(y):
        return _rect_face(y, side, _val(u0, y), _val(u1, y),
                          _val(v0, y), _val(v1, y))
    return loft([at(y0), at(y1)], ruled=True)


def _surface_run(y, u0, u1, upper, offset, coarse=0):
    """Surface points from u0 to u1, pushed ``offset`` INTO the material.

    ``coarse`` decimates to about that many samples, ends kept.  A 4 mm groove
    floor does not need thirty points to follow a surface this flat, and the
    boolean that eats thirty of these cutters at once very much does care.
    """
    up, lo = _airfoil(y)
    run = _slice(up if upper else lo, _val(u0, y), _val(u1, y))
    if coarse and len(run) > coarse:
        step = (len(run) - 1) / (coarse - 1.0)
        run = [run[min(int(round(i * step)), len(run) - 1)] for i in range(coarse)]
    sign = -1.0 if upper else 1.0
    return [(u, v + sign * offset) for u, v in run]


def _skin_loft(y0, y1, side, u0, u1, upper, offset, out, coarse=0):
    """A slab under one surface: floor follows the skin, roof clears it."""
    def at(y):
        run = _surface_run(y, u0, u1, upper, offset, coarse)
        sign = 1.0 if upper else -1.0
        return _poly_face(y, side, run + [(run[-1][0], run[-1][1] + sign * out),
                                          (run[0][0], run[0][1] + sign * out)])
    return loft([at(y0), at(y1)], ruled=True)


def _panel_slab(y0, y1, side, u0, u1, upper, depth):
    """A flush panel: top face IS the skin, bottom face ``depth`` below it."""
    def at(y):
        top = _surface_run(y, u0, u1, upper, 0.0)
        bot = _surface_run(y, u0, u1, upper, depth)
        return _poly_face(y, side, top + list(reversed(bot)))
    return loft([at(y0), at(y1)], ruled=True)


def _pod(y, side, f0, f1, drop, half_w, upper=False):
    """A slender teardrop blister riding on the skin.

    Its ellipses are CENTRED on the surface, so the buried half never has to be
    trimmed and the visible half is a clean blister."""
    up, lo = _airfoil(y)
    surf = up if upper else lo
    u0, u1 = _frac(y, f0), _frac(y, f1)
    span = Vector(0.0, float(side), 0.0)
    updir = _up_dir(y, side)
    sign = 1.0 if upper else -1.0
    faces = []
    for s in (0.0, 0.05, 0.16, 0.32, 0.52, 0.72, 0.89, 1.0):
        u = G.lerp(u0, u1, s)
        centre = _to3d([(u, _v_at(surf, u))], y, side)[0]
        shape = math.sin(math.pi * s ** 0.72) ** 0.55
        if s <= 0.0 or s >= 1.0 or shape < 1e-3:
            faces.append(Vertex(centre.X, centre.Y, centre.Z))
            continue
        a, b, m = half_w * shape, drop * shape, 26
        ring = [centre + span * (a * math.cos(2.0 * math.pi * j / m))
                + updir * (sign * b * math.sin(2.0 * math.pi * j / m))
                for j in range(m)]
        faces.append(Face(Wire([Line(ring[j], ring[(j + 1) % m]).edge()
                                for j in range(m)])))
    return loft(faces, ruled=False)


# ---------------------------------------------------------------------------
# panel lines
# ---------------------------------------------------------------------------


def _groove_span(side, line, y0, y1, upper):
    """A spanwise scribe line following a straight structural line in plan."""
    def at(y):
        u = _val(line, y)
        v = _v_at(_airfoil(y)[0 if upper else 1], u)
        v0, v1 = ((v - GROOVE_D, v + GROOVE_OUT) if upper
                  else (v - GROOVE_OUT, v + GROOVE_D))
        return _rect_face(y, side, u - 0.5 * GROOVE_W, u + 0.5 * GROOVE_W, v0, v1)
    return loft([at(y0), at(y1)], ruled=True)


def _groove_chord(side, y, u0, u1, upper):
    """A chordwise scribe line -- a rib or a frame."""
    return _skin_loft(y - 0.5 * GROOVE_W, y + 0.5 * GROOVE_W, side,
                      u0, u1, upper, GROOVE_D, GROOVE_OUT, coarse=6)


def _access_panel(side, y0, y1, f0, f1, upper):
    a, b = _straight(y0, y1, (f0, f0)), _straight(y0, y1, (f1, f1))
    return [_groove_span(side, a, y0, y1, upper),
            _groove_span(side, b, y0, y1, upper),
            _groove_chord(side, y0, a(y0), b(y0), upper),
            _groove_chord(side, y1, a(y1), b(y1), upper)]


def _grid(side):
    """(spar lines, rib lines, access doors) -- three disjoint cut batches."""
    y_in, y_out = Y_ROOT + 120.0, SLAT_Y1 - 40.0
    fwd = _straight(y_in, y_out, FRONT_SPAR)
    mid = _straight(y_in, y_out, MID_SPAR)
    joint = _straight(y_in, y_out, OUTER_JOINT)
    rear = _straight(y_in, y_out, (FLAP_FRAC, FLAP_FRAC))

    spars = [_groove_span(side, fwd, y_in, y_out, True),
             _groove_span(side, fwd, y_in, y_out, False),
             _groove_span(side, mid, y_in, y_out, True),
             _groove_span(side, mid, y_in, y_out, False),
             # the outer skin joint only exists where the spoilers are not
             _groove_span(side, joint, SPOIL_Y1 + 110.0, y_out, True),
             _groove_span(side, joint, y_in, y_out, False)]
    for upper in (True, False):
        # the rear spar only shows outboard of the flap, where no hinge line
        # has already drawn it
        spars.append(_groove_span(side, rear, FLAP_Y1 + 110.0, y_out, upper))

    ribs = []
    for i in range(8):
        y = G.lerp(Y_ROOT + 660.0, SLAT_Y1 - 320.0, i / 7.0)
        ribs.append(_groove_chord(side, y, fwd(y), _frac(y, SPOIL_FWD) - 24.0,
                                  True))
        ribs.append(_groove_chord(side, y, fwd(y), rear(y), False))

    doors = []
    for y0, y1, f0, f1 in ((Y_ROOT + 0.10 * SEMI, Y_ROOT + 0.235 * SEMI, 0.30, 0.44),
                           (Y_ROOT + 0.30 * SEMI, Y_ROOT + 0.425 * SEMI, 0.30, 0.44),
                           (Y_ROOT + 0.50 * SEMI, Y_ROOT + 0.605 * SEMI, 0.29, 0.43)):
        doors += _access_panel(side, y0, y1, f0, f1, False)
    return spars, ribs, doors


def _rivets(side):
    """Additive fastener domes -- never boolean cuts, per the brief."""
    proto = Solid.make_sphere(RIVET_R)
    P.style(proto, "wing_fastener", RIVET_GREY)
    y_in, y_out = Y_ROOT + 180.0, SLAT_Y1 - 120.0
    fwd = _straight(y_in, y_out, FRONT_SPAR)
    rear = _straight(y_in, y_out, (FLAP_FRAC, FLAP_FRAC))
    inst, n = [], 0
    for line, off, upper in ((fwd, 34.0, True), (fwd, 34.0, False),
                             (rear, -34.0, False)):
        y = y_in
        while y < y_out:
            u = line(y) + off
            v = _v_at(_airfoil(y)[0 if upper else 1], u)
            pos = (_to3d([(u, v)], y, side)[0]
                   + _up_dir(y, side) * ((-1.0 if upper else 1.0)
                                         * (RIVET_R - RIVET_H)))
            n += 1
            inst.append((proto, Location((pos.X, pos.Y, pos.Z)),
                         f"fastener_{n:03d}"))
            y += RIVET_PITCH
    out = compound_from_instances(f"wing_fasteners_{_sd(side)}", inst)
    # Also colour the compound itself: the occurrence-metadata tree does not
    # survive the stance transform, and without this the domes fall back to the
    # renderer's default grey.
    return P.style(out, f"wing_fasteners:{_sd(side)}", RIVET_GREY)


# ---------------------------------------------------------------------------
# assemblies
# ---------------------------------------------------------------------------


def _segments(y0, y1, count, gap):
    """``count`` spanwise bands inside [y0, y1] separated by ``gap``."""
    width = (y1 - y0 - gap * (count - 1)) / count
    return [(y0 + i * (width + gap), y0 + i * (width + gap) + width)
            for i in range(count)]


def _slats(side):
    out = []
    for i, (ya, yb) in enumerate(_segments(SLAT_Y0, SLAT_Y1, N_SLAT, GAP), 1):
        body = loft([_panel_face(ya, side, u1=_frac(ya, SLAT_FRAC)),
                     _panel_face(yb, side, u1=_frac(yb, SLAT_FRAC))], ruled=True)
        out.append(P.style(body, f"wing_slat:{_sd(side)}_{i}", SLAT_GREY))
    return out


def _le_structure(side):
    """The fixed leading-edge box the slats retract onto.

    Same section, 48 mm thinner and 38 mm further aft, so it stands a uniform
    gap inside the slat skin.  This is what stops the slat segment gaps being
    holes clean through the wing."""
    def at(y):
        upper, lower = _airfoil(y, tdelta=-CORE_INSET)
        cut = _frac(y, SLAT_FRAC) + GAP + 70.0 - CORE_SHIFT
        shift = lambda pts: [(u + CORE_SHIFT, v)                   # noqa: E731
                             for u, v in _slice(pts, None, cut)]
        return _face(shift(upper), shift(lower), y, side)
    return P.style(loft([at(SLAT_Y0 - GAP), at(SLAT_Y1 + GAP)], ruled=True),
                   f"wing_le_structure:{_sd(side)}", CORE_GREY)


def _slat_tracks(side):
    """The rails that show in the slat gaps, plus their underwing fairings.

    Each rail is 90 mm wide but the gap is only 24 mm: the rest is buried in
    the slats either side and in the leading-edge box behind, so the track is
    anchored at both ends and only the part inside the slot is on show."""
    out = []
    bounds = _segments(SLAT_Y0, SLAT_Y1, N_SLAT, GAP)
    stations = [SLAT_Y0 - 0.5 * GAP]
    stations += [0.5 * (bounds[i][1] + bounds[i + 1][0]) for i in range(N_SLAT - 1)]
    stations.append(SLAT_Y1 + 0.5 * GAP)
    for i, y in enumerate(stations, 1):
        rail = _box_loft(
            y - 45.0, y + 45.0, side,
            lambda yy: _frac(yy, SLAT_FRAC) - 0.070 * _chord(yy),
            lambda yy: _frac(yy, SLAT_FRAC) + 0.055 * _chord(yy),
            lambda yy: _v_at(_airfoil(yy)[1], _frac(yy, SLAT_FRAC)) + 14.0,
            lambda yy: 0.14 * _thick(yy))
        out.append(P.style(rail, f"slat_track:{_sd(side)}_{i}", TRACK_GREY))
    for i, (ya, yb) in enumerate(bounds, 1):
        yc = 0.5 * (ya + yb)
        thick = _thick(yc)
        out.append(P.style(
            _pod(yc, side, 0.035, 0.240, 0.155 * thick, 0.235 * thick),
            f"slat_actuator_fairing:{_sd(side)}_{i}", FAIRING_GREY))
    return out


def _flaps(side):
    out = []
    for i, (ya, yb) in enumerate(_segments(FLAP_Y0, FLAP_Y1, N_FLAP, GAP), 1):
        body = loft([_panel_face(ya, side, u0=_frac(ya, FLAP_FRAC)),
                     _panel_face(yb, side, u0=_frac(yb, FLAP_FRAC))], ruled=True)
        out.append(P.style(body, f"wing_flap:{_sd(side)}_{i}", FLAP_GREY))
    return out


def _flap_fairings(side):
    out = []
    for i in range(3):
        y = G.lerp(FLAP_Y0 + 0.15 * (FLAP_Y1 - FLAP_Y0),
                   FLAP_Y1 - 0.12 * (FLAP_Y1 - FLAP_Y0), i / 2.0)
        thick = _thick(y)
        out.append(P.style(
            _pod(y, side, 0.480, 0.845, 0.34 * thick, 0.40 * thick),
            f"flap_track_fairing:{_sd(side)}_{i + 1}", FAIRING_GREY))
    return out


def _spoilers(side):
    out = []
    for i, (ya, yb) in enumerate(_segments(SPOIL_Y0, SPOIL_Y1, N_SPOIL, GAP), 1):
        body = _panel_slab(ya, yb, side,
                           lambda yy: _frac(yy, SPOIL_FWD),
                           lambda yy: _frac(yy, SPOIL_AFT), True, SPOIL_DEEP)
        out.append(P.style(body, f"wing_spoiler:{_sd(side)}_{i}", SPOILER_GREY))
    return out


def _tip_cluster(side):
    """Tip cap split chordwise into nav light, housing and white aft light."""
    y0, y1 = Y_TIP - TIP_CAP, Y_TIP
    nav = P.LIGHT_RED if side > 0 else P.LIGHT_GREEN
    out = []
    for name, f0, f1, hexcol in (
            ("wingtip_navlight", None, TIP_LENS_AFT, nav),
            ("wingtip_housing", TIP_LENS_AFT, TIP_WHITE_FWD, WING_GREY),
            ("wingtip_taillight", TIP_WHITE_FWD, None, P.LIGHT_WHITE)):
        cut = lambda y, f: None if f is None else _frac(y, f)       # noqa: E731
        body = loft([_panel_face(y0, side, cut(y0, f0), cut(y0, f1)),
                     _panel_face(y1, side, cut(y1, f0), cut(y1, f1),
                                 tscale=TIP_BLUNT)], ruled=True)
        out.append(P.style(body, f"{name}:{_sd(side)}", hexcol))
    return out


# ---------------------------------------------------------------------------
# the panel itself
# ---------------------------------------------------------------------------


def _panel(side):
    y_cap = Y_TIP - TIP_CAP
    full = loft([_panel_face(Y_STUB, side), _panel_face(y_cap, side)], ruled=True)

    big = 900.0
    # The nose comes off in one piece over the whole slat run; the leading-edge
    # box behind it keeps the segment gaps from being through-holes.
    cutters = [_box_loft(SLAT_Y0 - GAP, SLAT_Y1 + GAP, side, -big,
                         lambda yy: _frac(yy, SLAT_FRAC) + GAP, -big, big)]
    # The flap pockets, by contrast, are cut segment by segment, so the strip
    # of wing between the two flaps stays flush instead of becoming a slot.
    for ya, yb in _segments(FLAP_Y0, FLAP_Y1, N_FLAP, GAP):
        cutters.append(_box_loft(ya, yb, side,
                                 lambda yy: _frac(yy, FLAP_FRAC) - GAP,
                                 lambda yy: _chord(yy) + big, -big, big))
    for ya, yb in _segments(SPOIL_Y0, SPOIL_Y1, N_SPOIL, GAP):
        # 8 mm deeper than the panel so the reveal reads as a shadow gap
        # instead of two coincident faces fighting for the same pixels
        cutters.append(_skin_loft(
            ya - GAP, yb + GAP, side,
            lambda yy: _frac(yy, SPOIL_FWD) - 16.0,
            lambda yy: _frac(yy, SPOIL_AFT) + 16.0,
            True, SPOIL_DEEP + 8.0, GROOVE_OUT))

    spars, ribs, doors = _grid(side)
    # Batched multi-tool subtracts, one per family, each internally disjoint:
    # the control-surface cutters occupy disjoint chordwise bands, the spar
    # lines disjoint chord fractions, the ribs disjoint stations.
    panel = full - cutters
    panel = panel - spars
    panel = panel - ribs
    panel = panel - doors
    return panel


def _wing(side):
    kids = [P.style(_panel(side), f"wing_panel:{_sd(side)}", WING_GREY),
            _le_structure(side)]
    kids += _slats(side)
    kids += _slat_tracks(side)
    kids += _flaps(side)
    kids += _flap_fairings(side)
    kids += _spoilers(side)
    kids += _tip_cluster(side)
    kids.append(_rivets(side))
    return group(f"wing_{_sd(side)}", kids)


def build():
    """The pair of outer wing panels, in world position on the stance."""
    return stance(group("wings", mirror_pair(_wing, "wing")))


def seal_report():
    """How the root rib sits against the glove, station by station.

    The root is meant to be BURIED, so the numbers to watch are: the glove
    edge must stay outboard of the root rib at every station along the root
    chord, and the section must not stand proud of the skin by more than the
    glove's own seal fairing can cover.
    """
    lines = [f"root rib at y={Y_STUB:.1f} mm  (seal is at {Y_ROOT:.1f})"]
    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = X_LE_ROOT + f * G.WING_ROOT_CHORD
        lines.append(f"  {f*100:5.1f}% chord  x={x/G.M:6.3f} m   "
                     f"glove edge y={G.glove_outer_y(x):7.1f}  "
                     f"clear of rib by {G.glove_outer_y(x) - Y_STUB:6.1f} mm")
    worst_t = worst_b = 0.0
    for y in (Y_STUB, 0.5 * (Y_STUB + Y_ROOT)):
        up, lo = _airfoil(y)
        for i in range(1, 20):
            u = i / 20.0 * _chord(y)
            top, bot = SEC.surfaces(_le_x(y) + u, y)
            if top is None:
                continue
            worst_t = max(worst_t, _chord_z(y) + _v_at(up, u) - top)
            worst_b = max(worst_b, bot - (_chord_z(y) + _v_at(lo, u)))
    lines.append(f"  root section stands proud of the skin by "
                 f"{worst_t:.1f} mm on top, {worst_b:.1f} mm underneath")
    return "\n".join(lines)


if __name__ == "__main__":
    import time

    t0 = time.time()
    shape = build()
    bb = shape.bounding_box()
    print(f"build {time.time() - t0:6.2f}s")
    print(f"root LE x={X_LE_ROOT / G.M:.3f} m  TE x="
          f"{(X_LE_ROOT + G.WING_ROOT_CHORD) / G.M:.3f} m")
    print(f"tip  LE x={TIP_X / G.M:.3f} m  y={Y_TIP / G.M:.3f} m  "
          f"span {2 * Y_TIP / G.M:.3f} m")
    print(f"bbox x {bb.min.X / G.M:7.3f}..{bb.max.X / G.M:7.3f}  "
          f"y {bb.min.Y / G.M:7.3f}..{bb.max.Y / G.M:7.3f}  "
          f"z {bb.min.Z / G.M:7.3f}..{bb.max.Z / G.M:7.3f}")
    print(seal_report())
