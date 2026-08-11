"""Front wing: mainplane + four flaps, endplates, cascades, mounting pillars.

The whole part is one idea: a five-element cascade whose chord, slot gap and
incidence all step through the geometric progressions in `spec`, wrapped by a
sculpted endplate that curls outboard at the bottom and rolls over at the top.

Two rules make the cascade READ rather than merely exist:

  * every slot gap is TRUE DAYLIGHT. `spec.cascade_gaps` is measured from the
    element's own upper surface at the overlap station, not from its chord
    line, so a stated 24 mm gap is 24 mm of visible air and not 24 mm minus
    whatever the section happened to be doing there.
  * the cascade OPENS OUTBOARD. One law (`_open`) drives both the slot scale
    and the chordwise step, so the stack is tight and neutral where the nose
    needs the air undisturbed and steps up in clear layers everywhere the eye
    actually looks. The flaps are cut off inboard on a rhythmic progression,
    which is what lets you count five elements from the front.

Spanwise the wing is a SPOON: near-flat through the neutral central section
(mainplane only, |y| < 150), washing in to full incidence over |y| = 160..730,
then rolling down hard into the endplate so the topmost flap's tip trailing
edge dies exactly on the endplate's rear diagonal instead of poking out of it.
"""

from __future__ import annotations

import math

from . import lib, spec

# ==========================================================================
# cascade rhythm — every number below comes out of spec's progressions
# ==========================================================================

_CHORDS = spec.cascade_chords(spec.FW_ROOT_CHORD, spec.FW_ELEMENTS)
_GAPS = spec.cascade_gaps(spec.FW_ROOT_GAP, spec.FW_ELEMENTS)
_INC = spec.FW_INCIDENCE_DEG

#: Each flap's leading edge sits this far along the chord of the element below,
#: measured from that element's own leading edge. Constant element-to-element
#: (so the slots read as one repeated interval), but the whole cascade OPENS
#: outboard: root -> outboard. At the root the stack has to clear x = 1000 with
#: full 300 mm chords, so it stays packed; outboard the chords have shrunk and
#: the elements can stand apart.
_OVERLAP = (0.335, 0.455)

#: Multiplier on `spec.cascade_gaps`, root -> outboard. The RATIO between
#: successive gaps is spec's; this only scales the whole progression so the
#: slots are legible at normal viewing distance. At the tip the gaps are the
#: single biggest consumer of the 300 mm endplate-height budget, which is what
#: caps this number.
_GAP_K = (1.28, 1.55)

#: incidence retained in the neutral central section (fraction of the peak)
_NEUTRAL_FRAC = 0.30

_LE_SWEEP = 78.0  # mainplane LE rake, centreline -> tip
_TIP_CHORD_K = 0.53  # chord scale at the endplate
#: Outboard end of every element. It has to land in the MIDDLE of the endplate
#: panel's 9 mm thickness — pushed out toward the outer face the tips ghost
#: through it, and the endplate's outer face is the one the camera sees.
_SPAN_TIP = spec.FW_HALF_SPAN + 1.5  # 986.5, panel spans 982.3..991.3

#: Inboard end of each element. The mainplane runs the full span; the flaps are
#: cut off on a constant 28 mm step so the neutral centre section is mainplane
#: only (the nose pylons rise through it untouched) and the four cut ends stand
#: in a row you can count.
_ROOT_Y = (0.0, 150.0, 178.0, 206.0, 234.0)

# section family: the mainplane is the thickest / least cambered, each flap
# gets thinner and more aggressively cambered as the cascade climbs.
_THICK = (0.108, 0.092, 0.084, 0.078, 0.072)
_CAMBER = (0.052, 0.060, 0.066, 0.072, 0.078)
_CAMBER_POS = (0.42, 0.40, 0.38, 0.36, 0.35)

_SPAN_FRACS = (0.0, 0.11, 0.22, 0.32, 0.42, 0.52, 0.62, 0.72, 0.82, 0.92, 1.0)
_YS = [-f * _SPAN_TIP for f in reversed(_SPAN_FRACS[1:])] + [
    f * _SPAN_TIP for f in _SPAN_FRACS
]

#: station fractions for a flap that starts partway out: clustered at the cut
#: end (so the chopped tip stays crisp) and at the roll-off into the endplate.
_FLAP_FRACS = (
    0.0, 0.018, 0.055, 0.115, 0.20, 0.30, 0.41, 0.52, 0.63, 0.74, 0.85, 0.94, 1.0
)


def _twist_frac(s: float) -> float:
    """Spanwise wash-in law: flat centre, loaded mid-span, unloaded tip."""
    if s <= 0.16:
        return 0.0
    if s < 0.74:
        return spec.smoothstep((s - 0.16) / 0.58)
    # Unload HARD into the tip. This is not decoration: at full incidence the
    # topmost flap's tip trailing edge lands above and behind the endplate's
    # rear diagonal and sticks out of it. Rolling the outboard flaps down is
    # both what stops that and what a real front wing does at the tip.
    return 1.0 - 0.45 * spec.smoothstep((s - 0.74) / 0.26)


def _open(s: float) -> float:
    """How far the cascade has opened at span fraction s (0 = packed, 1 = full)."""
    return spec.smoothstep((s - 0.16) / 0.46)


def _chord_scale(s: float) -> float:
    return 1.0 - (1.0 - _TIP_CHORD_K) * spec.smoothstep((s - 0.18) / 0.72)


def _upper_offset(chord, thickness, camber, camber_pos, frac, te) -> float:
    """Height of an element's UPPER surface above its own chord line, in mm.

    Sampled from `lib`'s own section maths so the slot gap can be stated as
    real daylight. These sections are strongly cambered the downforce way, so
    the answer is small and sometimes negative — which is exactly why measuring
    the gap from the chord line (as this module used to) quietly ate most of it.
    """
    upper, _ = lib._naca_points(chord, thickness, camber, camber_pos, 61, te)
    xt = frac * chord
    for (x0, y0), (x1, y1) in zip(upper, upper[1:]):
        if x0 <= xt <= x1:
            u = (xt - x0) / max(x1 - x0, 1e-9)
            return y0 + (y1 - y0) * u
    return upper[-1][1]


def _station(y: float) -> list[dict]:
    """The whole five-element stack at one spanwise station, in car coords."""
    s = min(abs(y) / spec.FW_HALF_SPAN, 1.0)
    x = spec.FW_LE_X - _LE_SWEEP * s**1.7
    # the mainplane LE hangs LOW through the loaded mid-span and only lifts
    # into the endplate at the very tip — it buys the cascade the height it
    # needs under FW_ENDPLATE_TOP_Z, and it is what ground effect looks like
    z = spec.FW_Z_ROOT + (spec.FW_Z_TIP - spec.FW_Z_ROOT) * s**2.2
    k = _chord_scale(s)
    w = _twist_frac(s)
    o = _open(s)
    ov = spec.lerp(_OVERLAP[0], _OVERLAP[1], o)
    gk = spec.lerp(_GAP_K[0], _GAP_K[1], o)

    out = []
    for i in range(spec.FW_ELEMENTS):
        a = _INC[i] * (_NEUTRAL_FRAC + (1.0 - _NEUTRAL_FRAC) * w)
        c = _CHORDS[i] * k
        th = _THICK[i] * (1.0 - 0.10 * s)
        out.append(
            {
                "le": (x, y, z),
                "chord": c,
                "twist": a,
                "thickness": th,
                "camber": _CAMBER[i],
                "camber_pos": _CAMBER_POS[i],
                "te": spec.TE_THICKNESS,
            }
        )
        if i < spec.FW_ELEMENTS - 1:
            ar = math.radians(a)
            # chordwise (rearward) and surface-normal (up) unit vectors
            ux, uz = -math.cos(ar), math.sin(ar)
            nx, nz = math.sin(ar), math.cos(ar)
            # stand off this element's own upper surface, then open the slot
            surf = _upper_offset(
                c, th, _CAMBER[i], _CAMBER_POS[i], ov, spec.TE_THICKNESS
            )
            g = surf + _GAPS[i] * gk
            x += ov * c * ux + g * nx
            z += ov * c * uz + g * nz
    return out


def _span_ys(y0: float) -> list[float]:
    return [y0 + (_SPAN_TIP - y0) * f for f in _FLAP_FRACS]


def _element_stations(i: int) -> list[dict]:
    """Stations for element `i`, on the LEFT side (the mainplane spans both)."""
    ys = _YS if i == 0 else _span_ys(_ROOT_Y[i])
    return [_station(y)[i] for y in ys]


# ==========================================================================
# the one accent: a trim band wrapped over the topmost flap's trailing edge
# ==========================================================================


#: the trim owns the last 7% of the topmost flap's chord — the flap is lofted
#: short and blunt, and this wedge finishes it. Butting the two rather than
#: overlaying a decal keeps the visible trailing edge exactly TE_THICKNESS and
#: leaves no near-coincident surfaces to shimmer.
_ACCENT_FRAC = 0.07
_ACCENT_CUT_T = 0.020  # blunt cut thickness, as a fraction of chord


def _tip_flap_stations(stations: list[dict]) -> list[dict]:
    return [
        dict(
            st,
            chord=st["chord"] * (1.0 - _ACCENT_FRAC),
            te=st["chord"] * _ACCENT_CUT_T,
        )
        for st in stations
    ]


def _te_accent(stations: list[dict]):
    secs = []
    for st in stations:
        c = st["chord"]
        c0 = c * (1.0 - _ACCENT_FRAC)  # where the carbon stops
        h = c * _ACCENT_CUT_T / 2.0  # half the blunt cut it plugs into
        d = c - c0
        e = spec.TE_THICKNESS / 2.0
        secs.append(
            {
                "plane": lib.section_plane(st["le"], twist_deg=st["twist"]),
                "pts": [
                    (c0, h),
                    (c0 + d * 0.40, h * 0.84),
                    (c0 + d * 0.75, h * 0.62),
                    (c, e),
                    (c, -e),
                    (c0 + d * 0.75, -h * 0.62),
                    (c0 + d * 0.40, -h * 0.84),
                    (c0, -h),
                ],
            }
        )
    return lib.swept_plate(secs)


# ==========================================================================
# endplate — straight runs meeting at tight radii, not a rounded slab
# ==========================================================================

#: The endplate is the widest thing on the car, so it is packaged against
#: `spec.HALF_WIDTH`, not against a local allowance. Nothing here may cross
#: y = 999. The footplate curl, the top roll and the outwash strake each stand
#: proud of the panel's outer face, and all three have to fit in what is left.
#
# THE ENDPLATE IS THREE BODIES, AND THAT IS DELIBERATE. Modelling it as one
# ribbon swept along x — panel, footplate curl and top roll in a single
# cross-section — does not survive `loft`: the section is a 300 mm band 7 mm
# thick containing two 90 deg turns, and OCC returns either a solid with a
# fifth of the right volume or "BRep_API: command not done". Split into a
# panel lofted ACROSS the span (big, well-conditioned closed sections) plus two
# SHORT swept bands for the curl and the roll, every loft is easy and each
# feature gets crisper control than the single ribbon ever gave.
#
_EP_Y_IN = 982.3  # panel inner face
_EP_Y_OUT = 991.3  # panel outer face
_EP_Y_MID = (_EP_Y_IN + _EP_Y_OUT) / 2.0
_EP_EDGE_R = 3.4  # bull-nose on the panel's cut edges
_EP_ROLL_CY = 993.6  # centre of the top roll
_EP_ROLL_R = 6.5  # outer roll radius ~ spec.TIP_ROLL_R with the band thickness
_EP_FOOT_CY = 988.0  # where the footplate turns up
_EP_FOOT_R = 6.0  # footplate curl radius
_EP_X_FRONT = 1396.0
_EP_X_REAR = 1058.0
_EP_STATIONS = 23

#: Side-view outline as STRAIGHT RUNS between corner knots in t (t = 0 at the
#: leading edge, 1 at the trailing edge). `_polyline` rounds each corner over a
#: 10 mm window, which is the whole point: a hard-raked leading edge, a level
#: crest, and a crisp diagonal cut across the top-rear corner.
_EP_TOP = ((0.0, 150.0), (0.235, 295.0), (0.780, 295.0), (1.0, 238.0))
_EP_BOT = ((0.0, 102.0), (0.31, 46.0), (0.70, 53.0), (1.0, 106.0))
#: inboard reach of the footplate — it grows out of the leading edge, holds,
#: and dies into the trailing edge rather than fading out mid-panel
_EP_FOOT_IN = ((0.0, 984.0), (0.10, 977.0), (0.34, 964.0), (0.86, 962.0), (1.0, 970.0))
#: footplate section thickness: feathered at the nose, full, thinned at the tail
_EP_FOOT_TMUL = ((0.0, 0.42), (0.14, 1.0), (0.80, 1.0), (1.0, 0.50))
#: the roll lip lives on the CREST only, and stops dead in the two corners
#: where the raked leading edge and the diagonal rear cut take over the edge
_EP_ROLL_T0, _EP_ROLL_T1 = 0.238, 0.598


def _line(seg, t: float) -> float:
    (t0, z0), (t1, z1) = seg
    return z0 + (z1 - z0) * (t - t0) / (t1 - t0)


def _polyline(t: float, knots, blend: float = 0.030) -> float:
    """Piecewise-linear f(t) through `knots`, corners rounded over ±`blend`.

    Straight runs stay straight — which is what stops the endplate reading as
    one continuous rounded blob — and every corner is a tight, deliberate
    radius instead of a smoothstep that eats a third of the panel.
    """
    segs = list(zip(knots, knots[1:]))
    idx = 0
    for i, (a, _b) in enumerate(segs):
        if t >= a[0]:
            idx = i
    z = _line(segs[idx], t)
    if idx > 0:
        t0 = segs[idx][0][0]
        if t < t0 + blend:
            u = spec.smoothstep((t - (t0 - blend)) / (2.0 * blend))
            z = spec.lerp(_line(segs[idx - 1], t), _line(segs[idx], t), u)
    if idx < len(segs) - 1:
        t1 = segs[idx][1][0]
        if t > t1 - blend:
            u = spec.smoothstep((t - (t1 - blend)) / (2.0 * blend))
            z = spec.lerp(_line(segs[idx], t), _line(segs[idx + 1], t), u)
    return z


def _ep_z_top(t: float) -> float:
    return _polyline(t, _EP_TOP)


def _ep_z_bot(t: float) -> float:
    return _polyline(t, _EP_BOT)


def _ep_x(t: float) -> float:
    return spec.lerp(_EP_X_FRONT, _EP_X_REAR, t)


def _catmull(pts, n: int, alpha: float = 0.5):
    """CENTRIPETAL Catmull-Rom resample of a control polygon.

    Centripetal, not uniform. This polygon deliberately mixes 60 mm panel runs
    with 5 mm steps round the roll, and uniform Catmull-Rom answers that with a
    cusp on the short segment — which then folds the offset band through itself
    and the endplate will not loft at all. The first two components are treated
    as the geometry; any further components (thickness) ride along.
    """
    p = list(pts)
    head = tuple(2 * p[0][i] - p[1][i] for i in range(len(p[0])))
    tail = tuple(2 * p[-1][i] - p[-2][i] for i in range(len(p[0])))
    P = [head] + p + [tail]
    ts = [0.0]
    for a, b in zip(P, P[1:]):
        ts.append(ts[-1] + max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-6) ** alpha)

    d = len(P[0])
    out = []
    for k in range(n):
        u = ts[1] + (ts[-2] - ts[1]) * k / (n - 1)
        i = 1
        while i < len(P) - 3 and u > ts[i + 1]:
            i += 1
        t0, t1, t2, t3 = ts[i - 1], ts[i], ts[i + 1], ts[i + 2]
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        row = []
        for c in range(d):
            a1 = ((t1 - u) * p0[c] + (u - t0) * p1[c]) / max(t1 - t0, 1e-9)
            a2 = ((t2 - u) * p1[c] + (u - t1) * p2[c]) / max(t2 - t1, 1e-9)
            a3 = ((t3 - u) * p2[c] + (u - t2) * p3[c]) / max(t3 - t2, 1e-9)
            b1 = ((t2 - u) * a1 + (u - t0) * a2) / max(t2 - t0, 1e-9)
            b2 = ((t3 - u) * a2 + (u - t1) * a3) / max(t3 - t1, 1e-9)
            row.append(((t2 - u) * b1 + (u - t1) * b2) / max(t2 - t1, 1e-9))
        out.append(tuple(row))
    return out


def _resample(dense, n: int, bend: float = 45.0):
    """Pick `n` points off a dense polyline — sparse on straights, dense in the
    corners.

    This is not a nicety. The endplate section is a 300 mm ribbon containing a
    90 deg curl whose arc is 10 mm long; sample it uniformly and the corner
    gets under one point, the offset normals there are nonsense, and the
    resulting wire lofts into a solid with a fifth of the right volume (valid,
    watertight, and completely wrong). Weighting arc length by turn angle puts
    the points where the shape actually is.
    """
    w = [0.0]
    for i in range(1, len(dense)):
        ds = math.hypot(dense[i][0] - dense[i - 1][0], dense[i][1] - dense[i - 1][1])
        if i < len(dense) - 1:
            ax = dense[i][0] - dense[i - 1][0]
            ay = dense[i][1] - dense[i - 1][1]
            bx = dense[i + 1][0] - dense[i][0]
            by = dense[i + 1][1] - dense[i][1]
            la = math.hypot(ax, ay) or 1e-9
            lb = math.hypot(bx, by) or 1e-9
            cosv = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
            ds += bend * math.acos(cosv)
        w.append(w[-1] + ds)

    out, j = [], 0
    for k in range(n):
        u = w[-1] * k / (n - 1)
        while j < len(w) - 2 and w[j + 1] < u:
            j += 1
        f = (u - w[j]) / max(w[j + 1] - w[j], 1e-12)
        a, b = dense[j], dense[j + 1]
        out.append(tuple(a[c] + (b[c] - a[c]) * f for c in range(len(a))))
    return out


def _band_outline(ctrl, n: int = 46, cap: int = 6):
    """Closed (u, v) outline of a plate of varying thickness following a
    centreline. `ctrl` is a list of (u, v, thickness) control points."""
    sm = _resample(_catmull(ctrl, 360), n)
    pts = [(p[0], p[1]) for p in sm]
    ths = [max(p[2], 0.6) for p in sm]

    nrm = []
    for i in range(len(pts)):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == len(pts) - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(dx, dy) or 1.0
        nrm.append((-dy / L, dx / L))

    left = [
        (pts[i][0] + nrm[i][0] * ths[i] / 2.0, pts[i][1] + nrm[i][1] * ths[i] / 2.0)
        for i in range(len(pts))
    ]
    right = [
        (pts[i][0] - nrm[i][0] * ths[i] / 2.0, pts[i][1] - nrm[i][1] * ths[i] / 2.0)
        for i in range(len(pts))
    ]

    def _cap(idx, start):
        cx, cy = pts[idx]
        r = ths[idx] / 2.0
        a0 = math.atan2(start[1] - cy, start[0] - cx)
        return [
            (cx + r * math.cos(a0 - math.pi * j / cap), cy + r * math.sin(a0 - math.pi * j / cap))
            for j in range(1, cap)
        ]

    return (
        left
        + _cap(len(pts) - 1, left[-1])
        + list(reversed(right))
        + _cap(0, right[0])
    )


def _inset(pts, d: float):
    """Shrink a closed (u, v) outline inward by `d` along its own normals."""
    if d <= 0.0:
        return list(pts)
    n = len(pts)
    a = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
            for i in range(n))
    sign = 1.0 if a > 0 else -1.0
    out = []
    for i in range(n):
        px, py = pts[i - 1]
        qx, qy = pts[(i + 1) % n]
        dx, dy = qx - px, qy - py
        L = math.hypot(dx, dy) or 1.0
        out.append((pts[i][0] - sign * dy / L * d, pts[i][1] + sign * dx / L * d))
    return out


def _ep_outline(inset: float = 0.0, n: int = 46, m: int = 5):
    """Closed side-view outline of the endplate panel, in the section plane's
    local (u, v) = (car +X, car +Z).

    Top edge front-to-rear, down the trailing edge, bottom edge rear-to-front,
    up the raked leading edge. Four deliberate corners, straight runs between.
    """
    top = [(_ep_x(i / (n - 1)), _ep_z_top(i / (n - 1))) for i in range(n)]
    bot = [(_ep_x(i / (n - 1)), _ep_z_bot(i / (n - 1))) for i in range(n)]
    rear = [
        (_EP_X_REAR, spec.lerp(top[-1][1], bot[-1][1], j / m)) for j in range(1, m)
    ]
    front = [
        (_EP_X_FRONT, spec.lerp(bot[0][1], top[0][1], j / m)) for j in range(1, m)
    ]
    return _inset(top + rear + list(reversed(bot)) + front, inset)


def _ep_panel():
    """The panel itself, lofted ACROSS the span so the sections are big closed
    curves rather than a hairline ribbon. The edge rolls off to a bull-nose."""
    lands = (
        (_EP_Y_IN, _EP_EDGE_R),
        (_EP_Y_IN + 1.3, 1.15),
        (_EP_Y_MID, 0.0),
        (_EP_Y_OUT - 1.3, 1.15),
        (_EP_Y_OUT, _EP_EDGE_R),
    )
    secs = [
        {
            "plane": lib.plate_plane((0, y, 0), (0, -1, 0), up=(0, 0, 1)),
            "pts": _ep_outline(inset),
        }
        for (y, inset) in lands
    ]
    return lib.swept_plate(secs)


def _ep_footplate():
    """The footplate: a shelf that reaches inboard under the mainplane, then
    CURLS up and outboard round a 6 mm corner and dies back into the panel."""
    rc = _EP_FOOT_R
    fc = _EP_FOOT_CY
    s45, c45 = math.sin(math.pi / 4), math.cos(math.pi / 4)
    secs = []
    for i in range(_EP_STATIONS):
        t = i / (_EP_STATIONS - 1)
        zb = _ep_z_bot(t)
        yi = _polyline(t, _EP_FOOT_IN)
        fm = max(_polyline(t, _EP_FOOT_TMUL), 0.42)
        ctrl = [
            (yi, zb + 2.0, 4.2 * fm),  # feathered inboard tip
            (0.5 * (yi + fc), zb + 0.4, 6.4 * fm),  # flat underside
            (fc, zb, 7.0 * fm),  # tangent outboard — the curl starts
            (fc + rc * s45, zb + rc * (1 - c45), 7.0 * fm),  # 45 deg
            (fc + rc, zb + rc, 6.6 * fm),  # 90 deg: outboard-most, tangent up
            (fc + rc - 3.0, zb + rc + 11.0, 5.8 * fm),  # dies inside the panel
        ]
        secs.append(
            {
                "plane": lib.plate_plane((_ep_x(t), 0, 0), (1, 0, 0), up=(0, 0, 1)),
                "pts": _band_outline(ctrl, n=26),
            }
        )
    # RULED. The band's arc length changes station to station as the footplate
    # reaches further inboard, so a smooth loft slides material along the
    # section and beads the whole bottom edge. At 15 mm station spacing the
    # ruled patches are flat to well under a degree.
    return lib.swept_plate(secs, ruled=True)


def _ep_roll_lip():
    """The rolled-over top edge: a quarter turn outboard on `spec.TIP_ROLL_R`,
    running the length of the crest and stopping dead in both corners."""
    rr = _EP_ROLL_R
    cy = _EP_ROLL_CY
    s45, c45 = math.sin(math.pi / 4), math.cos(math.pi / 4)
    secs = []
    n = 13
    for i in range(n):
        t = spec.lerp(_EP_ROLL_T0, _EP_ROLL_T1, i / (n - 1))
        zt = _ep_z_top(t)
        ctrl = [
            (_EP_Y_MID, zt - 17.0, 6.2),  # buried in the panel
            (cy - rr, zt - rr, 6.8),  # tangent up — the roll starts
            (cy - rr * c45, zt - rr + rr * s45, 6.4),  # 45 deg
            (cy, zt, 5.4),  # 90 deg — the lip, pointing outboard
        ]
        secs.append(
            {
                "plane": lib.plate_plane((_ep_x(t), 0, 0), (1, 0, 0), up=(0, 0, 1)),
                "pts": _band_outline(ctrl, n=22),
            }
        )
    return lib.swept_plate(secs, ruled=True)


# ==========================================================================
# outwash strake — a raised tunnel on the outer face, not a blister
# ==========================================================================

#: (t, z) of the ridge crest. The front station sits ON the raked leading edge
#: and the rear one ON the trailing edge, so the tunnel runs off the panel at
#: both ends instead of fading out in the middle of it.
_STRAKE_PATH = (
    (0.088, 195.0),
    (0.220, 191.0),
    (0.350, 184.0),
    (0.480, 174.0),
    (0.610, 162.0),
    (0.740, 149.0),
    (0.870, 137.0),
    (0.985, 126.0),
)
_STRAKE_Y = 990.6  # base plane, a hair inside the panel's outer face
#: proud height and across-the-plate width, station by station
_STRAKE_H = (1.6, 4.6, 5.9, 6.4, 6.4, 6.0, 4.8, 2.0)
_STRAKE_L = (13.0, 26.0, 36.0, 42.0, 42.0, 37.0, 28.0, 15.0)


def _strake_path():
    return [(_ep_x(t), _STRAKE_Y, z) for (t, z) in _STRAKE_PATH]


def _outwash_strake():
    """Raised tunnel on the endplate's outer face that turns flow around the
    front tyre. Square-shouldered — steep side walls and a flat crown — so it
    casts an edge instead of reading as a soft swelling in the panel."""
    path = _strake_path()
    n = len(path)
    secs = []
    for i, p in enumerate(path):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        d = (b[0] - a[0], 0.0, b[2] - a[2])
        h, half = _STRAKE_H[i], _STRAKE_L[i] / 2.0
        secs.append(
            {
                # local +y = car +Y (outboard), local +x runs across the ridge
                "plane": lib.plate_plane(p, d, up=(0, 1, 0)),
                "pts": [
                    (-half, -3.2),
                    (-half, h * 0.52),
                    (-half * 0.88, h * 0.96),
                    (-half * 0.42, h),
                    (half * 0.42, h),
                    (half * 0.88, h * 0.96),
                    (half, h * 0.52),
                    (half, -3.2),
                    (half * 0.45, -4.4),
                    (-half * 0.45, -4.4),
                ],
            }
        )
    return lib.swept_plate(secs)


# ==========================================================================
# upper cascade — two rhythmic winglets off the inner face of the endplate
# ==========================================================================

_CASC_YS = (846.0, 872.0, 898.0, 924.0, 950.0, 972.0, 990.0)
_CASC_CHORD = 64.0
_CASC_INC = (22.0, 33.0)
#: the pair is spaced on the same rhythm as the main cascade but opened up, so
#: from head-on you read two elements with daylight between them, not a block
_CASC_OVERLAP = 0.72
_CASC_GAP = 24.0


def _cascade_stations():
    lower, upper = [], []
    for y in _CASC_YS:
        u = (y - _CASC_YS[0]) / (_CASC_YS[-1] - _CASC_YS[0])
        x = 1332.0 - 16.0 * u
        z = 208.0 + 14.0 * u
        c = _CASC_CHORD * (1.0 - 0.26 * u)
        a = spec.lerp(_CASC_INC[0], _CASC_INC[0] + 6.0, u)
        lower.append(
            {
                "le": (x, y, z),
                "chord": c,
                "twist": a,
                "thickness": 0.062,
                "camber": 0.086,
                "camber_pos": 0.34,
                "te": spec.TE_THICKNESS,
            }
        )
        ar = math.radians(a)
        bx = x + _CASC_OVERLAP * c * -math.cos(ar) + _CASC_GAP * math.sin(ar)
        bz = z + _CASC_OVERLAP * c * math.sin(ar) + _CASC_GAP * math.cos(ar)
        upper.append(
            {
                "le": (bx, y, bz),
                "chord": c * spec.CHORD_RATIO,
                "twist": a + (_CASC_INC[1] - _CASC_INC[0]),
                "thickness": 0.058,
                "camber": 0.094,
                "camber_pos": 0.33,
                "te": spec.TE_THICKNESS,
            }
        )
    return lower, upper


# ==========================================================================
# wing pillars — the pylons the nose comes down onto
# ==========================================================================


#: HANDSHAKE WITH THE NOSE. The nose's laminated pylon pad is flat over
#: |y| = 38..90 at x = 1250, top face z = 200; outboard of |y| ~ 90 the nose
#: skin drops to z = 204..218 and a pylon would clash into it. So the upper end
#: of each pylon sits exactly on |y| = 64 — the centre of that pad. The flaps
#: are cut off at |y| = 150, so the pylon now rises through clear air.
_PYLON_TOP = (1250.0, 64.0, 200.0)


def _pillar():
    """Slender pylon from the mainplane upper surface to the nose's pad.

    The first segment is deliberately near-vertical: `blade_path` hangs each
    section normal to the local path, so a raked root would tip the chord and
    drop the trailing end of the section out through the mainplane underside.
    """
    return lib.blade_path(
        [(1288.0, 56.0, 76.0), (1282.0, 60.0, 138.0), _PYLON_TOP],
        (96.0, 82.0, 64.0),
        thickness_ratio=0.17,
    )


# ==========================================================================


def build_front_wing():
    bodies = []

    # element 0 spans the whole car; the flaps are left-side bodies mirrored by
    # lib.pair, because each is cut off inboard on its own station.
    bodies.append(
        lib.styled(
            lib.wing_element(_element_stations(0)), "fw_mainplane", spec.CARBON_GLOSS
        )
    )

    # alternating gloss / satin carbon so consecutive elements separate in value
    flap_colors = (spec.CARBON, spec.CARBON_GLOSS, spec.CARBON, spec.CARBON_GLOSS)
    last = spec.FW_ELEMENTS - 1
    for i in range(1, spec.FW_ELEMENTS):
        st = _element_stations(i)
        if i == last:
            # the topmost flap stops 7% short and blunt; the accent trim finishes it
            bodies += lib.pair(
                lib.wing_element(_tip_flap_stations(st)),
                f"fw_flap_{i}",
                flap_colors[i - 1],
            )
            # THE accent — one thin vermillion band on the topmost trailing edge
            bodies += lib.pair(_te_accent(st), "fw_te_trim", spec.ACCENT)
        else:
            bodies += lib.pair(lib.wing_element(st), f"fw_flap_{i}", flap_colors[i - 1])

    bodies += lib.pair(_ep_panel(), "fw_endplate", spec.CARBON_GLOSS)
    bodies += lib.pair(_ep_footplate(), "fw_footplate", spec.CARBON)
    bodies += lib.pair(_ep_roll_lip(), "fw_endplate_roll", spec.CARBON)
    bodies += lib.pair(_outwash_strake(), "fw_outwash_strake", spec.CARBON_WEAVE)

    casc_lo, casc_hi = _cascade_stations()
    bodies += lib.pair(lib.wing_element(casc_lo), "fw_cascade_lower", spec.CARBON_WEAVE)
    bodies += lib.pair(lib.wing_element(casc_hi), "fw_cascade_upper", spec.CARBON_WEAVE)

    bodies += lib.pair(_pillar(), "fw_pillar", spec.CARBON)

    return lib.group("front_wing", bodies)


# --------------------------------------------------------------------------
# INCIDENCE GOES THROUGH `twist`.
#
# This module was originally written against a `lib.section_plane()` whose
# `twist_deg` silently yawed the section instead of pitching it (build123d's
# `Plane.rotated()` composes in WORLD axes), so incidence was routed through
# `sweep_deg` as a workaround. `lib.section_plane()` has since been rebuilt
# from explicit direction vectors and `twist_deg` now does what it says, so
# the workaround is gone and the station dicts carry plain `twist`.
