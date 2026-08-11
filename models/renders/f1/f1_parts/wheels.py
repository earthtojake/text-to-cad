"""Corners: slick tyres, rims, aero wheel covers, wheel nuts, carbon brake
discs, six-pot calipers, brake ducts, uprights and hubs.

Everything is modelled in a LOCAL WHEEL FRAME whose origin is the axle centre
and whose axes are parallel to the car's: +X forward, +Y outboard, +Z up. One
`Pos()` at the end drops the corner onto its car-coordinate hub, so a corner
stays a single rigid child that the steering animation can rotate about the
front ball-joint axis — upright, hub, brake, duct and wheel all turn together
because they are one child, and the wishbones do not, because their outboard
ends sit exactly on that axis.

The LEFT corner is modelled and the right corner is its y-mirror, which is
what guarantees a ball-joint eye lands exactly on the mirrored hardpoint.
Every eye centre in here is `spec`'s hardpoint minus the hub origin — no
number in this file re-states a suspension coordinate.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Cylinder,
    Line,
    Plane,
    Pos,
    Rot,
    Sphere,
    Spline,
    Vector,
    loft,
    make_face,
    revolve,
)

from . import lib, spec

# ==========================================================================
# wheel-frame constants — the family every corner is cut from
# ==========================================================================

BEAD_R = spec.RIM_DIAMETER / 2.0  # 228.6 — nominal rim / bead-seat radius
FLANGE_R = 245.0  # rim flange lip
DROP_R = 208.0  # barrel drop centre
BARREL_IN_R = 200.0  # barrel bore at the drop centre
MAXW_R = 300.0  # radius of maximum tyre section width
SHOULDER_R = 338.0  # tread / sidewall material break
TREAD_R = spec.TIRE_R  # 360

RIM_HW = {"f": 137.0, "r": 183.0}  # half rim width
DISC_R = {"f": 165.0, "r": 140.0}  # 330 / 280 mm brake discs
DISC_T = {"f": 27.0, "r": 24.0}
DISC_Y = -26.5  # brake-disc mid plane, just inboard of the wheel centre
CAL_PHI = {"f": 34.0, "r": 146.0}  # caliper clock: front ahead, rear behind

COVER_R = 243.0  # wheel-cover outer radius
RING_R0, RING_R1 = 207.0, 219.0  # THE accent ring — identical on all corners
RING_DEPTH = 1.8  # the ring is inlaid flush, not cut through the cover
N_SPOKE = 5
N_FLUTE = 13  # cover flutes — BLIND, milled into the face, never through it
FLUTE_DEPTH = 3.0  # milled depth; the cover's thinnest fluted station is 5.0
FLUTE_TOOL_H = 44.0  # axial height of the flute cutter (all of it outboard)
N_DRILL = 48  # brake-disc cooling drillings per row

EYE_R = 15.0  # ball-joint eye housing radius
EYE_L = 34.0  # ball-joint eye housing length


def _sidewall_y(r: float, hw: float, bh: float) -> float:
    """Half-width of the tyre's outer surface at radius r, bead -> max width."""
    t = (r - BEAD_R) / (MAXW_R - BEAD_R)
    t = min(max(t, 0.0), 1.0)
    return bh + (hw - bh) * t**0.55


def _band(r: float) -> float:
    """Two shallow concentric relief ridges moulded into the sidewall."""
    out = 0.0
    for r0, half, amp in ((252.0, 10.0, 3.2), (276.0, 9.0, 2.6)):
        d = abs(r - r0)
        if d < half:
            out += amp * 0.5 * (1.0 + math.cos(math.pi * d / half))
    return out


# ==========================================================================
# construction helpers — profiles are written as (axial y, radius) pairs
# ==========================================================================

_PROFILE_PLANE = Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))


def _rev(segments, arc: float = 360.0):
    """Revolve a closed (y, r) profile about the axle.

    Each segment is a point list: two points make a line, more make a spline.
    Consecutive segments must share their endpoints exactly.
    """
    curves = []
    for seg in segments:
        curves.append(Line(seg[0], seg[1]) if len(seg) == 2 else Spline(*seg))
    wire = curves[0]
    for c in curves[1:]:
        wire = wire + c
    return revolve(_PROFILE_PLANE * make_face(wire), Axis.Y, arc)


def _poly(pts):
    """Closed polyline profile — crisp machined steps, no spline rounding."""
    loop = list(pts) + [pts[0]]
    return [[loop[i], loop[i + 1]] for i in range(len(pts))]


def _ring(y0: float, y1: float, r0: float, r1: float, arc: float = 360.0):
    """Revolved rectangle — grooves, slabs and knives."""
    return _rev(
        [
            [(y0, r0), (y0, r1)],
            [(y0, r1), (y1, r1)],
            [(y1, r1), (y1, r0)],
            [(y1, r0), (y0, r0)],
        ],
        arc=arc,
    )


def _spin(shape, angle_deg: float):
    """Rotate about the axle (the local Y axis)."""
    return Rot(0.0, angle_deg, 0.0) * shape


def _polar(radius: float, phi_deg: float, y: float = 0.0):
    """Wheel-frame point at azimuth phi (0 = forward, 90 = up)."""
    a = math.radians(phi_deg)
    return (radius * math.cos(a), y, radius * math.sin(a))


def _radial(phi_deg: float):
    a = math.radians(phi_deg)
    return (math.cos(a), 0.0, math.sin(a))


def _tangent(phi_deg: float):
    a = math.radians(phi_deg)
    return (-math.sin(a), 0.0, math.cos(a))


def _cyl(radius: float, length: float, center, axis):
    d = Vector(axis).normalized()
    return Plane(origin=Vector(center), z_dir=d) * Cylinder(radius, length)


def _vol(s) -> float:
    try:
        return float(s.volume)
    except Exception:
        return 0.0


def _defrag(shape, min_frac: float = 0.01):
    """Drop the crumbs a blind pocket leaves behind.

    Milling a groove into a curved panel reliably shaves off a lens of material
    a few hundredths of a millimetre thick and leaves it floating as its own
    solid — 0.008% of the body's volume, invisible, and enormously expensive:
    every one of them is a separate shell the tessellator has to mesh, and they
    are the reason one body in this module was exporting a 190 MB GLB. Keep
    only the solids that are actually part of the part.
    """
    shape = lib.as_body(shape)
    try:
        solids = shape.solids()
    except Exception:
        return shape
    if len(solids) < 2:
        return shape
    biggest = max(s.volume for s in solids)
    keep = [s for s in solids if s.volume >= min_frac * biggest]
    if not keep or len(keep) == len(solids):
        return shape
    return lib.as_body(keep)


def _cut(base, tools):
    """Subtract a list of tools, keeping the body if a boolean collapses.

    Every result goes through `lib.repair` and `_defrag`: a blind pocket milled
    into a lofted or revolved surface routinely leaves one hair-wide face or a
    floating crumb that OCC still calls a solid, and those are what later
    booleans — and the tessellator — choke on.
    """
    if not isinstance(tools, (list, tuple)):
        tools = [tools]
    try:
        out = _defrag(lib.repair(base - list(tools)))
        if out is not None and _vol(out) > 1e-6:
            return out
    except Exception:
        pass
    for t in tools:
        try:
            out = _defrag(lib.repair(base - t))
        except Exception:
            continue
        if out is not None and _vol(out) > 1e-6:
            base = out
    return base


def _loft(sections, margin: float = 12.0):
    """Loft a section stack, rejecting a smooth loft that leaves its sections.

    build123d's smooth loft through a stack of small, closely spaced faces can
    return a perfectly VALID solid that bulges hundreds of millimetres away
    from every section it was built from. It is the nastiest failure in this
    module because nothing downstream complains: the body is a solid, it is
    watertight, it has positive volume — it is just not the shape that was
    drawn. The cover's flute cutter did exactly this, and because the excursion
    is numerically sensitive to the absolute Y of the sections it did it
    DIFFERENTLY on the front rim (half-width 137) and the rear (183), which is
    how two corners ended up wearing a different wheel face from the other two.

    So: build the smooth loft, then check it against the bounding box of its
    own sections. A smooth loft is allowed to bow `margin` outside them. If it
    bows further it is discarded for the ruled loft through the same sections,
    which is duller and always honest.
    """
    faces = [f for f in sections if f is not None]
    boxes = [lib.bbox(f) for f in faces]
    lo = [min(b[0][i] for b in boxes) - margin for i in range(3)]
    hi = [max(b[1][i] for b in boxes) + margin for i in range(3)]
    try:
        out = loft(faces, ruled=False)
        if out is not None and out.is_valid and out.volume > 0:
            blo, bhi = lib.bbox(out)
            if all(blo[i] >= lo[i] and bhi[i] <= hi[i] for i in range(3)):
                return out
    except Exception:
        pass
    return lib.loft_solid(faces, ruled=True)


def _lofted(sections):
    """Loft superellipse sections given as (origin, x_dir, z_dir, hw, hh, n)."""
    faces = []
    for origin, x_dir, z_dir, hw, hh, n in sections:
        plane = Plane(origin=Vector(origin), x_dir=Vector(x_dir), z_dir=Vector(z_dir))
        pts = lib.superellipse_pts(hw, hh, n, n, samples=26)
        faces.append(plane * make_face(Spline(*pts, periodic=True)))
    return _loft(faces)


def _limb(p0, p1, law, thin=(1, 0, 0)):
    """Organic tapered strut from p0 to p1.

    `law` is [(t, half-width, half-thickness, exponent)]; `thin` names the
    direction the half-thickness is measured along. This is how every load
    path in the upright is drawn: fat at the bearing root, waisted mid-span,
    slim at the joint.
    """
    a, b = Vector(p0), Vector(p1)
    ax = (b - a).normalized()
    td = Vector(thin)
    td = (td - ax * td.dot(ax)).normalized()
    wd = td.cross(ax)
    return _lofted(
        [(a + (b - a) * t, wd, ax, hw, ht, n) for t, hw, ht, n in law]
    )


def _pin_axis(p_in, p_out):
    """Pin direction of a joint on a `lib.blade_*` member.

    Reproduces `lib.blade_face`'s frame so the eye's bore lines up with the
    thin axis of the wishbone that lands on it, and the suspension module's
    clevis straddles a boss it actually fits.
    """
    n = (Vector(p_out) - Vector(p_in)).normalized()
    ref = Vector(lib.FLOW)
    if abs(ref.dot(n)) > 0.97:
        ref = Vector(0, 0, 1)
        if abs(ref.dot(n)) > 0.97:
            ref = Vector(0, 1, 0)
    x_dir = (ref - n * ref.dot(n)).normalized()
    return n.cross(x_dir)


# ==========================================================================
# 1 — SLICK TYRE: revolved sculpted profile, hollow casing, tread/sidewall
#     split on one exact cylinder so the two rubbers share a face
# ==========================================================================


def _tyre_outer(hw: float, bh: float):
    pts = []
    r = BEAD_R
    while r < MAXW_R - 0.01:
        pts.append((-(_sidewall_y(r, hw, bh) + _band(r)), r))
        r += 2.5
    pts += [
        (-(hw - 0.35), 294.0),
        (-(hw - 0.30), MAXW_R),
        (-(hw - 0.35), 306.0),
        (-(hw - 0.9), 314.0),
        (-(hw - 2.4), 326.0),
        (-(hw - 6.2), 337.0),
        (-(hw - 13.0), 347.0),
        (-(hw - 24.0), 354.4),
        (-(hw - 41.0), 358.4),
        (-(hw - 64.0), 359.72),
        (-0.42 * hw, 359.93),
        (-0.20 * hw, 359.98),
        (0.0, TREAD_R),
    ]
    return pts + [(-y, rr) for (y, rr) in reversed(pts[:-1])]


def _tyre_cavity(hw: float, bh: float):
    def sw(r):
        return _sidewall_y(r, hw, bh)

    pts = [
        (bh, 244.0),
        (sw(254.0) - 5.0, 254.0),
        (sw(270.0) - 6.5, 270.0),
        (sw(286.0) - 8.0, 286.0),
        (hw - 9.5, 300.0),
        (hw - 11.5, 315.0),
        (hw - 16.0, 328.0),
        (hw - 25.0, 337.0),
        (hw - 40.0, 342.0),
        (hw - 64.0, 344.0),
        (0.34 * hw, 344.6),
        (0.0, 344.8),
    ]
    return pts + [(-y, r) for (y, r) in reversed(pts[:-1])]


def _tyre(hw: float, bh: float):
    casing = _rev(
        [
            _tyre_outer(hw, bh),
            [(bh, BEAD_R), (bh, 244.0)],
            _tyre_cavity(hw, bh),
            [(-bh, 244.0), (-bh, BEAD_R)],
        ]
    )
    knife = _cyl(SHOULDER_R, 2.2 * hw + 60.0, (0, 0, 0), (0, 1, 0))
    return casing - knife, casing & knife


# ==========================================================================
# 2 — RIM: barrel with real flanges and a drop centre, five sculpted spokes
# ==========================================================================

_RIM_OUTER = (
    (-1.000, FLANGE_R),
    (-0.968, FLANGE_R),
    (-0.936, 235.0),
    (-0.906, BEAD_R),
    (-0.780, BEAD_R),
    (-0.640, 216.0),
    (-0.470, DROP_R),
    (0.120, DROP_R),
    (0.320, 212.0),
    (0.530, 220.0),
    (0.700, 226.5),
    (0.800, BEAD_R),
    (0.906, BEAD_R),
    (0.936, 235.0),
    (0.968, FLANGE_R),
    (1.000, FLANGE_R),
)

_RIM_INNER = (
    (1.000, 237.0),
    (0.958, 223.5),
    (0.880, 220.6),
    (0.700, 218.0),
    (0.530, 212.0),
    (0.320, 204.0),
    (0.120, BARREL_IN_R),
    (-0.470, BARREL_IN_R),
    (-0.640, 208.0),
    (-0.780, 220.6),
    (-0.880, 220.6),
    (-0.958, 223.5),
    (-1.000, 237.0),
)

# spoke: radius, tangential width, axial thickness, aero twist (deg)
_SPOKE_LAW = (
    (44.0, 98.0, 42.0, 0.0),
    (78.0, 80.0, 33.0, 5.0),
    (112.0, 64.0, 25.0, 12.0),
    (146.0, 56.0, 20.5, 20.0),
    (178.0, 58.0, 17.5, 26.0),
    (211.0, 72.0, 15.0, 29.0),
)


def _rim(bh: float, clearances):
    part = _rev(
        [
            [(f * bh, r) for f, r in _RIM_OUTER],
            [(bh, FLANGE_R), (bh, 237.0)],
            [(f * bh, r) for f, r in _RIM_INNER],
            [(-bh, 237.0), (-bh, FLANGE_R)],
        ]
    )
    y_face = 0.30 * bh
    part = part + _rev(
        [
            [(y_face - 28.0, 30.0), (y_face - 28.0, 52.0)],
            [
                (y_face - 28.0, 52.0),
                (y_face - 12.0, 64.0),
                (y_face + 16.0, 66.0),
                (y_face + 26.0, 58.0),
            ],
            [(y_face + 26.0, 58.0), (y_face + 26.0, 30.0)],
            [(y_face + 26.0, 30.0), (y_face - 28.0, 30.0)],
        ]
    )
    faces = []
    for rad, wide, thick, twist in _SPOKE_LAW:
        plane = lib.plate_plane((rad, y_face, 0.0), (1, 0, 0), up=(0, 1, 0))
        plane = plane.rotated((0, 0, twist))
        pts = lib.rounded_plate_pts(thick, wide, min(thick, wide) * 0.34, samples=5)
        faces.append(plane * make_face(Spline(*pts, periodic=True)))
    blade = _loft(faces)
    for i in range(N_SPOKE):
        part = part + _spin(blade, 360.0 * i / N_SPOKE + 18.0)
    # the barrel steps around the suspension pickups rather than through them
    return _cut(part, clearances)


# ==========================================================================
# 3 — WHEEL COVER: the wheel's face as ONE graphic object. A rolled outer rim,
#     a dished field carrying a spiral of BLIND milled flutes, a domed centre,
#     and THE one accent ring, split off the same solid so it shares its faces.
#
#     The flutes used to be through-slots. On the corner nearest the camera
#     they stopped reading as a spiral and started reading as a bolt circle,
#     because each slot showed the bright magnesium rim spoke behind it: a ring
#     of bright holes punched through an otherwise black disc. The face of a
#     real F1 wheel is a closed dark disc. So the flute tool now lives entirely
#     OUTBOARD of the dish and only mills `FLUTE_DEPTH` into it — the graphic
#     survives as shading, the cover stays solid, and nothing behind it can
#     leak through on any corner.
# ==========================================================================

_COVER_STATIONS = (  # (radius, outboard offset from the rim flange, inboard)
    (COVER_R, 5.0, 1.6),
    (238.0, 3.6, 0.8),
    (232.0, 2.0, -0.4),
    (222.0, 0.4, -3.4),
    (208.0, -3.0, -8.0),
    (192.0, -6.6, -12.0),
    (168.0, -9.6, -15.6),
    (140.0, -11.2, -17.6),
    (112.0, -11.4, -18.0),
    (88.0, -9.6, -16.0),
    (66.0, -5.6, -11.6),
    (48.0, -0.6, -6.0),
    (38.0, 2.8, -2.0),
    (31.0, 4.4, 0.4),
)


# the flute spiral, sampled densely enough that the tool floor tracks the dish
_FLUTE_STATIONS = (  # (radius, spiral offset deg, tangential width)
    (80.0, 0.0, 9.5),
    (108.0, 5.0, 13.0),
    (136.0, 10.5, 15.0),
    (162.0, 16.0, 15.5),
    (184.0, 21.5, 13.0),
    (199.0, 26.0, 8.5),
)


def _cover_face_y(bh: float, radius: float) -> float:
    """Outboard surface height of the cover dish at radius `radius`.

    The flute tool is positioned off this, so the milled floor follows the dish
    instead of slicing a flat plane through a curved panel — which is what
    turned the old slots into through-holes at the outer stations.
    """
    st = list(reversed(_COVER_STATIONS))  # ascending radius
    if radius <= st[0][0]:
        return bh + st[0][1]
    if radius >= st[-1][0]:
        return bh + st[-1][1]
    for i in range(len(st) - 1):
        r0, d0, _ = st[i]
        r1, d1, _ = st[i + 1]
        if r0 <= radius <= r1:
            t = (radius - r0) / (r1 - r0)
            return bh + d0 + (d1 - d0) * t
    return bh + st[-1][1]


def _flute_face(bh: float, radius: float, spiral_deg: float, wide: float):
    """Section of the flute cutter: normal radial, swept into a spiral.

    The section's inboard edge sits `FLUTE_DEPTH` under the dish and the rest
    of it stands proud of the wheel, so subtracting it can only ever mill a
    blind groove.
    """
    yc = _cover_face_y(bh, radius) - FLUTE_DEPTH + FLUTE_TOOL_H / 2.0
    plane = lib.plate_plane(
        _polar(radius, spiral_deg, yc), _radial(spiral_deg), up=(0, 1, 0)
    )
    pts = lib.rounded_plate_pts(wide, FLUTE_TOOL_H, wide * 0.48, samples=6)
    return plane * make_face(Spline(*pts, periodic=True))


def _cover(bh: float):
    out = [(bh + d, r) for r, d, _ in _COVER_STATIONS]
    inn = [(bh + d, r) for r, _, d in reversed(_COVER_STATIONS)]
    shell = _rev(
        [
            out,
            [out[-1], inn[0]],
            inn,
            [inn[-1], out[0]],
        ]
    )

    flute = _loft(
        [_flute_face(bh, r, s, w) for r, s, w in _FLUTE_STATIONS]
    )
    cutters = [_spin(flute, 360.0 * i / N_FLUTE) for i in range(N_FLUTE)]
    shell = _cut(shell, cutters)

    # The accent ring is SPLIT off the finished shell, not laid on top of it,
    # so the one stripe of colour on the wheel shares its faces with the cover
    # and cannot step proud of it on any corner. The tool is a shallow turned
    # groove that PARALLELS the dish rather than a slab through the whole
    # panel: a full-depth slab severed the cover into two disjoint solids, and
    # a two-solid compound survives `mirror` as one body but not as two — so
    # the left covers exported as an unlabelled pair and the right ones as a
    # single body. Same geometry, different tree, on the same car.
    d0 = _cover_face_y(bh, RING_R0) - RING_DEPTH
    d1 = _cover_face_y(bh, RING_R1) - RING_DEPTH
    y_over = bh + 12.0
    slab = _rev(
        [
            [(y_over, RING_R0), (y_over, RING_R1)],
            [(y_over, RING_R1), (d1, RING_R1)],
            [(d1, RING_R1), (d0, RING_R0)],
            [(d0, RING_R0), (y_over, RING_R0)],
        ]
    )
    cover = lib.repair(_defrag(lib.as_body(shell - slab)))
    ring = lib.repair(lib.as_body(shell & slab))
    return cover, ring


# ==========================================================================
# 4 — WHEEL NUT: one turned, capped machined button with a single retention
#     groove. It was castellated and cut in bright ALLOY, which made the
#     centre of the wheel face the brightest, busiest object in the whole
#     three-quarter view — the six castellations threw six specular highlights
#     and the open bore showed the hub behind it. A closed crown in gunmetal
#     titanium reads as machined without competing with the bodywork.
# ==========================================================================


def _nut(bh: float):
    # Stated as offsets from the rim flange plane, with no tyre-width clamp in
    # them, so the front and rear nuts are the SAME machined part sitting the
    # same distance proud of the same cover — the front/rear difference in this
    # module is the tyre section width and nothing else.
    y0 = bh + 4.8  # clear of the cover's centre boss (max +4.4 at r=31)
    y1 = bh + 15.0
    body = _rev(
        [
            [(y0, 0.0), (y0, 34.0)],  # seat face, closed across the axis
            [(y0, 34.0), (y0 + 2.2, 37.0)],  # lead-in chamfer
            [(y0 + 2.2, 37.0), (y1 - 3.0, 37.0)],  # turned flank
            [(y1 - 3.0, 37.0), (y1, 32.0)],  # crown chamfer
            # FLAT crown, closed across the axis. A domed crown was tried and
            # is a mirror: a sphere always finds the specular angle, so the nut
            # burned out to pure white in every three-quarter view and put the
            # brightest pixel on the car dead centre of the wheel face. A flat
            # face flares only when the light happens to line up with it.
            [(y1, 32.0), (y1, 0.0)],
            [(y1, 0.0), (y0, 0.0)],
        ]
    )
    body = _cut(body, _ring(y0 + 3.4, y0 + 5.6, 32.0, 40.0))
    body = _cut(body, _ring(y1 + 0.2, y1 - 1.6, 0.0, 20.0))  # drive recess
    clip = _ring(y0 + 3.9, y0 + 5.3, 32.4, 37.4, arc=306.0)
    return lib.repair(body), lib.repair(clip)


# ==========================================================================
# 5 — CARBON BRAKE DISC: thin, big, with the dense regular ring of radial
#     cooling drillings and an inner/outer groove pair reading as the
#     vented core.
# ==========================================================================


def _disc(axle: str):
    r_out = DISC_R[axle]
    r_in = 96.0 if axle == "f" else 86.0
    t = DISC_T[axle]
    y0, y1 = DISC_Y - t / 2.0, DISC_Y + t / 2.0
    body = _rev(
        [
            [(y0, r_in), (y0, r_out - 3.0)],
            [(y0, r_out - 3.0), (y0 + 3.0, r_out)],
            [(y0 + 3.0, r_out), (y1 - 3.0, r_out)],
            [(y1 - 3.0, r_out), (y1, r_out - 3.0)],
            [(y1, r_out - 3.0), (y1, r_in)],
            [(y1, r_in), (y0, r_in)],
        ]
    )
    grooves = []
    for rg in (r_out - 27.0, r_in + 16.0):
        grooves.append(_ring(y0, y0 + 1.8, rg - 3.2, rg + 3.2))
        grooves.append(_ring(y1, y1 - 1.8, rg - 3.2, rg + 3.2))
    body = _cut(body, grooves)

    drills = []
    for row, yd in enumerate((DISC_Y - 6.2, DISC_Y + 6.2)):
        for i in range(N_DRILL):
            phi = 360.0 * (i + 0.5 * row) / N_DRILL
            drills.append(
                _cyl(2.6, 62.0, _polar(r_out - 18.0, phi, yd), _radial(phi))
            )
    return _cut(body, drills)


# ==========================================================================
# 6 — CALIPER: a machined six-pot straddling the disc, bridge windows, pad
#     pins and a brake-line fitting.
# ==========================================================================


def _cal_face(phi: float, rc: float, axial: float, radial: float):
    plane = lib.plate_plane(
        _polar(rc, phi, DISC_Y), _tangent(phi), up=_radial(phi)
    )
    pts = lib.rounded_plate_pts(axial, radial, min(axial, radial) * 0.3, samples=5)
    return plane * make_face(Spline(*pts, periodic=True))


def _caliper(axle: str):
    r_out = DISC_R[axle]
    t = DISC_T[axle]
    phi = CAL_PHI[axle]
    rc = r_out - 10.0
    half_ax = t / 2.0 + 24.0
    body = _loft(
        [
            _cal_face(phi - 19.0, rc, 2 * half_ax - 22.0, 52.0),
            _cal_face(phi - 10.0, rc, 2 * half_ax - 4.0, 66.0),
            _cal_face(phi, rc, 2 * half_ax, 70.0),
            _cal_face(phi + 10.0, rc, 2 * half_ax - 4.0, 66.0),
            _cal_face(phi + 19.0, rc, 2 * half_ax - 22.0, 52.0),
        ]
    )
    # the disc passes through: what is left is two cheeks under one bridge
    body = body - _ring(
        DISC_Y - t / 2.0 - 3.0, DISC_Y + t / 2.0 + 3.0, 0.0, r_out + 7.0
    )
    # rhythmic bridge windows
    windows = []
    for d in (-9.5, 9.5):
        plane = lib.plate_plane(
            _polar(r_out + 18.0, phi + d, DISC_Y), _tangent(phi + d), up=_radial(phi + d)
        )
        windows.append(plane * Box(2 * half_ax + 20.0, 34.0, 15.0))
    body = _cut(body, windows)

    pots = None
    for d in (-11.0, 0.0, 11.0):
        for s in (-1.0, 1.0):
            yb = DISC_Y + s * (half_ax - 5.0)
            boss = _cyl(14.0, 20.0, _polar(r_out - 22.0, phi + d, yb), (0, 1, 0))
            pots = boss if pots is None else pots + boss
    pots = pots - _ring(
        DISC_Y - t / 2.0 - 3.0, DISC_Y + t / 2.0 + 3.0, 0.0, r_out + 7.0
    )

    pins = None
    for d in (-14.0, 14.0):
        p = _cyl(5.0, 2 * half_ax + 14.0, _polar(r_out + 1.0, phi + d, DISC_Y), (0, 1, 0))
        pins = p if pins is None else pins + p

    fit_c = _polar(r_out + 12.0, phi + 24.0, DISC_Y - half_ax + 12.0)
    line = _cyl(9.0, 16.0, fit_c, _radial(phi + 24.0))
    line = line + _cyl(
        5.0, 46.0, _polar(r_out + 30.0, phi + 24.0, DISC_Y - half_ax + 12.0),
        _radial(phi + 24.0),
    )
    return body, pots, pins + line


# ==========================================================================
# 7 — BRAKE DUCT: carbon drum wrapping the inboard face of the disc, a rolled
#     forward inlet scoop, outlet slots, and turning vanes drawn from the
#     SAME aerofoil family as the front wing (lib.wing_element).
# ==========================================================================


def _duct(axle: str, bh: float):
    yd = -bh  # the rim's inboard flange plane
    drum = _rev(
        [
            [  # outboard (concave) face
                (yd + 13.0, 94.0),
                (yd + 10.0, 124.0),
                (yd + 6.0, 152.0),
                (yd + 1.0, 174.0),
                (yd - 3.0, 186.0),
            ],
            [  # rolled outer lip
                (yd - 3.0, 186.0),
                (yd - 6.5, 190.0),
                (yd - 10.0, 187.0),
                (yd - 11.0, 181.0),
            ],
            [  # inboard face
                (yd - 11.0, 181.0),
                (yd - 8.0, 170.0),
                (yd - 3.0, 148.0),
                (yd + 2.0, 122.0),
                (yd + 6.0, 94.0),
            ],
            [(yd + 6.0, 94.0), (yd + 13.0, 94.0)],
        ]
    )
    # outlet furniture: three rhythmic kidney exits high on the drum
    exits = []
    for phi in (104.0, 142.0, 180.0):
        exits.append(_cyl(17.0, 60.0, _polar(158.0, phi, yd), (0, 1, 0)))
    drum = _cut(drum, exits)

    # forward inlet scoop with a rolled lip, fused into the drum
    mouth = _polar(250.0, -30.0, yd - 43.0)
    mid = _polar(206.0, -36.0, yd - 35.0)
    root = _polar(166.0, -44.0, yd - 20.0)
    shell = _lofted(
        [
            (mouth, (0, 1, 0), (1, 0, 0.32), 24.0, 46.0, 2.5),
            (mid, (0, 1, 0), (1, 0, 0.52), 24.0, 36.0, 2.6),
            (root, (0, 1, 0), (1, 0, 0.74), 22.0, 30.0, 2.8),
        ]
    )
    bore = _lofted(
        [
            (Vector(mouth) + Vector(22, 0, 10), (0, 1, 0), (1, 0, 0.32), 19.0, 40.0, 2.5),
            (mid, (0, 1, 0), (1, 0, 0.52), 19.0, 30.0, 2.6),
            (Vector(root) - Vector(34, 0, -26), (0, 1, 0), (1, 0, 0.74), 17.0, 24.0, 2.8),
        ]
    )
    scoop = shell - bore
    duct = drum + scoop

    # turning vanes — one aerofoil family with the front wing, rhythmic
    chords = spec.cascade_chords(126.0, 3)
    gaps = spec.cascade_gaps(46.0, 3)
    vanes = []
    z = -58.0
    for i, chord in enumerate(chords):
        span0 = yd - 6.0
        span1 = yd - 50.0 - 7.0 * i
        vanes.append(
            lib.wing_element(
                [
                    {
                        "le": (232.0 - 6.0 * i, span0, z),
                        "chord": chord,
                        "twist": 7.0 + 9.5 * i,
                        "thickness": 0.085,
                    },
                    {
                        "le": (232.0 - 6.0 * i - 10.0, (span0 + span1) / 2.0, z - 4.0),
                        "chord": chord * 0.92,
                        "twist": 9.0 + 10.5 * i,
                        "thickness": 0.078,
                    },
                    {
                        "le": (232.0 - 6.0 * i - 26.0, span1, z - 11.0),
                        "chord": chord * 0.76,
                        "twist": 11.0 + 12.0 * i,
                        "thickness": 0.070,
                    },
                ]
            )
        )
        if i < len(gaps):
            z -= chord * 0.30 + gaps[i]
    return duct, vanes


# ==========================================================================
# 8 — UPRIGHT + HUB: machined titanium, waisted, with the load paths from the
#     ball joints to the bearing housing left visible and pocketed out.
# ==========================================================================


def _local(pt, x_axle: float, hub_y: float):
    return (pt[0] - x_axle, pt[1] - hub_y, pt[2] - spec.HUB_Z)


def _eye(center, axis, r: float = EYE_R, length: float = EYE_L):
    return _cyl(r, length, center, axis)


def _upright(axle: str, joints):
    """joints: [(local point, pin axis, root point on the bearing housing)]"""
    housing = _rev(
        [
            [(-104.0, 54.0), (-104.0, 88.0)],
            [  # waisted outer surface — the bearing carrier necks in mid-span
                (-104.0, 88.0),
                (-88.0, 92.0),
                (-64.0, 82.0),
                (-42.0, 78.0),
                (-26.0, 84.0),
                (-18.0, 90.0),
            ],
            [(-18.0, 90.0), (-18.0, 54.0)],
            [(-18.0, 54.0), (-104.0, 54.0)],
        ]
    )
    part = housing
    pockets = []
    for pt, axis, root, law, thin in joints:
        part = part + _limb(root, pt, law, thin=thin)
        part = part + _eye(pt, axis)
        # lightening scallops: milled into BOTH flanks of the waist, never
        # through it — a limb that a boolean severs is not a load path.
        ax = (Vector(pt) - Vector(root)).normalized()
        td = Vector(thin)
        td = (td - ax * td.dot(ax)).normalized()
        waist = law[len(law) // 2]
        for t, rp in ((0.40, 14.0), (0.66, 11.0)):
            mid = Vector(root) + (Vector(pt) - Vector(root)) * t
            for s in (-1.0, 1.0):
                pockets.append(
                    _cyl(rp, 40.0, mid + td * (s * (waist[2] + 13.0)), td)
                )
    part = _cut(part, pockets)
    # bores: the bearing bore and every joint's pin hole
    bores = [_cyl(54.0, 120.0, (0, -61.0, 0), (0, 1, 0))]
    for pt, axis, _root, _law, _thin in joints:
        bores.append(_cyl(7.0, EYE_L + 12.0, pt, axis))
    return _cut(part, bores)


def _hub(bh: float):
    body = _rev(
        _poly(
            [
                (-104.0, 13.0),
                (-104.0, 38.0),
                (-98.0, 44.0),
                (-98.0, 52.0),
                (-20.0, 52.0),
                (-16.0, 58.0),
                (-6.0, 62.0),
                (4.0, 60.0),
                (4.0, 100.0),
                (-13.0, 100.0),
                (-13.0, 92.0),
                (2.0, 60.0),
                (10.0, 44.0),
                (10.0, 28.0),
                # the hub stops SHORT of the nut's seat face: it used to run
                # out to bh+15 and its bored end ring was the bright metal
                # showing at the centre of the wheel face.
                (bh + 1.0, 26.0),
                (bh + 1.0, 13.0),
            ]
        )
    )
    for i in range(6):
        body = body + _spin(
            _cyl(8.0, 22.0, (46.0, 1.0, 0.0), (0, 1, 0)), 60.0 * i
        )
    return body


# ==========================================================================
# assembly
# ==========================================================================

_AXLE_OF = {"fl": "f", "fr": "f", "rl": "r", "rr": "r"}
_CACHE: dict[str, list] = {}


def _joint_defs(axle: str, x_axle: float, hub_y: float):
    """Ball-joint eyes, straight off the spec hardpoints."""
    def L(p):
        return _local(p, x_axle, hub_y)

    up_law = ((0.0, 54.0, 40.0, 2.6), (0.42, 32.0, 25.0, 2.3), (1.0, 21.0, 17.0, 2.1))
    lo_law = ((0.0, 56.0, 42.0, 2.6), (0.42, 34.0, 26.0, 2.3), (1.0, 21.0, 17.0, 2.1))
    arm_law = ((0.0, 46.0, 32.0, 2.5), (0.45, 27.0, 21.0, 2.2), (1.0, 20.0, 16.0, 2.1))
    if axle == "f":
        return [
            (L(spec.F_UPPER_BALL), _pin_axis(spec.F_UPPER_IN_FWD, spec.F_UPPER_BALL),
             (0.0, -62.0, 62.0), up_law, (1, 0, 0)),
            (L(spec.F_LOWER_BALL), _pin_axis(spec.F_LOWER_IN_FWD, spec.F_LOWER_BALL),
             (0.0, -60.0, -64.0), lo_law, (1, 0, 0)),
            (L(spec.F_TRACKROD_OUT), _pin_axis(spec.F_RACK_END, spec.F_TRACKROD_OUT),
             (48.0, -70.0, 34.0), arm_law, (0, 0, 1)),
        ]
    return [
        (L(spec.R_UPPER_BALL), _pin_axis(spec.R_UPPER_IN_FWD, spec.R_UPPER_BALL),
         (0.0, -62.0, 62.0), up_law, (1, 0, 0)),
        (L(spec.R_LOWER_BALL), _pin_axis(spec.R_LOWER_IN_FWD, spec.R_LOWER_BALL),
         (0.0, -60.0, -64.0), lo_law, (1, 0, 0)),
        (L(spec.R_TOELINK_OUT), _pin_axis(spec.R_TOELINK_IN, spec.R_TOELINK_OUT),
         (-46.0, -68.0, -40.0), arm_law, (0, 0, 1)),
        (L(spec.R_PULLROD_OUT), _pin_axis(spec.R_PULLROD_IN, spec.R_PULLROD_OUT),
         (-8.0, -66.0, 60.0), arm_law, (0, 0, 1)),
    ]


def _left_corner(axle: str):
    """[(shape, label, colour)] for the LEFT corner of one axle, wheel frame."""
    if axle in _CACHE:
        return _CACHE[axle]
    front = axle == "f"
    hw = (spec.TIRE_W_FRONT if front else spec.TIRE_W_REAR) / 2.0
    bh = RIM_HW[axle]
    x_axle = spec.FRONT_AXLE_X if front else spec.REAR_AXLE_X
    hub_y = spec.FRONT_HUB_Y if front else spec.REAR_HUB_Y
    joints = _joint_defs(axle, x_axle, hub_y)

    out = []
    tread, carcass = _tyre(hw, bh)
    out.append((tread, "tyre_tread", spec.RUBBER))
    out.append((carcass, "tyre_carcass", spec.RUBBER_SIDEWALL))

    clearances = [
        _cyl(EYE_R + 3.0, EYE_L + 8.0, pt, axis) for pt, axis, _r, _l, _t in joints
    ]
    clearances += [Pos(pt) * Sphere(EYE_R + 3.0) for pt, *_ in joints]
    out.append((_rim(bh, clearances), "rim", spec.MAGNESIUM))

    cover, ring = _cover(bh)
    out.append((cover, "wheel_cover", spec.CARBON_GLOSS))
    out.append((ring, "cover_ring", spec.ACCENT))
    nut, clip = _nut(bh)
    out.append((nut, "wheel_nut", spec.ANODIZED))
    out.append((clip, "nut_clip", spec.TITANIUM))

    out.append((_disc(axle), "brake_disc", spec.CARBON_DISC))
    cal, pots, hardware = _caliper(axle)
    out.append((cal, "caliper", spec.ANODIZED))
    out.append((pots, "caliper_pots", spec.ALLOY))
    out.append((hardware, "caliper_hardware", spec.STEEL))

    duct, vanes = _duct(axle, bh)
    out.append((duct, "brake_duct", spec.CARBON_MATTE))
    for i, v in enumerate(vanes):
        out.append((v, f"duct_vane_{i + 1}", spec.CARBON_MATTE))

    out.append((_upright(axle, joints), "upright", spec.TITANIUM))
    out.append((_hub(bh), "hub", spec.ALLOY))

    _CACHE[axle] = out
    return out


def build_corner(corner: str):
    axle = _AXLE_OF[corner]
    front = axle == "f"
    x = spec.FRONT_AXLE_X if front else spec.REAR_AXLE_X
    place = Pos(x, spec.FRONT_HUB_Y if front else spec.REAR_HUB_Y, spec.HUB_Z)
    left = corner.endswith("l")

    kids = []
    for shape, label, color in _left_corner(axle):
        body = place * shape
        if not left:
            body = lib.mirror_y(body)
        kids.append(lib.styled(body, f"{label}:{corner}", color))
    return lib.group(f"corner_{corner}", kids)
