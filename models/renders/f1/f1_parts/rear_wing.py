"""Rear wing: mainplane, DRS flap, endplates, swan-neck pylon, beam wing, DRS linkage.

Four assembly children, because the animation sidecar drives two of them:

  build_rear_wing()    static structure  — mainplane, endplates, pylon
  build_drs_flap()     rotates about the axis through spec.DRS_PIVOT parallel to Y
  build_drs_actuator() the four-bar that drives it
  build_beam_wing()    static, two elements

GEOMETRY NOTES THAT MATTER TO THE ANIMATION
-------------------------------------------
* The flap is modelled CLOSED (spec.RW_FLAP_INCIDENCE_CLOSED_DEG) and every
  station's leading edge sits a constant `_FLAP_PIVOT_OFF` back along its own
  chord from the pivot axis, so the flap's lower-front nose is a surface of
  revolution about that axis: the slot gap is invariant under DRS rotation.
* The crank is modelled at spec.DRS_CRANK_ANGLE_CLOSED_DEG and its rod-end eye
  is exactly on spec.DRS_CRANK_END_CLOSED; the flap's lug eye is exactly on
  spec.DRS_LUG_CLOSED. The link body spans precisely spec.DRS_LINK_L.
* The bellcrank arm sweeps FORWARD of the mainplane leading edge rather than
  taking the short straight line to its rod end — a straight spoke would be
  buried inside the mainplane at the closed pose. The swept arm is clear of the
  mainplane through the whole 67.5 deg crank sweep.
* The endplate outline is a walked POLYGON with radiused corners, not a bowed
  point cloud (see `_EP_CORNERS`). Its diagonal top-rear cut is aimed to clear
  the DRS bearing at spec.DRS_PIVOT while still uncovering the mainplane
  trailing edge, the slot gap and the flap aft of x = -4000.
* The carbon mainplane STOPS at `_MAIN_TIP_Y`, inboard of spec.DRS_LINK_Y, and
  closes into a machined titanium tip rib. It has to: the spec four-bar sweeps
  127 mm of a 152 mm chord at y = 462, so no mainplane can coexist with it
  there. The 74 mm bay that opens up is the DRS bay — the linkage is fully
  visible in it, the flap roofs it, the endplate walls it, and a slender tie
  blade closes the trailing-edge line out to the endplate. See the report.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Cylinder,
    Location,
    Plane,
    Pos,
    Rotation,
    Sphere,
    Spline,
    Vector,
    extrude,
    make_face,
)

from . import lib, spec

# ==========================================================================
# derived datums
# ==========================================================================

_PIV = Vector(*spec.DRS_PIVOT)
_FLAP_TW0 = spec.RW_FLAP_INCIDENCE_CLOSED_DEG
_FLAP_PIVOT_OFF = 32.0  # pivot sits this far aft of the flap LE, on its chord

# section family for this wing: thin, strongly cambered, genuinely thin TE
_MAIN_T, _MAIN_CAM = 0.070, 0.085
_FLAP_T, _FLAP_CAM = 0.070, 0.050

_MAIN_TIP_Y = 446.0  # carbon element closes here, inboard of the DRS bay
_RIB_OUT_Y = 452.0  # outboard face of the rib = mounting face for the crank
_FLAP_TIP_Y = spec.RW_HALF_SPAN - 6.0  # running clearance, bridged by the boss

_EP_IN_Y = spec.RW_HALF_SPAN  # endplate inner face
_EP_OUT_Y = spec.RW_HALF_SPAN + 16.0  # outer face; nothing goes past +24


def _chord_dir(twist_deg: float):
    """Unit vector LE -> TE in the car x-z plane for a section at `twist_deg`."""
    a = math.radians(twist_deg)
    return Vector(-math.cos(a), 0.0, math.sin(a))


def _up_dir(twist_deg: float):
    """Unit section normal ("up" in the section's own frame)."""
    a = math.radians(twist_deg)
    return Vector(math.sin(a), 0.0, math.cos(a))


# --------------------------------------------------------------------------
# LOCAL SECTION PLACEMENT
#
# `lib.section_plane()` applies its twist as `Plane.rotated((0, 0, twist))`,
# and build123d's `Plane.rotated` builds its matrix in WORLD axes — so that is
# a rotation about world Z, i.e. a YAW. Every element built through
# `lib.airfoil_face()` / `lib.wing_element()` therefore comes out flat and
# swept instead of pitched: a 34 deg "twist" moved the flap 56 mm sideways and
# 0 mm up. `twist_deg` and `sweep_deg` are transposed in that helper.
#
# We keep the section FAMILY (`lib.airfoil_profile`) and the loft helper
# (`lib.loft_solid`), and only place the section ourselves, so this module is
# correct both before and after that helper is fixed. Flagged in the report.
# --------------------------------------------------------------------------


def _section_plane(origin, twist_deg: float) -> Plane:
    """Local +x = chord LE->TE, local +y = section normal, normal = car Y.

    Positive `twist_deg` lifts the trailing edge (more downforce), matching the
    sign convention stated in spec.py.
    """
    return Plane(
        origin=Vector(*origin), x_dir=_chord_dir(twist_deg), z_dir=Vector(0, 1, 0)
    )


def _afoil_face(st: dict):
    wire = lib.airfoil_profile(
        st["chord"],
        thickness=st.get("thickness", 0.095),
        camber=st.get("camber", 0.055),
        camber_pos=st.get("camber_pos", 0.40),
        samples=st.get("samples", 37),
        te_thickness=st.get("te"),
    )
    return _section_plane(st["le"], st.get("twist", 0.0)) * make_face(wire)


def _wing(stations, ruled: bool = False):
    """`lib.wing_element` with the section placement corrected."""
    return lib.loft_solid([_afoil_face(st) for st in stations], ruled=ruled)


# ==========================================================================
# MAINPLANE — spoon planform
# ==========================================================================


def _main_span_t(y: float) -> float:
    """Span fraction referenced to the FULL half span, not the carbon tip.

    Keeping the reference at spec.RW_HALF_SPAN means the spoon law is the one
    the wing would have had at full span; the element just stops early.
    """
    return spec.smoothstep(min(abs(y) / (spec.RW_HALF_SPAN * 0.96), 1.0))


def _main_chord(y: float) -> float:
    """Spoon chord law: loaded and deep at the centre, unloaded at the tips."""
    return lib.taper(spec.RW_MAIN_CHORD, 150.0, _main_span_t(y), ease=1.25)


def _main_station(y: float, roll: bool = True) -> dict:
    s = _main_span_t(y)
    twist = lib.taper(spec.RW_MAIN_INCIDENCE_DEG, 9.6, s)
    le_x = spec.RW_MAIN_LE_X - 28.0 * s  # LE bows FORWARD at the centreline
    le_z = spec.RW_MAIN_Z + 6.0 * s
    # tip roll: the outboard 20 mm lifts and thins so the element rolls over
    # into its closing rib instead of ending in a flat slab face
    r = 0.0
    if roll:
        r = min(max(0.0, (abs(y) - (_MAIN_TIP_Y - 20.0)) / 20.0), 1.0)
        le_z += spec.TIP_ROLL_R * 0.5 * r * r
    return {
        "le": (le_x, y, le_z),
        "chord": _main_chord(y) * (1.0 - 0.18 * r * r),
        "twist": twist,
        "thickness": lib.taper(_MAIN_T, 0.060, s) * (1.0 - 0.32 * r),
        "camber": lib.taper(_MAIN_CAM, 0.072, s),
        "camber_pos": 0.40,
        "samples": 49,
    }


_MAIN_YS = (
    0.0, 58.0, 122.0, 190.0, 258.0, 322.0, 380.0, 412.0,
    430.0, 440.0, _MAIN_TIP_Y,
)


def _mainplane():
    ys = [-y for y in reversed(_MAIN_YS[1:])] + list(_MAIN_YS)
    return _wing([_main_station(y) for y in ys])


# ==========================================================================
# DRS FLAP — modelled closed, nose concentric with the pivot axis
# ==========================================================================


def _flap_span_t(y: float) -> float:
    return spec.smoothstep(min(abs(y) / _FLAP_TIP_Y, 1.0))


def _flap_station(y: float) -> dict:
    s = _flap_span_t(y)
    twist = lib.taper(_FLAP_TW0, 31.0, s)
    r = max(0.0, (abs(y) - (_FLAP_TIP_Y - 18.0)) / 18.0)
    r = min(r, 1.0)
    # LE is always _FLAP_PIVOT_OFF forward of the pivot ALONG THIS STATION'S
    # chord, so the nose stays a surface of revolution about the pivot axis.
    le = _PIV - _chord_dir(twist) * _FLAP_PIVOT_OFF
    return {
        "le": (le.X, y, le.Z),
        "chord": lib.taper(spec.RW_FLAP_CHORD, 152.0, s) * (1.0 - 0.16 * r * r),
        "twist": twist,
        "thickness": _FLAP_T * (1.0 - 0.28 * r),
        "camber": lib.taper(_FLAP_CAM, 0.042, s),
        "camber_pos": 0.38,
        "samples": 49,
    }


_FLAP_YS = (0.0, 70.0, 150.0, 230.0, 310.0, 380.0, 440.0, 480.0, 500.0, _FLAP_TIP_Y)


def _flap_element():
    ys = [-y for y in reversed(_FLAP_YS[1:])] + list(_FLAP_YS)
    return _wing([_flap_station(y) for y in ys])


# ==========================================================================
# ENDPLATE — slim raked plate: straight runs, crisp corners, top-rear cut
# ==========================================================================
#
# The outline is walked as CORNERS, not as a cloud of bowed points: straight
# runs meet at explicitly radiused corners, so the plate reads as a hard-edged
# carbon panel rather than one continuous rounded blob.
#
# The built solid measures 255 x 16 x 481 mm: its fore-aft chord is 1.02 x
# spec.RW_MAIN_CHORD, i.e. only just longer than the mainplane it closes — a
# slim, tall plate, not a whale fin. The top-rear corner is cut away on a 45 deg
# diagonal that starts just aft of spec.DRS_PIVOT (the plate still has to carry
# the flap bearing), so from x = -4000 aft the mainplane trailing edge, the slot
# gap and the DRS flap all stand PROUD of the plate in side view instead of
# hiding behind it.
#
#   A top-front       B crown          C foot of the diagonal cut
#   D trailing edge   E lower rear     F bottom, at the beam-wing junction
#   K lower-LE knuckle                 J upper-LE knuckle
_EP_CORNERS = (
    (-3846.0, 896.0, 12.0),  # A
    (-3972.0, 912.0, 10.0),  # B
    (-4084.0, 800.0, 10.0),  # C
    (-4104.0, 566.0, 12.0),  # D
    (-4086.0, 428.0, 12.0),  # E
    (-4020.0, 440.0, 14.0),  # F
    (-3968.0, 520.0, 16.0),  # K
    (-3880.0, 738.0, 18.0),  # J
)

# Outline extents (corner to corner). The rolled edges pull the built solid in
# a little: it measures 255.1 x 481.1 mm.
EP_CHORD = 258.0
EP_HEIGHT = 484.0


def _unit2(dx: float, dz: float):
    L = math.hypot(dx, dz) or 1.0
    return dx / L, dz / L


def _round_corners(corners, arc_samples: int = 5, run_step: float = 18.0):
    """Dense closed loop from a polygon of (x, z, corner_radius).

    Emits a true circular arc at every corner and evenly-spaced points along
    every straight run between them. Sampling the straight runs densely is what
    stops the periodic spline through the result from bellying a flat trailing
    edge out into a leaf shape.
    """
    n = len(corners)
    fil = []
    for i in range(n):
        px, pz, _ = corners[(i - 1) % n]
        cx, cz, r = corners[i]
        qx, qz, _ = corners[(i + 1) % n]
        u1 = _unit2(px - cx, pz - cz)
        u2 = _unit2(qx - cx, qz - cz)
        cosang = max(-0.999999, min(0.999999, u1[0] * u2[0] + u1[1] * u2[1]))
        half = math.acos(cosang) / 2.0  # half the interior angle
        t = r / max(math.tan(half), 1e-6)  # tangent distance from the corner
        lim = 0.45 * min(math.hypot(px - cx, pz - cz), math.hypot(qx - cx, qz - cz))
        if t > lim:
            t, r = lim, lim * math.tan(half)
        p1 = (cx + u1[0] * t, cz + u1[1] * t)
        p2 = (cx + u2[0] * t, cz + u2[1] * t)
        bis = _unit2(u1[0] + u2[0], u1[1] + u2[1])
        ctr_d = r / max(math.sin(half), 1e-6)
        ctr = (cx + bis[0] * ctr_d, cz + bis[1] * ctr_d)
        a1 = math.atan2(p1[1] - ctr[1], p1[0] - ctr[0])
        a2 = math.atan2(p2[1] - ctr[1], p2[0] - ctr[0])
        da = a2 - a1
        while da > math.pi:
            da -= 2.0 * math.pi
        while da < -math.pi:
            da += 2.0 * math.pi
        fil.append((p1, p2, ctr, r, a1, da))

    pts = []
    for i in range(n):
        p1, p2, ctr, r, a1, da = fil[i]
        for k in range(arc_samples + 1):
            a = a1 + da * k / arc_samples
            pts.append((ctr[0] + r * math.cos(a), ctr[1] + r * math.sin(a)))
        s, e = p2, fil[(i + 1) % n][0]
        L = math.hypot(e[0] - s[0], e[1] - s[1])
        m = max(int(L / run_step), 1)
        for k in range(1, m):
            f = k / m
            pts.append((s[0] + (e[0] - s[0]) * f, s[1] + (e[1] - s[1]) * f))
    return tuple(pts)


def _outward_normals(pts):
    """Unit outward normal at every point of a closed CONVEX loop."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cz = sum(p[1] for p in pts) / n
    out = []
    for i in range(n):
        ax, az = pts[(i - 1) % n]
        bx, bz = pts[(i + 1) % n]
        tx, tz = _unit2(bx - ax, bz - az)
        nx, nz = tz, -tx
        if nx * (pts[i][0] - cx) + nz * (pts[i][1] - cz) < 0.0:
            nx, nz = -nx, -nz
        out.append((nx, nz))
    return out


_EP_PTS = _round_corners(_EP_CORNERS)
_EP_NRM = _outward_normals(_EP_PTS)


def _edge_roll():
    """Per-point edge radius: spec.TIP_ROLL_R where the plate rolls over, a
    crisp panel radius everywhere else.

    Driven off the OUTLINE NORMAL, not off a bounding box, so the full roll
    lands exactly on the top edge and the raked leading edge, and dies out
    along the diagonal cut and the trailing edge — which stay hard.
    """
    out = []
    for (x, z), (nx, nz) in zip(_EP_PTS, _EP_NRM):
        w_top = max(0.0, nz) * spec.smoothstep((z - 858.0) / 56.0)
        w_le = max(0.0, nx) * spec.smoothstep((z - 470.0) / 120.0)
        out.append(2.4 + (spec.TIP_ROLL_R - 2.4) * max(w_top, 0.90 * w_le))
    return tuple(out)


_EP_ROLL = _edge_roll()

# Layer k is the circular roll parameter; y steps match a round-over of radius
# = the plate half-thickness, so the rolled edges are genuinely round.
_EP_LAYERS = (
    (_EP_IN_Y, 0.985), (_EP_IN_Y + 1.9, 0.80), (_EP_IN_Y + 4.2, 0.55),
    (0.5 * (_EP_IN_Y + _EP_OUT_Y), 0.0),
    (_EP_OUT_Y - 4.2, 0.55), (_EP_OUT_Y - 1.9, 0.80), (_EP_OUT_Y, 0.985),
)


def _ep_layer_pts(k: float):
    """Outline inset for a layer `k` (0 = mid-thickness, 1 = face)."""
    f = 1.0 - math.sqrt(max(0.0, 1.0 - k * k))
    out = []
    for (x, z), (nx, nz), r in zip(_EP_PTS, _EP_NRM, _EP_ROLL):
        off = r * f
        out.append((x - nx * off, z - nz * off))
    return out


def _endplate_shell():
    stations = []
    for y, k in _EP_LAYERS:
        pts = _ep_layer_pts(k)
        plane = lib.plate_plane((0.0, y, 0.0), (0, 1, 0))
        # plate_plane: local +x = car -X, local +y = car +Z
        stations.append({"plane": plane, "pts": [(-x, z) for x, z in pts]})
    return lib.swept_plate(stations)


def _louvre_cutters():
    """Rhythmic bank of gills through the outboard rear face.

    Real through-cuts, so the plate's carbon thickness is visible inside every
    slot. Length, pitch and tilt all progress geometrically down the trailing
    edge (spec rule 5) — the same rhythm law as the front wing cascade.
    """
    cutters = []
    n = 6
    length = 86.0
    x, z = -4036.0, 778.0
    for i in range(n):
        pts = lib.rounded_plate_pts(length, 6.8, 3.2, samples=5)
        # long axis stated explicitly: Plane.rotated() works in WORLD axes and
        # would tip the slot straight out of the endplate's own plane
        t = math.radians(10.0 - 2.6 * i)
        plane = Plane(
            origin=(x, 0.5 * (_EP_IN_Y + _EP_OUT_Y), z),
            x_dir=(-math.cos(t), 0.0, math.sin(t)),
            z_dir=(0, 1, 0),
        )
        face = plane * make_face(Spline(*pts, periodic=True))
        cutters.append(extrude(face, amount=40.0, both=True))
        x -= 2.2  # follow the trailing edge, which rakes aft going down
        z -= 33.5
        length *= 0.935
    return cutters


def _endplate():
    ep = _endplate_shell()
    for cutter in _louvre_cutters():
        try:
            trimmed = lib.cut(ep, cutter)
        except Exception:
            continue
        if lib.is_valid_shape(trimmed):
            ep = trimmed
    return ep


def _footplate_curl():
    """Footplate: the plate's bottom OUTBOARD edge rolls over into a curl.

    Stations normal to Y, exactly like the plate itself, because that is the
    one section stack OCC lofts reliably here: an X-normal band swept round the
    curl radius throws "BRep_API: command not done" the moment either end
    tapers. Each station is a lens along the plate's bottom edge; as it runs
    outboard it drops, thins and shortens, so the edge turns over and dies out
    instead of ending in a sawn-off panel face.
    """
    cx = -4051.0  # mid of the plate's bottom edge run
    z_edge = 428.0 + (cx + 4086.0) * (12.0 / 66.0)  # the bottom edge there
    tilt = math.degrees(math.atan2(12.0, 66.0))  # the bottom edge's own slope
    layers = (
        # (y, centre z offset from the plate edge, half chord, half thickness)
        (_EP_IN_Y + 2.0, 16.5, 34.0, 16.0),
        (_EP_IN_Y + 10.0, 9.0, 34.0, 13.0),
        (_EP_OUT_Y, 4.0, 33.0, 9.5),
        (_EP_OUT_Y + 4.0, 0.5, 31.0, 6.4),
        (_EP_OUT_Y + 7.6, -3.0, 28.0, 3.0),
    )
    stations = []
    for y, dz, hl, hh in layers:
        pts = _lens_pts(cx, z_edge + dz, hl, hh, tilt)
        plane = lib.plate_plane((0.0, y, 0.0), (0, 1, 0))
        stations.append({"plane": plane, "pts": [(-x, z) for x, z in pts]})
    return lib.swept_plate(stations)


def _lens_pts(cx, cz, hl, hh, tilt_deg, n: int = 16):
    """Blade-lens outline in car (x, z): pointed at both ends, tilted."""
    a = math.radians(tilt_deg)
    ca, sa = math.cos(a), math.sin(a)
    raw = []
    for i in range(n + 1):  # upper surface, forward -> aft
        t = -0.99 + 1.98 * i / n
        raw.append((hl * t, hh * (1.0 - t * t) ** 0.62))
    for i in range(1, n):  # lower surface, aft -> forward
        t = 0.99 - 1.98 * i / n
        raw.append((hl * t, -hh * (1.0 - t * t) ** 0.62))
    return [(cx + u * ca - v * sa, cz + u * sa + v * ca) for u, v in raw]


def _endplate_strakes():
    """Two horizontal strakes hung off the plate's INNER face, below the wing.

    Same rhythm law as every other cascade on the car: the lower strake's chord
    is spec.CHORD_RATIO of the upper one's, its span steps down by
    spec.GAP_RATIO, and its incidence steps up by a growing delta. Each one
    roots in the plate's inner face and tapers to a thin inboard tip.
    """
    out = []
    root_chord, root_span, tilt0 = 90.0, 28.0, -6.0
    for i, (cz, cx) in enumerate(((620.0, -4035.0), (548.0, -4045.0))):
        hl = 0.5 * root_chord * spec.CHORD_RATIO**i
        span = root_span * spec.GAP_RATIO**i
        tilt = tilt0 - 2.0 * i
        stations = []
        for f, hh_s, hl_s, dx, dz in (
            (0.00, 1.00, 1.00, 0.0, 0.0),
            (0.30, 0.92, 0.96, -3.0, -2.0),
            (0.70, 0.74, 0.86, -7.0, -5.0),
            (1.00, 0.50, 0.72, -11.0, -8.0),
        ):
            y = _EP_IN_Y - span * f
            pts = _lens_pts(cx + dx, cz + dz, hl * hl_s, 5.2 * hh_s, tilt - 2.0 * f)
            plane = lib.plate_plane((0.0, y, 0.0), (0, 1, 0))
            stations.append({"plane": plane, "pts": [(-x, z) for x, z in pts]})
        out.append(lib.swept_plate(stations))
    return out


def _endplate_foot():
    """Lower junction: the plate's bottom edge sweeps down, inboard and aft,
    tapering into the beam wing's UPPER element tip.

    spec.BEAM_WING_HALF_SPAN (425) is inboard of spec.RW_HALF_SPAN (520), so the
    endplate has to come to the beam wing rather than the other way round. The
    innermost station is deliberately the beam tip's own chord, tilt and
    thickness, so the two blend instead of colliding.
    """
    layers = (
        # (y, centre x, centre z, half chord, half thickness, tilt deg)
        (_EP_OUT_Y, -4053.0, 434.0, 33.0, 8.0, 6.0),
        (_EP_OUT_Y - 3.0, -4053.0, 434.0, 34.0, 9.5, 6.0),
        (_EP_IN_Y, -4056.0, 434.0, 36.0, 10.5, 8.0),
        (500.0, -4062.0, 434.0, 39.0, 11.0, 11.0),
        (476.0, -4070.0, 434.0, 42.0, 11.0, 14.0),
        (452.0, -4080.0, 434.5, 45.0, 10.0, 17.0),
        (436.0, -4090.0, 435.0, 48.0, 7.5, 20.0),
        (430.0, -4094.0, 435.5, 49.0, 5.0, 21.0),
    )
    stations = []
    for y, cx, cz, hl, hh, tilt in layers:
        pts = _lens_pts(cx, cz, hl, hh, tilt)
        plane = lib.plate_plane((0.0, y, 0.0), (0, 1, 0))
        stations.append({"plane": plane, "pts": [(-x, z) for x, z in pts]})
    return lib.swept_plate(stations)


# ==========================================================================
# SWAN-NECK PYLON — attaches on TOP of the mainplane, underside stays clean
# ==========================================================================


def _pylon():
    """Tapered blade rising from the rear crash structure to just ahead of the
    mainplane leading edge.

    The path never turns within 20 deg of horizontal: `lib.blade_face` frames
    its sections with `_ortho_basis`, which swaps its reference vector once the
    member runs along FLOW, and a path that turned over the top folded the loft
    on itself. The over-the-top curl is a separate body, `_pylon_neck`.
    """
    path = (
        (-3906.0, 0.0, 352.0),
        (-3903.0, 0.0, 452.0),
        (-3897.0, 0.0, 556.0),
        (-3888.0, 0.0, 652.0),
        (-3876.0, 0.0, 738.0),
        (-3864.0, 0.0, 792.0),
        (-3856.0, 0.0, 818.0),
    )
    chords = (172.0, 164.0, 154.0, 142.0, 130.0, 118.0, 108.0)
    return lib.blade_path(path, chords, thickness_ratio=0.105, samples=33)


def _pylon_neck():
    """The swan neck itself: hooks over the mainplane leading edge and lands on
    its UPPER surface, so the underside of the wing stays clean.

    Built as an explicit profile lofted across its thickness rather than as a
    swept blade, because the section frame is unstable through a 90 deg turn.
    """
    prof = (
        # outer edge: up the front, over the top, back along the crown
        (-3850.0, 802.0), (-3838.0, 826.0), (-3836.0, 850.0), (-3846.0, 870.0),
        (-3868.0, 880.0), (-3894.0, 880.0), (-3916.0, 872.0), (-3921.0, 856.0),
        # inner edge: forward again, sitting just into the mainplane's upper
        # surface so the joint closes with no visible gap
        (-3900.0, 834.0), (-3878.0, 829.0), (-3860.0, 826.0), (-3848.0, 814.0),
    )
    cx = sum(p[0] for p in prof) / len(prof)
    cz = sum(p[1] for p in prof) / len(prof)
    stations = []
    for y, k in ((-11.5, 0.7), (-9.0, 0.0), (9.0, 0.0), (11.5, 0.7)):
        pts = []
        for x, z in prof:
            dx, dz = x - cx, z - cz
            n = math.hypot(dx, dz) or 1.0
            off = 3.0 * (1.0 - math.sqrt(max(0.0, 1.0 - k * k))) if k else 0.0
            pts.append((-(x - dx / n * off), z - dz / n * off))
        stations.append({"plane": _plane_y(y), "pts": pts})
    return lib.swept_plate(stations)


def _pylon_shoe():
    """Machined foot clamping the pylon to the rear crash structure."""
    body = Pos((-3906.0, 0.0, 366.0)) * Rotation(0, 6, 0) * Box(150.0, 44.0, 26.0)
    return lib.safe_fillet(body, body.edges().filter_by(Axis.X), (6.0, 4.0, 2.0))


# ==========================================================================
# BEAM WING — two elements, arched over the rear crash structure
# ==========================================================================

_BEAM_TIP_Y = spec.BEAM_WING_HALF_SPAN + 8.0
_BEAM_YS = (0.0, 60.0, 130.0, 210.0, 290.0, 360.0, 410.0, _BEAM_TIP_Y)


def _beam_arch(y: float) -> float:
    """Centre lift so the beam wing clears the rear crash structure (z<=380)."""
    t = spec.smoothstep(min(abs(y) / 210.0, 1.0))
    return lib.taper(24.0, 0.0, t)


def _beam_station(y: float, upper: bool) -> dict:
    s = spec.smoothstep(min(abs(y) / _BEAM_TIP_Y, 1.0))
    arch = _beam_arch(y)
    r = max(0.0, min(1.0, (abs(y) - (spec.BEAM_WING_HALF_SPAN - 14.0)) / 22.0))
    if upper:
        # rhythm rule: chord and gap step down by the spec progressions
        chord = spec.BEAM_WING_CHORD * spec.CHORD_RATIO
        le_x = spec.BEAM_WING_X - 78.0 - 10.0 * s
        le_z = spec.BEAM_WING_Z + 42.0 + arch + 4.0 * s
        twist = lib.taper(27.0, 21.0, s)
        cam = lib.taper(0.062, 0.050, s)
    else:
        chord = spec.BEAM_WING_CHORD
        le_x = spec.BEAM_WING_X - 12.0 * s
        le_z = spec.BEAM_WING_Z + arch + 3.0 * s
        twist = lib.taper(16.0, 11.5, s)
        cam = lib.taper(0.072, 0.058, s)
    return {
        "le": (le_x, y, le_z + spec.TIP_ROLL_R * 0.4 * r * r),
        "chord": chord * lib.taper(1.0, 0.86, s) * (1.0 - 0.18 * r * r),
        "twist": twist,
        "thickness": 0.086 * (1.0 - 0.26 * r),
        "camber": cam,
        "camber_pos": 0.40,
        "samples": 45,
    }


def _beam_element(upper: bool):
    ys = [-y for y in reversed(_BEAM_YS[1:])] + list(_BEAM_YS)
    return _wing([_beam_station(y, upper) for y in ys])


# ==========================================================================
# MAINPLANE TIP RIB — closes the carbon element, carries the bellcrank
# ==========================================================================


def _plane_y(y: float) -> Plane:
    """Plane normal to Y: local +x = car -X (rearward), local +y = car +Z."""
    return Plane(origin=(0.0, y, 0.0), x_dir=(-1, 0, 0), z_dir=(0, 1, 0))


def _uv(pts):
    """Car (x, z) -> (u, v) in a `_plane_y` plane."""
    return [(-x, z) for x, z in pts]


def _tip_rib(y_in: float = _MAIN_TIP_Y - 5.0, y_out: float = _RIB_OUT_Y):
    """Machined closing rib: the mainplane's section, plus a bracket that drops
    forward and down to carry spec.DRS_CRANK_PIVOT."""
    st = _main_station(_MAIN_TIP_Y, roll=False)
    lx, _, lz = st["le"]
    cd, ud = _chord_dir(st["twist"]), _up_dir(st["twist"])
    c = st["chord"]

    def on(u_frac, v):
        p = Vector(lx, 0.0, lz) + cd * (c * u_frac) + ud * v
        return (p.X, p.Z)

    prof = [
        on(0.00, 0.0), on(0.14, 7.6), on(0.36, 8.4), on(0.62, 6.2),
        on(0.86, 3.0), on(0.995, 0.4), on(0.86, -3.6), on(0.62, -8.0),
        on(0.40, -11.0),
        # bracket: sweeps forward and down to the bellcrank bearing
        (-3928.0, 812.0), (-3908.0, 792.0),
        (spec.DRS_CRANK_PIVOT[0] - 13.0, spec.DRS_CRANK_PIVOT[2] - 12.0),
        (spec.DRS_CRANK_PIVOT[0] + 14.0, spec.DRS_CRANK_PIVOT[2] - 8.0),
        (spec.DRS_CRANK_PIVOT[0] + 17.0, spec.DRS_CRANK_PIVOT[2] + 14.0),
        (-3898.0, 824.0),
        on(0.10, -7.0), on(0.03, -3.0),
    ]
    stations = []
    for y, k in ((y_in, 0.55), (y_in + 2.5, 0.0), (y_out - 2.5, 0.0), (y_out, 0.55)):
        pts = []
        cx = sum(p[0] for p in prof) / len(prof)
        cz = sum(p[1] for p in prof) / len(prof)
        for x, z in prof:
            dx, dz = x - cx, z - cz
            n = math.hypot(dx, dz) or 1.0
            off = 2.4 * (1.0 - math.sqrt(max(0.0, 1.0 - k * k))) if k else 0.0
            pts.append((-(x - dx / n * off), z - dz / n * off))
        stations.append({"plane": _plane_y(y), "pts": pts})
    return lib.swept_plate(stations)


def _tip_tie():
    """Slender blade tying the tip rib's trailing edge out to the endplate.

    Runs ABOVE the pushrod's swept envelope (which tops out at z 827 at this
    station) so the wing's trailing-edge line reads continuous into the
    endplate instead of stopping in mid-air — rubric item 5. Its outboard end
    is aimed to die exactly INTO the endplate's diagonal top-rear cut, which is
    the edge that line is handing off to.
    """
    st = _main_station(_MAIN_TIP_Y, roll=False)
    lx, _, lz = st["le"]
    te = Vector(lx, 0.0, lz) + _chord_dir(st["twist"]) * (st["chord"] * 0.90)
    return lib.blade_member(
        (te.X + 4.0, _MAIN_TIP_Y - 4.0, te.Z),
        (te.X + 18.0, _EP_IN_Y + 8.0, te.Z + 4.0),
        26.0, 20.0, thickness_ratio=0.30,
    )


# ==========================================================================
# DRS FLAP HARDWARE — pivot bosses and the drive lug
# ==========================================================================


def _y_cylinder(x: float, y0: float, y1: float, z: float, r: float):
    """Cylinder about the Y axis, spanning y0..y1 at station (x, z)."""
    return (
        Location((x, 0.5 * (y0 + y1), z))
        * Rotation(-90, 0, 0)
        * Cylinder(r, abs(y1 - y0))
    )


def _pivot_boss(y0: float, y1: float, r: float):
    return _y_cylinder(spec.DRS_PIVOT[0], y0, y1, spec.DRS_PIVOT[2], r)


def _drs_lug():
    """Blade hanging from the flap's underside to spec.DRS_LUG_CLOSED."""
    a = math.radians(spec.DRS_LUG_ANGLE_CLOSED_DEG)
    root = Vector(
        spec.DRS_PIVOT[0] + 9.0 * math.cos(a),
        spec.DRS_LINK_Y,
        spec.DRS_PIVOT[2] + 9.0 * math.sin(a),
    )
    tip = Vector(*spec.DRS_LUG_CLOSED)
    mid = root + (tip - root) * 0.55 + Vector(-3.0, 0.0, 3.0)
    return lib.blade_path(
        [root, mid, tip], [30.0, 24.0, 18.0], thickness_ratio=0.34, samples=21
    )


def _lug_eye():
    return (
        Location(spec.DRS_LUG_CLOSED)
        * Rotation(-90, 0, 0)
        * Cylinder(10.0, 15.0)
    )


# ==========================================================================
# DRS ACTUATOR — the jewellery
# ==========================================================================

_CP = Vector(*spec.DRS_CRANK_PIVOT)
_CE = Vector(*spec.DRS_CRANK_END_CLOSED)
_LUG = Vector(*spec.DRS_LUG_CLOSED)


def _bellcrank():
    """Machined titanium rocker with sculpted lightening cuts.

    Hub on spec.DRS_CRANK_PIVOT; the drive arm reaches exactly
    spec.DRS_CRANK_END_CLOSED and sweeps FORWARD of the mainplane leading edge
    on its way there. A second, shorter arm takes the actuator pushrod.
    """
    def polar(deg, r):
        a = math.radians(deg)
        return (_CP.X + r * math.cos(a), _CP.Z + r * math.sin(a))

    # (angle, radius) walked monotonically once around the hub. The drive arm
    # peaks at spec.DRS_CRANK_ANGLE_CLOSED_DEG / spec.DRS_CRANK_R + a 5 mm cap
    # so the rod-end eye sits inside solid metal; the short arm at ~318 deg
    # takes the actuator ram.
    outline = (
        (88.0, 24.0), (98.0, 30.0), (106.0, 44.0), (111.0, 58.0),
        (114.0, 66.0), (118.0, spec.DRS_CRANK_R + 5.0), (122.0, 66.0),
        (126.0, 56.0), (132.0, 42.0), (140.0, 34.0), (152.0, 31.0),
        (170.0, 31.0), (190.0, 32.0), (210.0, 33.0), (230.0, 33.0),
        (250.0, 32.0), (268.0, 32.0), (285.0, 34.0), (300.0, 39.0),
        (312.0, 44.0), (322.0, 45.0), (332.0, 40.0),
        (344.0, 31.0), (356.0, 27.0), (370.0, 24.0), (390.0, 22.0),
        (410.0, 21.0), (428.0, 22.0),
    )
    prof = [polar(a, r) for a, r in outline]
    stations = []
    for y, k in ((452.0, 0.6), (454.4, 0.0), (469.6, 0.0), (472.0, 0.6)):
        cx = sum(p[0] for p in prof) / len(prof)
        cz = sum(p[1] for p in prof) / len(prof)
        pts = []
        for x, z in prof:
            dx, dz = x - cx, z - cz
            n = math.hypot(dx, dz) or 1.0
            off = 2.0 * (1.0 - math.sqrt(max(0.0, 1.0 - k * k))) if k else 0.0
            pts.append((-(x - dx / n * off), z - dz / n * off))
        stations.append({"plane": _plane_y(y), "pts": pts})
    crank = lib.swept_plate(stations)

    # sculpted lightening cuts — radiused, like a real machined rocker
    for deg, r, rad in ((118.0, 41.0, 6.0), (118.0, 27.0, 7.5),
                        (205.0, 23.0, 6.5), (318.0, 27.0, 6.0)):
        cx, cz = polar(deg, r)
        cut = Location((cx, spec.DRS_LINK_Y, cz)) * Rotation(-90, 0, 0) * Cylinder(rad, 60.0)
        try:
            out = crank - cut
            if out is not None and out.is_valid:
                crank = out
        except Exception:
            continue
    return crank


def _crank_hub():
    return (
        Location((_CP.X, spec.DRS_LINK_Y, _CP.Z))
        * Rotation(-90, 0, 0)
        * Cylinder(15.0, 30.0)
    )


def _crank_accent_ring():
    """THE accent on the whole rear wing: one vermillion ring on the bearing."""
    outer = (
        Location((_CP.X, spec.DRS_LINK_Y + 15.4, _CP.Z))
        * Rotation(-90, 0, 0)
        * Cylinder(14.6, 3.0)
    )
    bore = (
        Location((_CP.X, spec.DRS_LINK_Y + 15.4, _CP.Z))
        * Rotation(-90, 0, 0)
        * Cylinder(10.4, 9.0)
    )
    try:
        ring = outer - bore
        if ring is not None and ring.is_valid:
            return ring
    except Exception:
        pass
    return outer


def _link_rod():
    """Polished pushrod, exactly spec.DRS_LINK_L between its rod-end centres."""
    d = (_LUG - _CE).normalized()
    a = _CE + d * 15.0
    b = _LUG - d * 15.0
    return lib.blade_member(a, b, 15.0, 15.0, thickness_ratio=0.62, samples=21)


def _rod_end(center: Vector, toward: Vector):
    """Spherical rod end: polished ball in an anodized housing."""
    d = (toward - center).normalized()
    housing_a = center - d * 4.0
    housing_b = center + d * 17.0
    housing = lib.blade_member(housing_a, housing_b, 20.0, 13.0,
                               thickness_ratio=0.70, samples=17)
    ball = Location(tuple(center)) * Sphere(6.4)
    return housing, ball


def _actuator_body():
    """Compact electro-hydraulic actuator on the endplate inner face.

    Sits 46 mm further aft than the flow of the linkage alone would suggest:
    the endplate's raked leading edge passes x = -3880 at this height, and an
    actuator ahead of that line would poke out of the front of the plate.
    """
    axis_a = Vector(-3920.0, 494.0, 740.0)
    axis_b = Vector(-3998.0, 494.0, 724.0)
    body = lib.blade_member(axis_a, axis_b, 58.0, 46.0, thickness_ratio=0.86,
                            samples=25)
    cap_a = (
        Location(tuple(axis_a + (axis_a - axis_b).normalized() * 3.0))
        * Rotation(-90, 0, 0)
        * Cylinder(19.0, 26.0)
    )
    cap_b = (
        Location(tuple(axis_b + (axis_b - axis_a).normalized() * 2.0))
        * Rotation(-90, 0, 0)
        * Cylinder(16.0, 24.0)
    )
    # short pushrod from the actuator to the bellcrank's lower arm
    a2 = math.radians(spec.DRS_CRANK_ANGLE_CLOSED_DEG - 140.0)
    lower_arm = Vector(_CP.X + 21.0 * math.cos(a2), spec.DRS_LINK_Y,
                       _CP.Z + 21.0 * math.sin(a2))
    ram = lib.blade_member(Vector(-3930.0, 486.0, 744.0), lower_arm,
                           13.0, 11.0, thickness_ratio=0.72, samples=17)
    return body, cap_a, cap_b, ram


def _actuator_mount():
    plate = Location((-3958.0, 512.0, 734.0)) * Rotation(0, 8, 0) * Box(120.0, 12.0, 74.0)
    return lib.safe_fillet(plate, plate.edges().filter_by(Axis.Y), (10.0, 6.0, 3.0))


# ==========================================================================
# PUBLIC BUILDERS
# ==========================================================================


def build_rear_wing():
    """Static rear wing: mainplane, tip ribs, endplates, swan-neck pylon."""
    bodies = [lib.styled(_mainplane(), "rw_mainplane", spec.CARBON)]

    bodies += lib.pair(_tip_rib(), "rw_main_tip_rib", spec.TITANIUM)
    bodies += lib.pair(_tip_tie(), "rw_tip_tie", spec.CARBON)
    bodies += lib.pair(_endplate(), "rw_endplate", spec.CARBON_GLOSS)
    bodies += lib.pair(_footplate_curl(), "rw_footplate_curl", spec.CARBON)
    for i, strake in enumerate(_endplate_strakes()):
        bodies += lib.pair(strake, f"rw_endplate_strake_{i + 1}", spec.CARBON)
    bodies += lib.pair(_endplate_foot(), "rw_endplate_foot", spec.CARBON)

    bodies.append(lib.styled(_pylon(), "rw_pylon", spec.CARBON))
    bodies.append(lib.styled(_pylon_neck(), "rw_pylon_neck", spec.CARBON))
    bodies.append(lib.styled(_pylon_shoe(), "rw_pylon_shoe", spec.ANODIZED))
    return lib.group("rear_wing", bodies)


def build_drs_flap():
    """ONLY the flap that rotates — modelled in its CLOSED pose."""
    bodies = [lib.styled(_flap_element(), "drs_flap_element", spec.CARBON)]

    # machined pivot bosses at each end, running out into the endplate
    bodies += lib.pair(_pivot_boss(_FLAP_TIP_Y - 10.0, _EP_IN_Y + 5.0, 11.5),
                       "drs_pivot_boss", spec.TITANIUM)
    bodies += lib.pair(_pivot_boss(_EP_IN_Y + 5.0, _EP_IN_Y + 13.0, 15.0),
                       "drs_pivot_collar", spec.ANODIZED)

    bodies += lib.pair(_drs_lug(), "drs_lug", spec.TITANIUM)
    bodies += lib.pair(_lug_eye(), "drs_lug_eye", spec.ANODIZED)
    return lib.group("drs_flap", bodies)


def build_drs_actuator():
    """ONLY the linkage that drives the flap. Mirrored on both sides."""
    bodies = []
    bodies += lib.pair(_bellcrank(), "drs_bellcrank", spec.TITANIUM)
    bodies += lib.pair(_crank_hub(), "drs_crank_hub", spec.ALLOY)
    bodies += lib.pair(_crank_accent_ring(), "drs_crank_ring", spec.ACCENT)

    bodies += lib.pair(_link_rod(), "drs_link", spec.ALLOY)

    h_crank, b_crank = _rod_end(_CE, _LUG)
    h_lug, b_lug = _rod_end(_LUG, _CE)
    bodies += lib.pair(h_crank, "drs_rodend_crank", spec.ANODIZED)
    bodies += lib.pair(b_crank, "drs_ball_crank", spec.ALLOY)
    bodies += lib.pair(h_lug, "drs_rodend_lug", spec.ANODIZED)
    bodies += lib.pair(b_lug, "drs_ball_lug", spec.ALLOY)

    body, cap_a, cap_b, ram = _actuator_body()
    bodies += lib.pair(body, "drs_actuator_body", spec.ANODIZED)
    bodies += lib.pair(cap_a, "drs_actuator_cap_fwd", spec.ALLOY)
    bodies += lib.pair(cap_b, "drs_actuator_cap_aft", spec.ALLOY)
    bodies += lib.pair(ram, "drs_actuator_ram", spec.ALLOY)
    bodies += lib.pair(_actuator_mount(), "drs_actuator_mount", spec.ANODIZED)
    return lib.group("drs_actuator", bodies)


def build_beam_wing():
    """Two elements, arched over the rear crash structure, tips into the feet."""
    return lib.group("beam_wing", [
        lib.styled(_beam_element(upper=False), "beam_lower", spec.CARBON),
        lib.styled(_beam_element(upper=True), "beam_upper", spec.CARBON),
    ])
