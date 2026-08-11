"""Wheels -- 21in front / 22in rear turbine-blade rims and profiled tyres.

Everything is authored in a LOCAL wheel frame whose axis is +Z and whose
outboard direction is +Z, then placed at each corner with a single ``Location``
(``rx = -90 + camber`` on the left, ``+90 - camber`` on the right).  All of the
revolved parts are therefore ordinary ``(radius, axial)`` profiles revolved
about ``Axis.Z``, which is why the tyre can carry a real sidewall section --
bead, rim-protector rib, max-section bulge, shoulder roll, crowned and grooved
tread -- for the price of one profile.

The rim is the design event:

* a machined outer LIP (bright) whose bore is visible for its full depth
  because the spoke face is dished well inboard of the flange -- 36 mm on the
  front, 60 mm on the rear, so the two axles read differently at a glance, with
  a BRONZE pinstripe ring seated in a groove machined into that bore;
* nine TURBINE blades on a chamfered section, pitched 30 deg at the hub down to
  3 deg at the rim, raked back toward the tip, and swept on a ``t**2.15``
  concave curve so the face is a bowl, not a plate;
* a BRONZE centre-lock nut sitting at the bottom of that bowl -- the warm
  jewel on an otherwise cool wheel.

Spokes are placed with ``cadgen.compound_from_instances`` (36 occurrences over
two prototypes) so nine blades per corner cost two lofts, not thirty-six.

The module also owns the ARCH FLARE at each corner -- the haunch that swells
over the tyre, the crease that draws the arch line, and the rolled lip the
wheel tucks under.  It lives here rather than in ``body`` because it is the
wheel-to-body relationship: every one of its sections is solved against the
tyre envelope on one side and ``surfaces``' master section on the other, so it
covers whatever the wheel actually needs covering and dies back into whatever
the flank actually does.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Compound,
    Cylinder,
    FilletPolyline,
    Location,
    Part,
    Plane,
    Polyline,
    RegularPolygon,
    Solid,
    Spline,
    loft,
    make_face,
    revolve,
)


from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_SOLID
from OCP.TopLoc import TopLoc_Location
from build123d.topology.shape_core import downcast

from hypercar_parts import palette as P


# ---------------------------------------------------------------------------
# profile plumbing:  a chain of ("line" | "spline", points) in (radius, axial)
# ---------------------------------------------------------------------------


def _chain_wire(chain):
    """Close a (radius, axial) chain into a planar wire on Plane.XY."""
    edges = []
    for kind, pts in chain:
        edges.append(Spline(*pts) if kind == "spline" else Polyline(*pts))
    first = chain[0][1][0]
    last = chain[-1][1][-1]
    if (abs(first[0] - last[0]) + abs(first[1] - last[1])) > 1e-9:
        edges.append(Polyline(last, first))
    wire = edges[0]
    for e in edges[1:]:
        wire = wire + e
    return wire


def _chain_face(chain):
    """Close a (radius, axial) chain into a face on Plane.XZ.

    Built in local 2D as (u, v) = (radius, axial) then mapped through
    ``Plane.XZ``, which sends (u, v) -> (u, 0, v): exactly the half-plane
    ``revolve(..., Axis.Z)`` wants.
    """
    return Plane.XZ * make_face(_chain_wire(chain))


def _ring(chain):
    return revolve(_chain_face(chain), Axis.Z)


def _loop(pts):
    return [("line", list(pts))]


# ---------------------------------------------------------------------------
# per-axle specification
# ---------------------------------------------------------------------------


class _Spec:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    # -- derived rim datums -------------------------------------------------
    @property
    def SH(self):                       # sidewall height
        return self.R - self.bs

    @property
    def flange_r(self):                 # rim flange outer radius
        return self.bs + 19.0

    @property
    def bore_r(self):                   # inner bore of the barrel = the "lip"
        return self.bs - 6.0

    @property
    def a_out(self):                    # outboard-most rim point (flange tip)
        return self.rim_w / 2.0 + 10.0

    @property
    def a_in(self):                     # inboard flange tip
        return -(self.rim_w / 2.0 + 9.0)

    @property
    def a_face(self):                   # where the spoke face meets the barrel
        return self.a_out - self.lip_depth

    @property
    def a_split(self):                  # bright lip / dark barrel colour break
        return self.a_face + 2.0

    @property
    def a_groove(self):                 # centre of the bronze pinstripe groove
        return self.a_out - 25.0

    @property
    def a_hub(self):                    # spoke face at the centre of the bowl
        return self.a_face - self.concave

    @property
    def half_w(self):                   # tyre max section half width
        return self.W * 0.51

    @property
    def tread_h(self):                  # tread half width
        return self.W * 0.5 * 0.845

    @property
    def max_sect_r(self):               # radius of the tyre's widest point
        return self.bs + 0.55 * self.SH

    @property
    def lip_r(self):                    # arch lip: the visible edge of the arch
        return self.arch_r - self.lip_cut


FRONT = _Spec(
    name="front",
    bs=S.FRONT_RIM_D / 2.0,
    R=S.FRONT_TYRE_R,
    W=S.FRONT_TYRE_W,
    rim_w=250.0,
    lip_depth=46.0,
    concave=52.0,
    n_spokes=9,
    hub_r=86.0,
    blade_r0=60.0,
    chord=(68.0, -47.7, 103.7),     # 68 -> 64 waist -> 124
    thick=(32.0, 10.0),
    twist=(30.0, 3.0),
    rake=30.0,
    camber=1.5,
    # -- arch --------------------------------------------------------------
    hub_x=S.FRONT_AXLE_X,
    hub_y=S.FRONT_HUB_Y,
    hub_z=S.FRONT_HUB_Z,
    arch_r=S.FRONT_ARCH_R,
    lip_cut=6.0,                    # lip pulled in from the body's arch cut
    cover=11.0,                     # body outboard of the tyre's widest point
    p_min=6.0,                      # arch line always stands at least this proud
    p_cap=66.0,
    span=(-25.0, 205.0),
    x_lo=S.BX_DOOR_F + 30.0,
    x_hi=S.BX_FASCIA_F - 26.0,
)

REAR = _Spec(
    name="rear",
    bs=S.REAR_RIM_D / 2.0,
    R=S.REAR_TYRE_R,
    W=S.REAR_TYRE_W,
    rim_w=320.0,
    lip_depth=70.0,
    concave=62.0,
    n_spokes=9,
    hub_r=90.0,
    blade_r0=62.0,
    chord=(74.0, -53.1, 119.1),     # 74 -> 70 waist -> 140
    thick=(35.0, 11.0),
    twist=(28.0, 3.0),
    rake=32.0,
    camber=1.2,
    # -- arch --------------------------------------------------------------
    hub_x=S.REAR_AXLE_X,
    hub_y=S.REAR_HUB_Y,
    hub_z=S.REAR_HUB_Z,
    arch_r=S.REAR_ARCH_R,
    lip_cut=10.0,
    cover=8.0,
    # the rear flank is already at the car's max half-width where it crosses
    # the arch crown, so the rear haunch is won at the SHOULDERS (where the
    # tyre still out-sections the body) and stays a hairline over the top
    p_min=2.0,
    p_cap=44.0,
    span=(-19.0, 199.0),
    x_lo=S.BX_FASCIA_R + 30.0,
    x_hi=S.BX_DOOR_R - 30.0,
)


# ---------------------------------------------------------------------------
# tyre
# ---------------------------------------------------------------------------


def _tyre_sidewall(sp):
    """Carcass: bead -> rim-protector rib -> max section -> shoulder -> tread.

    Radially monotonic from the flange outward, which is what a mounted tyre
    actually does; the axial coordinate is what carries the shape (bulge out
    over the rib, out again to the max section, then tuck back in over the
    shoulder).  The tread band itself is left 3.4 mm undersize -- the separate
    ``_tyre_tread`` ring caps it, so the two rubber tones never share a face.
    """
    bs, R, SH = sp.bs, sp.R, sp.SH
    fr, ao = sp.flange_r, sp.a_out
    hw, th = sp.half_w, sp.tread_h

    bead = (bs - 1.0, ao - 3.0)
    rib = [
        (fr, ao - 3.0),
        (fr + 5.0, ao + 3.5),
        (fr + 10.0, ao + 6.0),          # rim-protector rib crest
        (fr + 16.0, ao + 4.5),
        (fr + 21.0, ao + 2.0),          # groove under the rib
    ]
    wall = [
        rib[-1],
        (bs + 0.42 * SH, hw * 0.988),
        (bs + 0.55 * SH, hw),           # max section width
        (bs + 0.72 * SH, hw * 0.985),
        (bs + 0.85 * SH, hw * 0.944),   # shoulder starts to roll
        (R - 11.0, hw * 0.902),
        (R - 5.0, hw * 0.868),
        (R - 3.4, th + 4.0),
    ]
    up = rib + wall[1:]
    down = [(r, -a) for (r, a) in reversed(up)]

    chain = [
        ("line", [bead, rib[0]]),
        ("spline", rib),
        ("spline", wall),
        ("line", [up[-1], down[0]]),    # flat under the tread cap
        ("spline", [(r, -a) for (r, a) in reversed(wall)]),
        ("spline", [(r, -a) for (r, a) in reversed(rib)]),
        ("line", [(down[-1][0], down[-1][1]), (bead[0], -bead[1]), bead]),
    ]
    return _ring(chain)


_GROOVES = ((0.300, 0.418), (0.612, 0.716))


def _tyre_tread(sp):
    """Crowned tread cap with four moulded circumferential grooves.

    The grooves are cut into the 2-D profile, not booleaned out of a cylinder,
    so they revolve for free and their edges stay razor sharp.
    """
    R, th = sp.R, sp.tread_h + 1.0
    drop, depth, wall = 2.8, 6.5, 0.014

    def crown(u):
        return R - drop * u * u

    keys = [(1.0, 0.0)]
    for g0, g1 in reversed(_GROOVES):
        keys += [(g1 + wall, 0.0), (g1, depth), (g0, depth), (g0 - wall, 0.0)]
    keys.append((0.0, 0.0))

    pts = []
    for i, (u, d) in enumerate(keys):
        if i and keys[i - 1][1] == 0.0 and d == 0.0:
            u0 = keys[i - 1][0]
            for k in range(1, 4):
                uu = u0 + (u - u0) * k / 4.0
                pts.append((crown(uu), uu * th))
        pts.append((crown(u) - d, u * th))

    outer = pts + [(r, -a) for (r, a) in reversed(pts[:-1])]
    chain = [
        ("line", [(R - 9.0, th), outer[0]]),
        ("line", outer),
        ("line", [outer[-1], (R - 9.0, -th), (R - 9.0, th)]),
    ]
    return _ring(chain)


# ---------------------------------------------------------------------------
# rim: machined lip, barrel, hub, centre-lock nut
# ---------------------------------------------------------------------------


def _rim_lip(sp):
    """The bright machined outer lip: flange tip, bore band, pinstripe groove.

    The groove is a 3 mm annular relief part-way down the bore.  It gives the
    lip a highlight line instead of one dead cylindrical band, and it is where
    the bronze pinstripe ring seats.
    """
    bs, fr, br = sp.bs, sp.flange_r, sp.bore_r
    ao, asp, ag = sp.a_out, sp.a_split, sp.a_groove
    return _ring(_loop([
        (br, asp),
        (bs, asp),
        (bs, sp.rim_w / 2.0 - 2.0),
        (bs + 8.0, ao - 11.0),
        (fr, ao - 4.0),
        (fr - 1.2, ao - 0.8),
        (fr - 6.0, ao),                 # flange tip: the bright ring
        (bs + 2.0, ao - 1.2),
        (br + 2.0, ao - 4.0),
        (br, ao - 8.0),
        (br, ag + 6.0),
        (br + 3.0, ag + 4.2),           # pinstripe groove
        (br + 3.0, ag - 4.2),
        (br, ag - 6.0),
    ]))


def _lip_pinstripe(sp):
    """Bronze ring seated in the lip groove -- jewellery that reads at 20 m."""
    br, ag = sp.bore_r, sp.a_groove
    return _ring(_loop([
        (br + 0.4, ag + 5.3),
        (br + 2.9, ag + 3.8),
        (br + 2.9, ag - 3.8),
        (br + 0.4, ag - 5.3),
    ]))


def _rim_barrel(sp):
    """Dark satin barrel: drop centre, inboard flange, spoke landing step."""
    bs, br = sp.bs, sp.bore_r
    af, ai, asp = sp.a_face, sp.a_in, sp.a_split
    return _ring(_loop([
        (br, asp),
        (br - 3.0, af - 6.0),           # step the spokes emerge from
        (br - 3.0, af - 18.0),
        (br - 9.0, af - 30.0),
        (br - 9.0, ai + 16.0),
        (br - 4.0, ai + 7.0),
        (bs - 2.0, ai + 3.0),
        (bs + 7.0, ai),                 # inboard flange tip
        (bs + 16.0, ai + 4.0),
        (bs + 12.0, ai + 11.0),
        (bs, ai + 15.0),
        (bs, asp),
    ]))


def _hub_disc(sp):
    """Machined centre the blades spring from.

    The face is one spline, not a stack of steps: the blade roots are buried
    inside this solid, so any facet here would show up as a false crease
    running under the spokes.
    """
    a0, hr = sp.a_hub, sp.hub_r
    face = [
        (33.0, a0 + 16.0),
        (50.0, a0 + 15.0),
        (68.0, a0 + 13.5),
        (hr - 4.0, a0 + 12.0),          # the blade roots stay under this the
    ]                                   # whole way out, so the edge stays round
    return _ring([
        ("line", [(33.0, a0 - 52.0), face[0]]),
        ("spline", face),
        ("line", [face[-1], (hr, a0 + 4.0), (hr, a0 - 24.0),
                  (hr - 13.0, a0 - 52.0), (33.0, a0 - 52.0)]),
    ])


def _centre_lock(sp):
    """Bronze centre-lock nut -- the single warm accent on the wheel."""
    a0 = sp.a_hub
    ring = Location((0, 0, a0 + 16.0)) * Cylinder(radius=56.0, height=6.0)
    body = loft([
        Plane.XY.offset(a0 + 15.0) * RegularPolygon(50.0, 6),
        Plane.XY.offset(a0 + 32.0) * RegularPolygon(50.0, 6),
        Plane.XY.offset(a0 + 38.0) * RegularPolygon(44.0, 6),
        Plane.XY.offset(a0 + 42.0) * RegularPolygon(34.0, 6),
    ])
    boss = Location((0, 0, a0 + 41.5)) * Cylinder(radius=18.0, height=7.0)
    return ring, body, boss


# ---------------------------------------------------------------------------
# turbine blade
# ---------------------------------------------------------------------------


def _blade_section(chord, thick, flat):
    """Chamfered blade section: a flat outboard face between two facets.

    A plain rounded rectangle gives a spoke one broad highlight and no line; the
    two chamfers give it a pair of crisp highlight lines that run the whole
    length of the blade and die into the machined lip -- a feature line that
    terminates deliberately instead of fading out.  ``flat`` widens toward the
    rim so the blade ends as a broad paddle, not a wedge.
    """
    hc, ht = chord / 2.0, thick / 2.0
    return make_face(FilletPolyline(
        (-hc, -0.10 * thick),           # leading edge
        (-flat * hc, ht),
        (flat * hc, ht),                # outboard flat
        (hc, -0.10 * thick),            # trailing edge
        (min(flat + 0.12, 0.86) * hc, -ht),
        (-min(flat + 0.12, 0.86) * hc, -ht),
        radius=thick * 0.20,
        close=True,
    ))


def _blade(sp):
    """One twisted, concave-swept turbine blade.

    The root is sunk inside the hub disc and the tip inside the barrel wall, so
    neither end cap is ever seen -- the blade appears to grow out of the hub
    and die into the machined lip.
    """
    r0, r1 = sp.blade_r0, sp.bs - 2.0
    a0 = sp.a_hub - 21.0
    a1 = sp.a_face + 5.0
    c0, c1, c2 = sp.chord
    t0, t1 = sp.thick
    w0, w1 = sp.twist

    sections = []
    n = 13
    for i in range(n):
        t = i / (n - 1.0)
        r = r0 + (r1 - r0) * t
        a = a0 + (a1 - a0) * t ** 2.15
        chord = c0 + c1 * t + c2 * t * t
        thick = t0 - t1 * t
        phi = w0 * (1.0 - t) ** 1.25 + w1 * t
        # (phi, 0, rake): the FIRST component turns the section about the
        # plane's normal -- the radial direction -- which is blade pitch.  The
        # third turns it about the wheel axis, which rakes the tip back.
        pl = Plane(origin=(r, 0.0, a), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
        pl = pl.rotated((phi, 0.0, sp.rake * t))
        sections.append(pl * _blade_section(chord, thick, 0.56 + 0.20 * t))
    return loft(sections)


# ---------------------------------------------------------------------------
# arch flare: the haunch, the arch line and the lip
# ---------------------------------------------------------------------------
#
# Before this existed the arch was a plain cylinder punched through the flank:
# no line, no lip, and -- fatally -- the front tyres stood 30..70 mm OUTBOARD
# of the bodywork over most of their length, because the nose sheds half-width
# far faster than the wheel sheds section.  The wheel read as a hole in a blob.
#
# The flare is one lofted band per corner, swept about the wheel axis.  Every
# section is solved, not styled:
#
#   * ``_body_half_y`` samples the SAME section splines ``surfaces`` lofts the
#     master body from, so the band's outer edge tracks the real flank;
#   * ``_tyre_envelope_a`` asks the tyre how wide it actually is at that
#     station, so the lip is pushed out exactly where the wheel needs covering
#     -- a big muscular flare fore and aft of the front wheel, a taut blade
#     over the crown where the fender crest is only 58 mm away, and barely a
#     crease at the rear where the haunch already covers the tyre.
#
# The band's outer edge is deliberately sunk ~5 mm BELOW the body surface and
# its skirt buried 17..33 mm deeper still, so the visible boundary is the
# transversal intersection of the two surfaces: a crisp arch line with no
# coplanar faces to z-fight, that dies into the flank instead of stopping at a
# manufactured step.


_SECTION_STEP = 4.0
_SECTION_CACHE = {}


def _tangent2(a, b):
    dy, dz = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dy, dz) or 1.0
    return (dy / n, dz / n)


def _section_samples(x):
    """Dense (y, z) samples of the master half-section at station ``x``.

    Rebuilds the very splines ``surfaces._mirrored_face`` uses -- same points,
    same end tangents -- so this is the master surface, not a paraphrase of it.
    """
    key = int(round(x / _SECTION_STEP))
    hit = _SECTION_CACHE.get(key)
    if hit is None:
        top, flank, under = S.body_section_bands(key * _SECTION_STEP)
        edges = (
            Spline(*top, tangents=((1, 0), _tangent2(top[-2], top[-1]))),
            Spline(*flank),
            Spline(*under, tangents=(_tangent2(under[0], under[1]), (-1, 0))),
        )
        hit = []
        for e in edges:
            hit.extend((e @ (i / 20.0)) for i in range(21))
        hit = [(p.X, p.Y) for p in hit]
        _SECTION_CACHE[key] = hit
    return hit


def _body_half_y(x, z):
    """Outboard y of the MASTER body surface at (x, z), arch cut ignored."""
    pts = _section_samples(x)
    best = None
    for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
        if (z0 - z) * (z1 - z) <= 0.0 and abs(z1 - z0) > 1e-9:
            y = y0 + (y1 - y0) * (z - z0) / (z1 - z0)
            if best is None or y > best:
                best = y
    return best if best is not None else max(p[0] for p in pts)


def _tyre_wall_a(sp, r):
    """Outboard half-width of the tyre carcass at radius ``r``.

    Mirrors ``_tyre_sidewall``'s control points -- if the tyre section is
    retuned the flare follows it rather than drifting out of step.
    """
    bs, R, SH, hw = sp.bs, sp.R, sp.SH, sp.half_w
    keys = (
        (sp.flange_r + 21.0, sp.a_out + 2.0),
        (bs + 0.42 * SH, hw * 0.988),
        (bs + 0.55 * SH, hw),
        (bs + 0.72 * SH, hw * 0.985),
        (bs + 0.85 * SH, hw * 0.944),
        (R - 11.0, hw * 0.902),
        (R - 5.0, hw * 0.868),
        (R, sp.tread_h + 1.0),
    )
    if r <= keys[0][0]:
        return keys[0][1]
    if r >= keys[-1][0]:
        return 0.0
    for (r0, a0), (r1, a1) in zip(keys, keys[1:]):
        if r0 <= r <= r1:
            return a0 + (a1 - a0) * (r - r0) / (r1 - r0)
    return 0.0


def _tyre_envelope_a(sp, dx):
    """Widest the tyre gets at the station ``dx`` mm fore/aft of the hub.

    The lip at that station always sits ABOVE the tyre's max-section radius, so
    covering this value is exactly what "the body covers the wheel" means.
    """
    if abs(dx) >= sp.R:
        return 0.0
    return _tyre_wall_a(sp, max(abs(dx), sp.max_sect_r))


def _ray_limit(sp, ct, st):
    """How far out the band may run before it fouls the crest, sill or a shut.

    The band's skirt has to stay buried inside the flank; the crest and the
    rocker are where the flank runs out.  Marching the ray is what keeps the
    front band a thin blade at the crown (the fender crest is 58 mm above the
    arch there) and lets it grow to a full haunch at the shoulders.
    """
    r = sp.lip_r
    while r < sp.lip_r + 172.0:
        nr = r + 6.0
        x = sp.hub_x + nr * ct
        z = sp.hub_z + nr * st
        if not (sp.x_lo < x < sp.x_hi):
            break
        if not (S.SILL_Z(x) + 20.0 < z < S.CREST_Z(x) - 16.0):
            break
        r = nr
    return r


def _relax(values, passes):
    """Laplacian smoothing with the ends pinned.

    The coverage demand steps hard where the tyre's shoulder runs out from
    under the arch; relaxing it turns that step into a ramp so the loft reads
    as a swelling instead of a shelf.
    """
    out = list(values)
    for _ in range(passes):
        prev = out[:]
        for i in range(1, len(out) - 1):
            out[i] = 0.25 * prev[i - 1] + 0.5 * prev[i] + 0.25 * prev[i + 1]
    return out


_FLARE_SECTIONS = 29


def _flare_profile(sp, th, b_lip, proud):
    """One (radius, outboard) section of the band, in the wheel's own frame."""
    ct, st = math.cos(th), math.sin(th)
    rl = sp.lip_r

    avail = max(_ray_limit(sp, ct, st) - rl, 54.0)
    skirt = min(max(0.26 * avail, 14.0), 42.0)
    w = max(min(40.0 + 1.30 * proud, avail - skirt), 28.0)
    ro, rs = rl + w, rl + w + skirt

    def body(r):
        return _body_half_y(sp.hub_x + r * ct, sp.hub_z + r * st) - sp.hub_y

    b_o, b_s, b_m = body(ro), body(rs), body(rl + 0.45 * w)

    a_lip = b_lip + proud
    top = a_lip + 2.0 + 0.05 * proud          # crown just outboard of the lip
    drop = top - (b_o - 5.0)
    return [
        ("spline", [
            (rl, a_lip),                      # the arch lip -- the visible edge
            (rl + 0.22 * w, top),             # the fender crowns just off the lip
            (rl + 0.58 * w, top - 0.50 * drop),
            (ro, b_o - 7.0),                  # sunk under the flank: arch line
            (rs, b_s - 17.0),
        ]),
        ("line", [(rs, b_s - 17.0), (rs, b_s - 33.0)]),
        ("line", [(rs, b_s - 33.0),
                  (rl + 0.45 * w, b_m - 30.0),
                  (rl, b_lip - 20.0)]),       # the lip's rolled inner return
        ("line", [(rl, b_lip - 20.0), (rl, a_lip)]),
    ]


def _arch_flare(sp, side):
    """The haunch over one wheel: lofted band, swept about the wheel axis."""
    t0, t1 = sp.span
    thetas = [
        math.radians(t0 + (t1 - t0) * i / (_FLARE_SECTIONS - 1.0))
        for i in range(_FLARE_SECTIONS)
    ]

    b_lip, demand = [], []
    for th in thetas:
        ct, st = math.cos(th), math.sin(th)
        rl = sp.lip_r
        b_lip.append(
            _body_half_y(sp.hub_x + rl * ct, sp.hub_z + rl * st) - sp.hub_y
        )
        env = _tyre_envelope_a(sp, rl * ct)
        demand.append(env + sp.cover if env > 0.0 else -1e6)

    proud = [
        min(max(d - b, sp.p_min), sp.p_cap) for b, d in zip(b_lip, demand)
    ]
    # Both ends are driven UNDER the flank, so the band's last sections are
    # fully submerged and the arch line dies out inside the body instead of
    # stopping at a blunt end cap down by the rocker.
    proud[0] = proud[-1] = -14.0
    proud[1] = proud[-2] = -6.0
    proud = _relax(proud, 7)
    b_lip = _relax(b_lip, 2)

    faces = []
    for th, bl, pr in zip(thetas, b_lip, proud):
        ct, st = math.cos(th), math.sin(th)
        plane = Plane(
            origin=(sp.hub_x, side * sp.hub_y, sp.hub_z),
            x_dir=(ct, 0.0, st),
            z_dir=(-side * st, 0.0, side * ct),
        )
        faces.append(plane * make_face(_chain_wire(_flare_profile(sp, th, bl, pr))))
    return loft(faces)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _wheel_prototype(sp):
    ring, body, boss = _centre_lock(sp)
    kids = [
        style(_tyre_sidewall(sp), f"tyre_wall:{sp.name}", P.TYRE_WALL),
        style(_tyre_tread(sp), f"tyre_tread:{sp.name}", P.TYRE),
        style(_rim_lip(sp), f"rim_lip:{sp.name}", P.RIM),
        style(_lip_pinstripe(sp), f"lip_pinstripe:{sp.name}", P.BRONZE),
        style(_rim_barrel(sp), f"rim_barrel:{sp.name}", P.RIM_DARK),
        style(_hub_disc(sp), f"wheel_hub:{sp.name}", P.STEEL_DARK),
        style(ring, f"centre_lock_ring:{sp.name}", P.BRONZE_DARK),
        style(body, f"centre_lock_nut:{sp.name}", P.BRONZE),
        style(boss, f"centre_lock_boss:{sp.name}", P.BRONZE_DARK),
    ]
    return group(f"wheel_{sp.name}", kids)


def _corners():
    """(spec, corner_label, base Location) for all four wheels."""
    out = []
    for sp, x, y0 in (
        (FRONT, S.FRONT_AXLE_X, S.FRONT_HUB_Y),
        (REAR, S.REAR_AXLE_X, S.REAR_HUB_Y),
    ):
        for side in (1, -1):
            name = f"{sp.name}_{'left' if side > 0 else 'right'}"
            rx = (-90.0 + sp.camber) if side > 0 else (90.0 - sp.camber)
            hub_z = S.FRONT_HUB_Z if sp is FRONT else S.REAR_HUB_Z
            out.append((sp, name, Location((x, side * y0, hub_z), (rx, 0, 0))))
    return out


def _bake(shape):
    """Bake a shape's location into its geometry, leaving an identity location.

    This matters for more than tidiness.  A part positioned by a TopLoc
    location keeps its geometry at the origin and carries the placement ONLY in
    the render package's per-occurrence transform.  The CAD Viewer drops those
    transforms when the STEP parameter module is switched off, which collapses
    all four wheels onto the prototype under the middle of the car -- and since
    the tyres are the only thing touching Z=0, the car then looks like it is
    floating.  Every other part module builds directly in world space, so the
    wheels were the only ones affected.

    Baking makes each wheel real world-space geometry, so it renders the same
    with the module on or off.  The cost is that the four wheels stop sharing a
    content-addressed component and become four unique ones.
    """
    occt = shape.wrapped
    loc = occt.Location()
    if loc.IsIdentity():
        return shape
    transformed = BRepBuilderAPI_Transform(
        occt.Located(TopLoc_Location()), loc.Transformation(), True
    )
    out = downcast(transformed.Shape())
    kind = out.ShapeType()
    if kind == TopAbs_COMPOUND:
        return Compound(out)
    if kind == TopAbs_SOLID:
        return Solid(out)
    return Part(out)


def build():
    """Four independently placed wheels.

    These were originally one ``compound_from_instances`` set: four wheels and
    36 spokes sharing two prototypes, placed by per-occurrence transforms.  That
    is much cheaper to build, but it makes every wheel a shared component whose
    position lives ONLY in the occurrence transform -- and when the viewer
    renders without the STEP module applied, those transforms collapse and all
    four wheels stack on the prototype, which sits flat under the middle of the
    car.  The tyres are also the only thing touching Z=0, so losing them makes
    the whole car look like it is floating.

    Placing each wheel as real, separately located geometry costs build time and
    package size and removes that entire failure mode.
    """
    corner_groups = []
    for sp, name, base in _corners():
        proto = _wheel_prototype(sp)
        kids = []
        for leaf in list(proto.children):
            placed = _bake(base * leaf)
            placed.label = f"{leaf.label.split(':')[0]}:{name}"
            placed.color = leaf.color
            kids.append(placed)
        for k in range(sp.n_spokes):
            spin = Location((0, 0, 0), (0, 0, 360.0 * k / sp.n_spokes))
            blade = _bake((base * spin) * _blade(sp))
            kids.append(style(blade, f"spoke:{name}_{k}", P.ALUMINIUM_DARK))
        corner_groups.append(group(f"wheel:{name}", kids))

    # each flare is unique geometry (it is solved against the flank, which is
    # not fore/aft symmetric), so these are four lofts, not four instances
    flares = []
    for sp in (FRONT, REAR):
        for side in (1, -1):
            name = f"{sp.name}_{'left' if side > 0 else 'right'}"
            flares.append(
                style(_arch_flare(sp, side), f"arch_flare:{name}", P.BODY)
            )

    return group("wheels", corner_groups + flares)
