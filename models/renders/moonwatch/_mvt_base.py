"""Movement base cluster: main plate, barrel + ratchet/crown/click, going
train, bridges, escapement, and balance assembly for the caliber-321-lineage
movement. Frame: MOVEMENT local (see `_spec.py`) — bridge side up, z = 0 at
the plate's bridge-side face.

Exposes `build_base()` -> list of labeled/colored parts, plus module-level
plan-outline constants (documented below) that the chronograph-works builder
imports READ-ONLY to route its levers around these bridges.

Bridge outlines are `_Outline` silhouettes: ONE smooth closed B-spline in
movement XY traced through control points (tapered necks between jewel
bosses, flared screwed feet, long rim-following sweeps — the individually
contoured cocks of the real 321, not circles blobbed around each jewel).
Anything inside an outline's `.anchors` disks between `BRIDGE_SEAT_Z` and
`BRIDGE_TOP_Z` (or the pallet/cock z-ranges) should be treated as occupied;
`.face(delta)` gives the exact profile. Low polished jewel tables (r 1.15 at
the train `JEWEL_POSITIONS_UPPER` entries) rise a further 0.06 above
`BRIDGE_TOP_Z`; the winding square + ratchet screw reach
`RATCHET_SCREW_TOP_Z` over `BARREL_POS`.

NOTE: `_finishing.py` helpers assume `align=(None,None,None)` centers
primitives; it actually leaves the raw OCC datum (see /BUGS.md). This module
compensates with corrective cuts (countersink cones, full-depth wheel
windows, perlage z-shift) or constructive local replacements (`_screw`:
flat slotted heads — F.slotted_screw's domed cap read as a featureless blob
at macro) while still building on the shared helpers.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Circle,
    Color,
    Cone,
    Cylinder,
    Part,
    Plane,
    Polygon,
    Pos,
    Rot,
    Sphere,
    extrude,
    revolve,
)

import _spec as S
import _finishing as F

# ---------------------------------------------------------------------------
# Smooth bridge silhouettes. The old outlines were unions of circles blobbed
# around each jewel: every concave junction was a scallop cusp and the
# bridges read as beads on a string (blind-critic verdict). Each outline is
# now ONE closed loop of traced control points — a closed Catmull-Rom
# densifies the trace and a single periodic B-spline is fit through the
# samples, so edges flow and concave junctions are drawn smooth (radius
# >= 0.8, no cusps). The smooth profile also lets OCC's 45-degree draft
# prism succeed where the circle-chain cusps made it throw (the old
# per-circle cone-cap fallback is gone). All loops were probe-checked
# against every planted feature (screw sinks, jewel sinks, chrono studs and
# feet, wheel keep-outs, inter-bridge gaps) in a dense-polyline design
# probe before being frozen here.
# ---------------------------------------------------------------------------


def _on(cx, cy, r, deg):
    a = math.radians(deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def _arcpts(cx, cy, r, a0, a1, n):
    """n+1 trace points along a circle arc (degrees, signed sweep)."""
    return [_on(cx, cy, r, a0 + (a1 - a0) * i / n) for i in range(n + 1)]


def _cr(p0, p1, p2, p3, t, dims):
    t2, t3 = t * t, t * t * t
    return tuple(
        0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t
               + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
               + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3)
        for j in range(dims))


def _stroke_pts(spine, n_per=5, cap_pts=5):
    """Closed trace loop of a variable-width stroke: open Catmull-Rom
    through (x, y, r) spine controls, offset both sides by the local
    radius, round end caps — the tapered-finger silhouette of a simple
    cock (head, waisted neck, flared screwed foot)."""
    pts = [spine[0]] + list(spine) + [spine[-1]]
    sp = []
    for k in range(len(spine) - 1):
        for i in range(n_per):
            sp.append(_cr(pts[k], pts[k + 1], pts[k + 2], pts[k + 3],
                          i / n_per, 3))
    sp.append(spine[-1])
    left, right = [], []
    for i, (x, y, r) in enumerate(sp):
        ax, ay, _ = sp[max(i - 1, 0)]
        bx, by, _ = sp[min(i + 1, len(sp) - 1)]
        tx, ty = bx - ax, by - ay
        L = math.hypot(tx, ty) or 1.0
        left.append((x - ty / L * r, y + tx / L * r))
        right.append((x + ty / L * r, y - tx / L * r))

    def cap(c, aa, ab):
        cx, cy, r = c
        return [_on(cx, cy, r, math.degrees(aa + (ab - aa) * i / (cap_pts + 1)))
                for i in range(1, cap_pts + 1)]

    x1, y1, _ = sp[-1]
    aL = math.atan2(left[-1][1] - y1, left[-1][0] - x1)
    aR = math.atan2(right[-1][1] - y1, right[-1][0] - x1)
    while aR > aL:
        aR -= 2 * math.pi
    x0, y0, _ = sp[0]
    aR0 = math.atan2(right[0][1] - y0, right[0][0] - x0)
    aL0 = math.atan2(left[0][1] - y0, left[0][0] - x0)
    while aL0 > aR0:
        aL0 -= 2 * math.pi
    return (left + cap(sp[-1], aL, aR)
            + list(reversed(right)) + cap(sp[0], aR0, aL0))


def _one_face(obj):
    """Normalize a make_face/offset result to a single Face."""
    from build123d import Face
    if isinstance(obj, Face):
        return obj
    faces = obj.faces()
    if len(faces) != 1:
        raise ValueError(f"outline produced {len(faces)} faces, expected 1")
    return faces[0]


def _poly_dist(pt, poly):
    """Distance from a point to a closed polyline."""
    x, y = pt
    best = 1e9
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx
                                                   + (y - y1) * dy) / L2))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


class _Outline:
    """Smooth closed bridge silhouette.

    `loop` — traced boundary control points; a closed Catmull-Rom densifies
    the trace (~0.25 segments) and ONE periodic B-spline is fit through the
    samples. `anchors` — (x, y, r) disks approximating the covered plan
    region, exported for keep-out planning (plate perlage, chrono routing).
    `face(delta)` — the profile face offset outward by `delta` (negative
    shrinks). Offsets are computed NUMERICALLY on the dense samples (point
    + normal * delta, ear-culled) and re-fit with a periodic B-spline:
    OCC's BRepOffsetAPI returns Null on some of these closed spline wires
    (balance cock, probe-verified), so no kernel offset is used at all.
    Faces are cached per delta.
    """

    def __init__(self, loop, anchors):
        self.loop = tuple(loop)
        self.anchors = tuple(anchors)
        self.max_r = max(math.hypot(x, y) for x, y in self.loop)
        n = len(self.loop)
        dense = []
        for k in range(n):
            p1, p2 = self.loop[k], self.loop[(k + 1) % n]
            m = max(2, int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / 0.25) + 1)
            for i in range(m):
                dense.append(_cr(self.loop[(k - 1) % n], p1, p2,
                                 self.loop[(k + 2) % n], i / m, 2))
        # orient CCW so the outward normal convention below holds
        area2 = sum(dense[i][0] * dense[(i + 1) % len(dense)][1]
                    - dense[(i + 1) % len(dense)][0] * dense[i][1]
                    for i in range(len(dense)))
        if area2 < 0:
            dense.reverse()
        self._dense = dense
        self._faces = {}

    def _offset_pts(self, delta):
        pts, n = self._dense, len(self._dense)
        out = []
        for i, (x, y) in enumerate(pts):
            ax, ay = pts[(i - 1) % n]
            bx, by = pts[(i + 1) % n]
            tx, ty = bx - ax, by - ay
            L = math.hypot(tx, ty) or 1.0
            out.append((x + ty / L * delta, y - tx / L * delta))
        # prune swallowtail artifacts: a valid offset point lies at least
        # |delta| from the source polyline; corner loops (offset > corner
        # radius) land closer and are dropped (the classic offset-validity
        # criterion — local crossing detection missed shallow tails,
        # probe-verified on the barrel rim corners)
        out = [p for p in out if _poly_dist(p, pts) >= abs(delta) - 0.02]
        # resample uniformly and lightly smooth: pruning leaves chamfer
        # gaps at corners whose interpolating spline would otherwise kink
        res = []
        for i, p in enumerate(out):
            q = out[(i + 1) % len(out)]
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            m = max(1, int(d / 0.25))
            for k in range(m):
                t = k / m
                res.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        for _ in range(2):
            res = [(0.25 * res[i - 1][0] + 0.5 * x + 0.25 * res[(i + 1) % len(res)][0],
                    0.25 * res[i - 1][1] + 0.5 * y + 0.25 * res[(i + 1) % len(res)][1])
                   for i, (x, y) in enumerate(res)]
        return res

    def face(self, delta=0.0):
        f = self._faces.get(delta)
        if f is None:
            from build123d import Spline, make_face
            pts = self._dense if delta == 0.0 else self._offset_pts(delta)
            f = _one_face(make_face(Spline(*pts, periodic=True)))
            self._faces[delta] = f
        return f


# ---------------------------------------------------------------------------
# Exported layout constants (READ-ONLY for other builders)
# ---------------------------------------------------------------------------

#: Bridges (barrel + train) span this z band; their striped top face is
#: BRIDGE_TOP_Z. The chronograph layer must stay above BRIDGE_TOP_Z except
#: where a plan position is outside every outline below.
BRIDGE_SEAT_Z = S.BRIDGE_SEAT_Z          # 1.8
BRIDGE_TOP_Z = S.BRIDGE_SEAT_Z + S.BRIDGE_THICKNESS  # 2.85

#: Barrel bridge: broad kidney plate — the rim arc sweeps the north half,
#: then ONE long S lower edge runs east from the west flank under the brake
#: studs, over the train-bridge center finger, dips SOUTH under the click,
#: the column-wheel seat and the minute-recorder head (the plate owns the
#: whole winding quadrant down to y ~ 1.3), out to the east rim corner.
BARREL_BRIDGE_OUTLINE = _Outline(
    _arcpts(0, 0, 12.80, 3, 143, 10) + [
        (-9.85, 6.55),          # rounded west rim corner (loft validity)
        (-9.4, 5.9), (-7.9, 4.35), (-6.4, 3.1), (-4.9, 1.9), (-2.9, 1.55),
        (-0.7, 2.0), (1.2, 2.25), (3.2, 2.35),
        (4.6, 1.70), (6.2, 1.38), (7.8, 1.30), (9.3, 1.40), (10.4, 1.62),
        (11.42, 2.3), (12.38, 1.5),
        (12.62, 1.05)],         # rounded east rim corner
    anchors=((-1.6, 8.0, 6.0), (6.9, 8.3, 3.9), (4.3, 4.1, 2.6),
             (10.6, 4.2, 3.4), (9.2, 6.6, 3.0), (5.3, 2.6, 1.2),
             (7.6, 2.5, 1.1), (9.6, 2.7, 1.2)))
#: Shallow machined pockets (x, y, r, depth) in the barrel bridge top: the
#: snailed ratchet wheel nests in a circular moat opening (rim r 5.20 around
#: the r 5.0 wheel) and the crown wheel sits in a scalloped notch (r 3.30
#: around the r 3.2 wheel). The two pockets merge into one figure-8
#: winding-works recess and both breach the rim edge — the "purposeful
#: cutout around each wheel" read of the reference; rims carry the same
#: 45-deg bevel + polished ribbon as the outline edges.
BARREL_BRIDGE_RECESSES = ((-1.6, 8.0, 5.20, 0.30), (6.9, 8.3, 3.30, 0.22))
#: Train bridge: a broad crab PLATE — wide body on the west rim, one wide
#: finger sweeping through the third boss to the center jewel with its south
#: edge scalloped around the balance (bulged out at the timing-screw
#: azimuths, dipping between them), one wide finger to the escape jewel; a
#: round window between the bosses reveals the third/fourth wheel teeth.
TRAIN_BRIDGE_OUTLINE = _Outline(
    [(-11.6, 3.6), (-10.4, 3.45), (-9.4, 2.6), (-8.7, 1.7), (-8.3, 1.05),
     (-7.2, 1.1), (-5.9, 1.0), (-4.6, 0.75), (-3.4, 0.5),
     (-2.5, 0.7), (-1.6, 1.0)]
    + _arcpts(0, 0, 1.68, 112, -100, 6)
    + [(-1.2, -2.2),
       _on(-0.4, -7.6, 5.42, 112.0), _on(-0.4, -7.6, 5.42, 123.75),
       _on(-0.4, -7.6, 5.00, 135.0), _on(-0.4, -7.6, 5.52, 146.25)]
    + _arcpts(-7.6, -5.2, 1.78, 20, -150, 5)
    + [(-9.9, -5.7), (-10.9, -5.8)]
    + _arcpts(0, 0, 12.80, 208, 164, 4),
    anchors=((0.0, 0.0, 1.7), (-2.2, -1.1, 1.7), (-3.6, -1.9, 1.9),
             (-5.0, -2.6, 2.1), (-6.5, -3.6, 1.9), (-7.6, -5.2, 1.8),
             (-6.0, 0.1, 1.3), (-7.4, 0.1, 1.4), (-8.85, -2.55, 1.7),
             (-10.2, 0.0, 2.0), (-10.5, 2.2, 1.7), (-11.0, -4.4, 1.8),
             (-9.7, -4.4, 1.5), (-12.2, -1.5, 1.4), (-9.4, 1.6, 1.2)))
#: Circles SUBTRACTED from the train-bridge outline (wheel-reveal window
#: over the third/fourth wheel teeth; rim gets the bevel + ribbon).
TRAIN_BRIDGE_CUTOUTS = ((-8.85, -2.55, 1.25),)
#: Pallet bridge (z PALLET_BRIDGE_Z): small waisted cock, jewel head to
#: screwed foot.
PALLET_BRIDGE_OUTLINE = _Outline(
    _stroke_pts([(-4.9, -7.2, 1.26), (-5.35, -8.02, 0.78),
                 (-5.9, -8.9, 1.24)]),
    anchors=((-4.9, -7.2, 1.26), (-5.35, -8.02, 0.78), (-5.9, -8.9, 1.24)))
#: Balance cock (z COCK_Z): one tapered finger — round head over the shock
#: setting, waisted neck, foot flaring along the rim — with the stud-holder
#: lobe blended smoothly into the head's east flank.
BALANCE_COCK_OUTLINE = _Outline(
    _arcpts(-0.4, -7.6, 2.0, -25, 220, 8)
    + [(-1.85, -9.81), (-2.38, -11.05), (-3.10, -11.55)]
    + _arcpts(0, 0, 13.12, 258, 275, 2)
    + [(1.30, -11.75), (0.80, -10.55), (0.70, -10.15)]
    + _arcpts(1.5, -9.22, 1.13, -118, 82, 5),
    anchors=((-0.4, -7.6, 2.0), (-0.5, -8.9, 1.45), (-0.62, -9.9, 1.18),
             (-0.78, -11.2, 1.55), (-0.9, -12.3, 2.3), (1.5, -9.22, 1.13)))
#: Nominal bridge rim radii (the outlines' rim arcs are traced at these).
BRIDGE_CLIP_R = 12.85
COCK_CLIP_R = 13.2

PALLET_BRIDGE_Z = (1.6, 1.96)            # pallet cock z band
COCK_Z = (2.7, 3.25)                     # balance cock plate z band
COCK_SHOCK_TOP_Z = 3.4                   # lyre-spring shock setting apex

#: Blued bridge screws: label -> (x, y). Screw heads sit at the owning
#: bridge's top surface; keep chronograph levers clear of a 1.1 mm radius.
#: Four screws shifted <= 0.4 from the round-1 spots so the smooth outlines'
#: necks and rim arcs keep full sink coverage (the old barrel:left spot was
#: 0.58 OUTSIDE its circle-chain outline — the screw floated off the edge).
#: barrel:top moved to the west wing: its old (1.6, 11.3) spot is inside the
#: ratchet moat recess AND under the r 5.0 ratchet wheel — the proud head
#: (top 2.91) clipped the wheel web (bottom 2.88) by 0.03, probe-caught.
BRIDGE_SCREW_POSITIONS = {
    "barrel_bridge:left": (-7.65, 9.59),
    "barrel_bridge:right": (11.2, 3.4),
    "barrel_bridge:top": (-8.9, 7.4),
    "train_bridge:foot": (-11.03, -4.26),
    "train_bridge:fourth": (-11.2, 2.15),
    "train_bridge:center": (-2.75, -0.95),
    "pallet_bridge": (-5.9, -8.9),
    "balance_cock": (-0.83, -12.87),
}
#: Upper (bridge-top) jewel positions: label -> (x, y).
JEWEL_POSITIONS_UPPER = {
    "center": S.CENTER_WHEEL_POS,
    "third": S.THIRD_WHEEL_POS,
    "fourth": S.FOURTH_WHEEL_POS,
    "escape": S.ESCAPE_WHEEL_POS,
    "barrel": S.BARREL_POS,
    "pallet": S.PALLET_FORK_POS,
}
#: Ratchet / crown wheel occupy z [RATCHET_Z0, RATCHET_TOP_Z] above the
#: barrel bridge; the raised winding square + blued screw reach
#: RATCHET_SCREW_TOP_Z (chronograph levers must clear a 1.3 mm radius there).
RATCHET_Z0 = 2.88
RATCHET_TOP_Z = 3.14
RATCHET_SQUARE_TOP_Z = 3.46
RATCHET_SCREW_TOP_Z = 3.58
BALANCE_RIM_Z = (2.0, 2.45)              # balance rim ring z band (r 4.1..4.8)

# --- internal z plan -------------------------------------------------------
_DRUM_Z = (0.4, 1.45)                    # barrel drum wall
_FLANGE_Z = (1.435, 1.735)               # barrel tooth flange (top of drum)
_CW_Z = 0.2                              # center wheel web mid z
_CP_Z = (1.25, 1.75)                     # center pinion
_TP_Z = (0.05, 0.60)                     # third pinion
_TW_Z = 0.88                             # third wheel web mid z
_FP_Z = (0.70, 1.30)                     # fourth pinion
_FW_Z = 1.40                             # fourth wheel web mid z
_EP_Z = (1.25, 1.72)                     # escape pinion
_EW_Z = 1.12                             # escape wheel web mid z
_FORK_Z = (1.28, 1.43)                   # pallet fork plate

# --- mesh-driven diameters (tip circles reach partner pinion roots) --------
_BARREL_GEAR_D = 13.65                   # 80 t, meshes center pinion
_CENTER_PINION_D = 4.2                   # 12 leaves
_CENTER_WHEEL_D = 9.6                    # 64 t, meshes third pinion
_THIRD_PINION_D = 2.6
_THIRD_WHEEL_D = 10.0                    # 60 t, meshes fourth pinion
_FOURTH_PINION_D = 2.53
_FOURTH_WHEEL_D = 9.71                   # 70 t, meshes escape pinion
_ESCAPE_PINION_D = 3.0
_ESCAPE_WHEEL_D = 5.4                    # 15 club teeth

_ARBOR_R = 0.30


def _cyl(r, h, z0):
    """Cylinder spanning z [z0, z0 + h] (default centered primitive)."""
    return Pos(0, 0, z0 + h / 2.0) * Cylinder(r, h)


def _ring(ri, ro, h, z0):
    return Pos(0, 0, z0) * extrude(Circle(ro) - Circle(ri), amount=h)


def _blob(circles, clip_r, cutouts=()):
    """2D union of (x, y, r) circles clipped to a disk about the origin.

    ONE multi-operand fuse, clip LAST: pairwise 2D `+` decays once operands
    stop overlapping (the balance-cock STRIPE INSET went disjoint at the stud
    lobe, its `& Circle` clip returned silently EMPTY, and the cock shipped
    with no striping cut at all — same failure class as /BUGS.md's keyless
    entry)."""
    discs = [Pos(x, y) * Circle(r) for x, y, r in circles]
    prof = discs[0] + discs[1:] if len(discs) > 1 else discs[0]
    prof = prof & Circle(clip_r)
    for x, y, r in cutouts:
        prof = prof - Pos(x, y) * Circle(r)
    return prof


def _ang(frm, to):
    return math.degrees(math.atan2(to[1] - frm[1], to[0] - frm[0]))


def _finish(part, label, color):
    part.label = label
    part.color = Color(*color)
    return part


# Stripe-shadow tone: spec COPPER_GOLD_DEEP sits only ~0.04 above COPPER_GOLD
# and vanished inside the key light's specular pool (render-verified), so the
# overlay uses the same hue scaled to a true groove shadow.
_STRIPE_SHADOW_COLOR = tuple(0.62 * c for c in S.COPPER_GOLD_DEEP[:3]) + (1.0,)


def _add_shadow(parts, shadow, label):
    """Append a bridge's stripe-shadow overlay (a list of connected solids),
    one part per solid: the clipped alternate bands are disjoint arcs, and a
    single multi-solid part would trip validation the way the tangent
    escape-wheel teeth did. Solids are used directly — Part(sol.wrapped)
    loses .volume (reports 0 on build123d 0.10) and risks being dropped by
    volume-filtering exporters."""
    if not shadow:
        return
    if len(shadow) == 1:
        parts.append(_finish(shadow[0], f"{label}:stripe_shadow",
                             _STRIPE_SHADOW_COLOR))
        return
    for i, sol in enumerate(shadow):
        parts.append(_finish(sol, f"{label}:stripe_shadow:{i}",
                             _STRIPE_SHADOW_COLOR))


# Polished-anglage ribbon tone: the constructive 45-deg bevels share the
# bridge COPPER_GOLD and the renderer applies uniform material properties, so
# the geometry rendered invisibly (blind critic: "raw extruded edges"). The
# ribbon overlay carries the mirror-polish read purely by tone. The first
# pass (0.88, 0.66, 0.46) was still hue-adjacent to COPPER_GOLD and washed
# into the same specular pool at macro (blind critic round 7: "no polished
# anglage chamfer"); this near-white warm-gold mirror tone stays clearly
# distinct from the striped tops at any angle. Inline by design (not a spec
# finish color: it stands in for specular pickup, not a material).
_ANGLAGE_COLOR = (0.97, 0.82, 0.62, 1.0)


def _add_anglage(parts, ribbon, label):
    """Append a bridge's polished-bevel ribbon overlay (list of connected
    solids), one part per solid — same pattern/rationale as `_add_shadow`
    (disjoint arcs in one part trip validation; `Part(sol.wrapped)` loses
    `.volume` on build123d 0.10, see /BUGS.md)."""
    if not ribbon:
        return
    if len(ribbon) == 1:
        parts.append(_finish(ribbon[0], f"{label}:anglage", _ANGLAGE_COLOR))
        return
    for i, sol in enumerate(ribbon):
        parts.append(_finish(sol, f"{label}:anglage:{i}", _ANGLAGE_COLOR))


def _screw(head_d=S.SCREW_HEAD_DIAMETER, hh=0.34, shank=0.8,
           slot_w=None, slot_angle=0.0, color=S.BLUED):
    """Flat mirror-top slotted screw, head top at z = 0, shank hanging below.

    Fully constructive local replacement for F.slotted_screw: its domed cap
    (a 2.6r sphere intersection) rendered as a featureless glossy blob at
    macro — no flat disc for the key light, so the slot never read. Here the
    head is a flat-top cylinder with a small bright 45-deg rim chamfer baked
    in as a truncated-cone cap (no OCC chamfer), and ONE full-width slot cut
    at `slot_angle` deep enough to read as a crisp dark line across the
    light-catching disc. Slot floor stays inside the head so the part is one
    solid at every head height."""
    r = head_d / 2.0
    if slot_w is None:
        slot_w = 0.20 * head_d                # 0.26 at the 1.3 spec head
    ch = min(0.09, 0.30 * hh, 0.25 * r)       # bright 45-deg rim chamfer
    depth = min(0.22, hh - 0.06)              # 0.22 at the 0.34 spec head
    head = _cyl(r, hh - ch, -hh) + Pos(0, 0, -ch / 2) * Cone(r, r - ch, ch)
    shank_p = _cyl(0.275 * head_d, shank + 0.05, -hh - shank)
    slot = Rot(0, 0, slot_angle) * Box(head_d + 0.6, slot_w, 2 * depth)
    s = (head + shank_p) - slot
    s.color = Color(*color)
    return s


def _place_screw(x, y, surface_z, proud=0.06, slot_angle=None, **kw):
    """Screw with its flat head top `proud` above `surface_z`. Slot angle is
    a fixed pseudo-random function of position — like a serviced movement,
    every slot points its own way, none of them animated/parametric."""
    if slot_angle is None:
        slot_angle = (x * 47.9 + y * 83.3) * 57.29578 % 180.0
    return Pos(x, y, surface_z + proud) * _screw(slot_angle=slot_angle, **kw)


def _sink_tool(cone_r=0.97, wall_r=0.72, cone_z=0.20, seat_z=0.60, bore_r=0.45):
    """Polished jewel countersink cutter, target surface at z=0: a SHALLOW
    inverted conical ring (opening cone_r at the surface, narrowing to wall_r
    at depth cone_z — the bright polished ring of a real sink), a cylindrical
    seat counterbore holding chaton + jewel, then the through bore. Built
    locally: F.jewel_countersink_cut's cone is half above the surface AND
    inverted (raw-OCC-datum bug, /BUGS.md), so at any parameterization its
    opening bulges widest just under the rim — it cannot produce the
    countersink-ring read of a real jewel setting."""
    tool = (Pos(0, 0, -cone_z / 2 + 0.001) * Cone(wall_r, cone_r, cone_z)
            + _cyl(wall_r, seat_z, -seat_z))
    return tool + _cyl(bore_r, 3.0, -3.0)


def _ruby_disc(r=0.46, t=0.30, ch=0.05, hole_r=0.14):
    """Ruby jewel disc, rim at z=0 with a polished dome cap (apex +0.14):
    cylinder body + the spherical cap through the z=0 rim circle. The first
    flat-top pass killed F.jewel's oversized proud bead but overshot into
    "flat decal", and the 0.08 sag that replaced it still read as "flat
    magenta discs" at macro (blind critic round 8) — 0.14 over a 0.9 dia is
    the visibly crowned stone that catches one bright point highlight.
    Callers compensate the extra 0.06 sag by seating the rim deeper
    (~0.11-0.12 under the surrounding face) so every apex stays at its
    proven clearance height while the curvature doubles. The optional
    pivot-hole bore (dark oil-sink dot) pierces the dome. (`ch` kept for
    signature stability; the dome supersedes the old flat-top edge
    chamfer.)"""
    h = 0.14
    c = (h * h - r * r) / (2.0 * h)          # sphere center z (below rim)
    dome = Pos(0, 0, c) * Sphere(h - c) & _cyl(r, h + 0.05, 0.0)
    body = _cyl(r, t, -t) + dome
    if hole_r > 0:
        body = body - _cyl(hole_r, t + 0.3, -t - 0.1)
    return body


def _grain(span_l, span_w, cx, cy, z_top, angle, clip=None):
    """Directional satin-grain tools: F.straight_grain_cutter's V-groove
    field (surface at z=0, grooves along X) rotated so the grain runs along
    `angle` (degrees), centered at (cx, cy) with the finished surface at
    z_top. Returns a LIST for one multi-tool subtract. With `clip` (a solid),
    the tools are fused and intersected with it first — REQUIRED wherever
    overshoot would carve internal voids (recess floors inside a thicker
    solid) or nick a polished anglage bevel (grain stays off bevels)."""
    tools = [Pos(cx, cy, z_top) * Rot(0, 0, angle) * t
             for t in F.straight_grain_cutter(span_l, span_w)]
    if clip is None:
        return tools
    fused = tools[0] + tools[1:] if len(tools) > 1 else tools[0]
    return [fused & clip]


def _window_cutter(od, frac):
    """Full-depth replica of F.train_wheel's crossing-out cutter (the helper
    only cuts the top half of every spoke window; see /BUGS.md)."""
    r_o = od / 2.0
    r_root = r_o - r_o * frac
    rim_inner = r_root - od * 0.10
    hub = max(1.4, od * 0.14)
    spoke_w = max(0.5, od * 0.045)
    ring = _cyl(rim_inner, 1.2, -0.6) - _cyl(hub / 2.0 + 0.4, 1.4, -0.7)
    spokes = []
    for k in range(5):
        sp = Rot(0, 0, 72.0 * k) * (Pos(rim_inner * 1.025, spoke_w / 2.0, 0)
                                    * Box(rim_inner * 2.05, spoke_w, 1.6))
        spokes.append(sp)
    return ring - spokes


# ---------------------------------------------------------------------------
# Bridge factory: loft the smooth outline with its baked 45-deg anglage,
# circular stripes about (0,0), raised polished jewel bosses, jewel
# countersinks + polished screw sinks, all in batched booleans.
# ---------------------------------------------------------------------------

# Jewel "boss" flattened to a low polished table: the old r1.5 x 0.14 raised
# donut + domed jewel bulged like beads at macro; real settings are flush
# discs in shallow conical sinks with at most a slightly proud polished table.
_BOSS_R = 1.15                           # polished table radius around a sink
_BOSS_H = 0.06                           # table rise above the striped top
# Circular-striping V grooves about (0,0): depth sets the facet slope that
# makes the stripes READ under the presentation light. Facet angle is
# atan(depth / (groove_width/2)): 0.07 -> 4.3 deg invisible, 0.13 -> 8 deg
# washed out, 0.22 -> ~13 deg still lost in one specular pool at macro
# (blind A/B verdict); 0.40 -> ~23 deg matches the ratchet snailing's ~20 deg
# facets, the one cut texture that DID read in that A/B. Capped per bridge so
# thin cocks are not pierced.
_STRIPE_DEPTH = 0.40
# 45-deg bevel, a touch wide of the 0.22 spec minimum: at 0.30 the bright
# band was ~2 px at the presentation framing and never read (blind critic
# round 7), but the 0.42 counter-swing turned the slimmed spline bridges
# into "uniform mirror-chrome rims" (round 8) — the ribbon ate ~40% of the
# narrow necks. 0.26 keeps a legible chamfer LINE tracing every contour
# while staying <= 25% of the thinnest visible top width.
_BRIDGE_ANGLAGE = 0.26


def _bevel_extrude(outline, z0, z1, w):
    """Extrude an outline with a TRUE 45-degree top-perimeter anglage baked
    into the construction: straight walls to z1 - w, then a 45-degree
    tapered cap. OCC `chamfer` cannot cut this ring — F.anglage_top's
    whole-list retry shrank or dropped bevels, single-edge chamfers refuse
    concave junctions, and grouped chamfers after neighbors exist SEGFAULT
    OCC (see /BUGS.md). Baking the bevel also means every later boolean
    (stripes, sinks) cannot erase it. Built as ONE 3-section ruled loft
    (wall, wall, inward offset): fusing a straight extrude with a separate
    cap returned EMPTY on the barrel outline — OCC BOP glue failure on the
    coincident spline-bounded face pair (probe-verified)."""
    from build123d import loft
    f = outline.face(0.0)
    return loft([Pos(0, 0, z0) * f, Pos(0, 0, z1 - w) * f,
                 Pos(0, 0, z1) * outline.face(-w)], ruled=True)


def _cap(outline, z1, w):
    """The 45-degree tapered cap of `_bevel_extrude` spanning [z1 - w, z1]:
    a RULED LOFT between the profile and its inward numeric offset.
    LocOpe_DPrism (extrude taper=45) throws on every one of these dense
    periodic-spline profiles (BRepFill_TrimSurfaceTool 'incoherent
    intersection' / NCollection errors, probe-verified), so the loft IS the
    primary path; outline rim corners carry explicit rounding points where
    a sharp corner made the ruled surface fold (barrel,
    BRepCheck-verified)."""
    from build123d import loft
    return loft([Pos(0, 0, z1 - w) * outline.face(0.0),
                 Pos(0, 0, z1) * outline.face(-w)], ruled=True)


def _bridge(outline, z0, z1, jewel_xy, screw_xy, cutouts=(), recesses=(),
            extra_cuts=(), stripe=True, boss_xy=(), jewel_sink_kw=None,
            boss_sink_kw=None):
    """Returns (bridge_body, stripe_shadow_or_None, anglage_ribbon_or_None).
    `recesses` — (x, y, r, depth) shallow machined pockets in the top face
    (wheel seats / winding moats): full circular rim with the same 45-deg
    bevel + polished ribbon as the through-cutouts, but the floor stays at
    z1 - depth so the plate below keeps carrying its bores and jewels.
    Pockets may overlap each other (merged figure-8 moat) and may breach the
    outer wall (scalloped notch): ribbons are clipped to the plan silhouette
    and carved by sibling pockets so nothing floats in a void.
    The anglage ribbon is a ~0.03-thick polished skin over the 45-deg bevel
    loop (outline + wheel-reveal rims). The stripe shadow is a
    0.035 skin over every SECOND stripe band (COPPER_GOLD_DEEP two-tone
    assist): even at ~23-degree facets the presentation light's specular pool
    still washed the narrow train-bridge / cock fields flat at macro, so the
    alternating-band read is carried by tone as well as slope, exactly like
    the darker/lighter alternation of real cotes de Geneve."""
    bevel_w = _BRIDGE_ANGLAGE if (z1 - z0) >= 0.5 else S.ANGLAGE_WIDTH
    body = _bevel_extrude(outline, z0, z1, bevel_w)

    if boss_xy:
        adds = []
        for x, y in boss_xy:
            adds.append(Pos(x, y, 0) * (
                _cyl(_BOSS_R, z1 - z0, z0)
                + Pos(0, 0, z1 + _BOSS_H / 2) * Cone(_BOSS_R, _BOSS_R - _BOSS_H,
                                                     _BOSS_H)))
        body = body + adds

    cuts = list(extra_cuts)
    for x, y, r in cutouts:
        # wheel-reveal cutout with its own 45-deg anglage ring at the rim
        cuts.append(Pos(x, y, 0) * (
            _cyl(r, z1 - z0 + 1.0, z0 - 0.5)
            + Pos(0, 0, z1 - bevel_w / 2) * Cone(r, r + bevel_w, bevel_w)))
    recess_tools = []
    for x, y, r, d in recesses:
        # shallow machined pocket: floor at z1 - d, beveled rim like a cutout
        tool = Pos(x, y, 0) * (
            _cyl(r, d + 1.0, z1 - d)
            + Pos(0, 0, z1 - bevel_w / 2) * Cone(r, r + bevel_w, bevel_w))
        recess_tools.append(tool)
        cuts.append(tool)
    for x, y in jewel_xy:
        cuts.append(Pos(x, y, z1) * _sink_tool(**(jewel_sink_kw or {})))
    for x, y in boss_xy:
        cuts.append(Pos(x, y, z1 + _BOSS_H) * _sink_tool(**(boss_sink_kw or {})))
    for x, y in screw_xy:
        # sink hugs the 1.3 head (0.07 ring + 0.13 flare): the old 1.75/2.1
        # flare read as one 2.2 mm "screw" blob at macro
        sink = _cyl(0.72, 0.30, -0.30) + Pos(0, 0, -0.05) * Cone(0.72, 0.85, 0.10)
        cuts.append(Pos(x, y, z1) * sink
                    + Pos(x, y, 0) * _cyl(0.45, z1 - z0 + 1.0, z0 - 0.5))

    shadow = None
    if stripe:
        depth = min(_STRIPE_DEPTH, 0.55 * (z1 - z0))
        rings = F.snailing_cutter(2 * outline.max_r + 2.0, 2.4,
                                  pitch=S.GENEVA_STRIPE_PITCH,
                                  groove_depth=depth, groove_width=1.85)
        # stripe field runs right up to the bevel: the band extrusion below
        # clips every groove inside this inset face, so the ribbon can never
        # be scalloped and only a hairline flat separates it from the first
        # V — the striped two-tone field owns the whole remaining top (the
        # old 0.08 margin on top of the 0.42 bevel left a bare copper border
        # that read as part of the chrome rim)
        m = bevel_w + 0.02
        inset = outline.face(-m)
        for x, y, r in cutouts:
            inset = inset - Pos(x, y) * Circle(r + m)
        for x, y, r, _d in recesses:
            # keep the grooves off the pocket rim bevel AND the pocket floor
            # (the 0.4 V's are deeper than the shallow floors)
            inset = inset - Pos(x, y) * Circle(r + m)
        for x, y in boss_xy:
            inset = inset - Pos(x, y) * Circle(_BOSS_R + 0.05)
        for x, y in jewel_xy:
            # keep the stripe grooves off the polished sink cone: the 0.4-deep
            # V's are deeper than the 0.2 cone and would scallop its rim
            inset = inset - Pos(x, y) * Circle(
                (jewel_sink_kw or {}).get("cone_r", 0.97) + 0.15)
        # band must reach below the deepest V (0.3 clipped the 0.4 grooves
        # into flat-bottomed slots, killing the facet read)
        band = Pos(0, 0, z1 - depth - 0.1) * extrude(inset, amount=depth + 0.2)
        # two-tone assist: thin skins over alternate V bands, same profile
        # as the cutter so they lie exactly on the striped facets
        w2 = 1.85 / 2.0
        shells = []
        r, k = 3.1, 0        # first snailing_cutter ring at inner/2 + pitch
        while r < outline.max_r + 1.0:
            if k % 2 == 0:
                hexp = Plane.XZ * Polygon(
                    (r - w2, 0.02), (r, -depth), (r + w2, 0.02),
                    (r + w2, 0.055), (r, -depth + 0.035), (r - w2, 0.055),
                    align=None)
                shells.append(revolve(hexp, Axis.Z))
            r += S.GENEVA_STRIPE_PITCH
            k += 1
        if shells:
            skin = (Pos(0, 0, z1) * (shells[0] + shells[1:])) & band
            # the clip can return a mixed-dimension compound (stray faces
            # along coincident boundaries); keep only the solids. NOTE: do
            # not re-wrap as Part(solid.wrapped) — that reports volume 0 on
            # build123d 0.10 and the guard below would discard real bands.
            sols = skin.solids()
            if sols:
                fused = sols[0] if len(sols) == 1 else sols[0] + sols[1:]
                trimmed = fused - cuts
                if hasattr(trimmed, "solids"):
                    pieces = list(trimmed.solids())
                else:                      # Solid - [tools] -> ShapeList
                    pieces = [s for shp in trimmed for s in shp.solids()]
                shadow = [s for s in pieces if s.volume > 1e-6] or None
        cuts.append((Pos(0, 0, z1) * rings) & band)

    # polished anglage ribbon: the body's OWN 45-deg cap translated UP by
    # d = 0.07 * sqrt(2) and clipped back to z1 — a 45-deg cone translated
    # vertically by d coincides with the same cone grown horizontally by d,
    # so this is the ~0.07-normal-thickness skin over the bevel WITHOUT a
    # second loft (the grown-profile loft pair folded/invalidated on the
    # barrel outline, BRepCheck-verified). Minus the body and the same
    # cuts it can never bury or erase the baked bevel, tops out flush at
    # z1 (leaving the ~0.1 flush bright ring inside the bevel's top edge).
    # Wheel-reveal cutout rims get the mirrored treatment: the cut's own
    # flare cone minus an INWARD-shifted copy, a shell living inside the
    # cut void so it cannot interpenetrate the bridge (its own cut tool
    # would erase it if it went through the shared `cuts` subtraction).
    rib_d = 0.07 * math.sqrt(2.0)
    clip = Pos(0, 0, z1 - (bevel_w + 1.0) / 2) * Box(
        2 * outline.max_r + 4.0, 2 * outline.max_r + 4.0, bevel_w + 1.0)
    outer = (Pos(0, 0, rib_d) * _cap(outline, z1, bevel_w)) & clip
    ribs = [outer - ([body] + cuts)]
    for x, y, r in cutouts:
        ribs.append(Pos(x, y, z1 - bevel_w / 2) * (
            Cone(r, r + bevel_w, bevel_w)
            - Cone(r - rib_d, r + bevel_w - rib_d, bevel_w)))
    if recesses:
        # pocket-rim ribbons: same shell-in-the-void construction as the
        # cutout rims, but clipped to the plan silhouette (a pocket may
        # breach the outer wall) and carved by sibling pockets (merged
        # moats) so no ribbon arc floats over open air
        prism = Pos(0, 0, z1 - bevel_w - 0.2) * extrude(
            outline.face(-bevel_w), amount=bevel_w + 0.4)
        for i, (x, y, r, d) in enumerate(recesses):
            ring = Pos(x, y, z1 - bevel_w / 2) * (
                Cone(r, r + bevel_w, bevel_w)
                - Cone(r - rib_d, r + bevel_w - rib_d, bevel_w))
            ring = ring & prism
            others = [t for j, t in enumerate(recess_tools) if j != i]
            if others:
                ring = ring - others
            ribs.append(ring)
    ribbon = [s for shp in ribs for s in shp.solids()
              if s.volume > 1e-4] or None
    return body - cuts, shadow, ribbon


# ---------------------------------------------------------------------------
# 1. Main plate (perlage, recesses, bosses, lower jewels)
# ---------------------------------------------------------------------------

def _plate_parts():
    parts = []
    plate = _cyl(S.MOVEMENT_DIAMETER / 2.0, S.PLATE_THICKNESS, -S.PLATE_THICKNESS)
    rim_edges = [e for e in plate.edges()
                 if abs(e.bounding_box().max.Z) < 1e-6
                 or abs(e.bounding_box().min.Z + S.PLATE_THICKNESS) < 1e-6]
    plate, _ = F.safe_chamfer(plate, rim_edges, 0.15)

    bx, by = S.BARREL_POS
    lx, ly = S.BALANCE_POS

    # bosses/pillars where bridges land (heights limited by wheel clearances)
    # + a crescent platform under the balance-cock foot (relieved around the
    # balance rim sweep so the wheel spins free below the cock)
    foot_prof = ((Pos(-0.9, -12.3) * Circle(1.9)) & Circle(13.4)
                 - Pos(lx, ly) * Circle(4.95))
    bosses = [
        Pos(-7.65, 9.59, 0) * _cyl(1.1, 1.38, 0),
        Pos(11.2, 3.4, 0) * _cyl(1.1, 1.80, 0),
        Pos(-11.03, -4.26, 0) * _cyl(1.0, 1.25, 0),
        Pos(-11.2, 2.15, 0) * _cyl(1.0, 1.26, 0),
        Pos(-5.9, -8.9, 0) * _cyl(0.8, 1.55, 0),
        extrude(foot_prof, amount=2.70),
    ]
    plate = plate + bosses
    cuts = [
        Pos(bx, by, 0) * _cyl(6.4, 0.55, -0.35),          # barrel recess
        Pos(lx, ly, 0) * _cyl(5.3, 0.50, -0.30),          # balance recess
        _cyl(0.9, 3.0, -1.6),                              # center bore
        Pos(bx, by, 0) * _cyl(0.75, 3.0, -1.6),            # barrel arbor bore
        # radial stem bore at 3 o'clock (keyless builder finishes it)
        Pos(12.2, 0, S.STEM_AXIS_Z_LOCAL) * Rot(0, 90, 0) * Cylinder(0.5, 3.2),
    ]
    # lower train/balance jewels: countersinks open to the dial side
    lower = [S.CENTER_WHEEL_POS, S.THIRD_WHEEL_POS, S.FOURTH_WHEEL_POS,
             S.ESCAPE_WHEEL_POS, S.PALLET_FORK_POS, S.BALANCE_POS]
    for x, y in lower:
        cuts.append(Pos(x, y, -S.PLATE_THICKNESS) * Rot(180, 0, 0) * _sink_tool())

    # perlage over every open bridge-side field (hex grid, keep-out filtered;
    # stamps dropped 0.033 so the helper's z>=0-clipped lens actually bites)
    proto = F.perlage_cutter(0.001, 0.001)[0]
    keep_out = [(x, y, r - 0.45) for x, y, r in
                (BARREL_BRIDGE_OUTLINE.anchors + TRAIN_BRIDGE_OUTLINE.anchors
                 + PALLET_BRIDGE_OUTLINE.anchors
                 + BALANCE_COCK_OUTLINE.anchors)]
    keep_out += [(bx, by, 6.5), (lx, ly, 5.4), (-0.9, -12.3, 2.4)]
    step, row = S.PERLAGE_DIAMETER + 0.05, (S.PERLAGE_DIAMETER + 0.05) * 0.8660
    n = int(12.6 / step) + 1
    for j in range(-n - 2, n + 3):
        for i in range(-n - 2, n + 3):
            x = i * step + (step / 2 if j % 2 else 0.0)
            y = j * row
            if math.hypot(x, y) > 12.5:
                continue
            if any(math.hypot(x - kx, y - ky) < kr for kx, ky, kr in keep_out):
                continue
            cuts.append(Pos(x, y, -0.033) * proto)
    # directional satin grain on the two recess floors — the big perlage
    # keep-out fields that read as blank glossy copper through the bridge
    # gaps. Tools are fused + clipped INSIDE each recess wall (radius a hair
    # under the recess cut) so nothing carves voids in the surrounding solid.
    for cx, cy, rr, zf in ((bx, by, 6.32, -0.35), (lx, ly, 5.22, -0.30)):
        gclip = Pos(cx, cy, 0) * _cyl(rr, 0.6, zf - 0.3)
        cuts.extend(_grain(2 * rr + 0.5, 2 * rr + 0.5, cx, cy, zf,
                           _ang((cx, cy), (0.0, 0.0)), clip=gclip))
    plate = plate - cuts
    parts.append(_finish(plate, "main_plate", S.COPPER_GOLD))

    for (x, y), name in zip(lower, ("center", "third", "fourth", "escape",
                                    "pallet", "balance")):
        # domed disc seated 0.11 inside the sink (0.21 at the balance, where
        # the dial-side shock ring + cap jewel stack sits below it) — drops
        # deepened 0.06 with the 0.14 dome so each apex keeps its old z
        drop = 0.21 if name == "balance" else 0.11
        ruby = (Pos(x, y, -S.PLATE_THICKNESS) * Rot(180, 0, 0)
                * Pos(0, 0, -drop) * _ruby_disc())
        parts.append(_finish(ruby, f"plate_jewel:{name}", S.RUBY))
    # Incabloc-style polished setting hint at the balance, dial side
    ring = Pos(lx, ly, 0) * _ring(0.65, 1.2, 0.18, -1.68)
    parts.append(_finish(ring, "balance_lower_shock_ring", S.STEEL_BRIGHT))
    cap = Pos(lx, ly, 0) * _cyl(0.5, 0.2, -1.58)
    parts.append(_finish(cap, "balance_lower_cap_jewel", S.RUBY_BRIGHT))
    return parts


# ---------------------------------------------------------------------------
# 2. Barrel group (drum + tooth flange, lid, mainspring, arbor)
# ---------------------------------------------------------------------------

def _barrel_parts():
    parts = []
    bx, by = S.BARREL_POS
    rot_flange = _ang(S.BARREL_POS, S.CENTER_WHEEL_POS)

    flange = Rot(0, 0, rot_flange) * F.train_wheel(
        S.BARREL_TEETH, _BARREL_GEAR_D, web_thickness=0.30, spoke_count=0,
        tooth_depth_frac=0.12, color=S.BRASS_MOVEMENT)
    drum = (
        _cyl(6.0, _DRUM_Z[1] - _DRUM_Z[0], _DRUM_Z[0])
        - _cyl(5.5, 1.2, _DRUM_Z[0] + 0.15)
        + Pos(0, 0, (_FLANGE_Z[0] + _FLANGE_Z[1]) / 2.0) * flange
    )
    drum = drum - [_cyl(0.85, 3.0, 0.2), _cyl(5.44, 1.2, 0.9)]
    drum = Pos(bx, by, 0) * drum
    parts.append(_finish(drum, "barrel_drum", S.BRASS_MOVEMENT))

    lid = _cyl(5.42, 0.15, 1.45) - _cyl(0.85, 1.0, 1.2)
    parts.append(_finish(Pos(bx, by, 0) * lid, "barrel_lid", S.BRASS_MOVEMENT))

    coils = Pos(2.65, -0.05, 0) * Box(3.9, 0.1, 0.6) * 0 if False else None
    coils = Pos(0, 0, 1.0) * Box(3.9, 0.1, 0.6)
    coils = Pos(2.68, 0, 0) * coils  # radial tie keeping the coils one solid
    for r in (0.8, 1.7, 2.6, 3.5, 4.4):
        coils = coils + _ring(r, r + 0.16, 0.6, 0.7)
    parts.append(_finish(Pos(bx, by, 0) * coils, "mainspring", S.STEEL_DARK))

    # raised polished winding square: proud of the ratchet wheel with a
    # chamfered crown, wide enough (1.70; half-diagonal 1.20 clears the
    # exported 1.3 lever keep-out) to carry a machined spot-face for the
    # blued ratchet screw — head Ø1.3 seated IN a Ø1.44 counterbore with a
    # bright flared rim, top 0.04 proud of the square, instead of the old
    # dome perched loose on the square top
    square = Pos(0, 0, (2.80 + RATCHET_SQUARE_TOP_Z) / 2.0) * Box(
        1.70, 1.70, RATCHET_SQUARE_TOP_Z - 2.80)
    square, _ = F.safe_chamfer(
        square,
        [e for e in square.edges()
         if abs(e.bounding_box().max.Z - RATCHET_SQUARE_TOP_Z) < 1e-6
         and abs(e.bounding_box().min.Z - RATCHET_SQUARE_TOP_Z) < 1e-6],
        0.12)
    arbor = (
        _cyl(0.5, 1.75, -1.30)             # lower pivot into the plate
        + _cyl(0.675, 2.42, 0.45)          # body through drum/lid/bridge jewel
        + square
    )
    arbor = arbor - [
        # ratchet-screw spot-face: floor 0.02 under the head bottom (head top
        # RATCHET_SQUARE_TOP_Z + 0.04, hh 0.34), flare cone = the bright
        # machined rim ring of a real screw sink
        _cyl(0.72, 0.6, RATCHET_SQUARE_TOP_Z - 0.32),
        Pos(0, 0, RATCHET_SQUARE_TOP_Z - 0.05) * Cone(0.72, 0.85, 0.10),
    ]
    parts.append(_finish(Pos(bx, by, 0) * arbor, "barrel_arbor", S.STEEL_DARK))
    return parts


# ---------------------------------------------------------------------------
# 3. Going train (wheels GILT, pinions+arbors STEEL_DARK, mesh-phased)
# ---------------------------------------------------------------------------

def _train_parts():
    parts = []

    def wheel(label, teeth, dia, pos, z_mid, partner, frac, thick=0.18, bore=0.34):
        w = F.train_wheel(teeth, dia, web_thickness=thick, tooth_depth_frac=frac)
        w = w - [_window_cutter(dia, frac), _cyl(bore, 2.0, -1.0)]
        w = Pos(pos[0], pos[1], z_mid) * Rot(0, 0, _ang(pos, partner)) * w
        parts.append(_finish(w, label, S.GILT))

    def pinion(label, leaves, dia, pos, z_band, partner, arbor_top=2.18):
        p = F.pinion(leaves, dia, z_band[1] - z_band[0])  # spans z [0, L]
        rot = _ang(pos, partner) + 180.0 / leaves
        body = (Pos(0, 0, z_band[0]) * Rot(0, 0, rot) * p
                + _cyl(_ARBOR_R, arbor_top + 1.28, -1.28))
        parts.append(_finish(Pos(pos[0], pos[1], 0) * body, label, S.STEEL_DARK))

    cw, tw, fw, ew = (S.CENTER_WHEEL_POS, S.THIRD_WHEEL_POS,
                      S.FOURTH_WHEEL_POS, S.ESCAPE_WHEEL_POS)
    wheel("center_wheel", S.CENTER_WHEEL_TEETH, _CENTER_WHEEL_D, cw, _CW_Z, tw, 0.11)
    pinion("center_pinion", S.CENTER_PINION_LEAVES, _CENTER_PINION_D, cw, _CP_Z,
           S.BARREL_POS)
    wheel("third_wheel", S.THIRD_WHEEL_TEETH, _THIRD_WHEEL_D, tw, _TW_Z, fw, 0.10)
    pinion("third_pinion", S.THIRD_PINION_LEAVES, _THIRD_PINION_D, tw, _TP_Z, cw)
    wheel("fourth_wheel", S.FOURTH_WHEEL_TEETH, _FOURTH_WHEEL_D, fw, _FW_Z, ew, 0.12)
    pinion("fourth_pinion", S.FOURTH_PINION_LEAVES, _FOURTH_PINION_D, fw, _FP_Z, tw)
    pinion("escape_pinion", S.ESCAPE_PINION_LEAVES, _ESCAPE_PINION_D, ew, _EP_Z, fw)
    return parts


# ---------------------------------------------------------------------------
# 4. Bridges, screws, upper jewels, ratchet/crown/click layer
# ---------------------------------------------------------------------------

def _bridge_parts():
    parts = []
    z0, z1 = BRIDGE_SEAT_Z, BRIDGE_TOP_Z
    bx, by = S.BARREL_POS
    cwx, cwy = S.CROWN_WHEEL_POS

    # barrel bridge -------------------------------------------------------
    extra = [
        Pos(cwx, cwy, 0) * _cyl(0.6, 1.4, z1 - 0.9),      # crown-wheel screw bore
        Pos(3.74, 3.87, 0) * _cyl(0.3, 1.2, z1 - 0.7),    # click screw bore
        Pos(5.3, 4.6, 0) * _cyl(0.26, 1.2, z1 - 0.7),     # click-spring screw bore
    ]
    zb = z1 + _BOSS_H                     # polished jewel-table top
    # barrel sink cut flush into the striped top (no table: the ratchet wheel
    # starts only 0.03 above it) and widened so the winding square's corners
    # (half-diagonal 1.004) clear the cone at the square's z2.80 base
    bb, bb_shadow, bb_rib = _bridge(BARREL_BRIDGE_OUTLINE, z0, z1,
                            [S.BARREL_POS],
                            [BRIDGE_SCREW_POSITIONS["barrel_bridge:left"],
                             BRIDGE_SCREW_POSITIONS["barrel_bridge:right"],
                             BRIDGE_SCREW_POSITIONS["barrel_bridge:top"]],
                            recesses=BARREL_BRIDGE_RECESSES,
                            extra_cuts=extra,
                            jewel_sink_kw=dict(cone_r=1.30, wall_r=1.06,
                                               cone_z=0.20, seat_z=0.55,
                                               bore_r=0.72))
    parts.append(_finish(bb, "barrel_bridge", S.COPPER_GOLD))
    _add_shadow(parts, bb_shadow, "barrel_bridge")
    _add_anglage(parts, bb_rib, "barrel_bridge")
    # ruby ring recessed in the counterbore around the arbor (the old jewel
    # minus arbor bore left a 0.025 shell perched at the surface); top z1-0.10
    # stays under the winding square's z2.80 base
    ruby = _ring(0.70, 1.03, 0.20, z1 - 0.30)
    parts.append(_finish(Pos(bx, by, 0) * ruby, "bridge_jewel:barrel", S.RUBY))

    # train bridge --------------------------------------------------------
    train_jewels = [S.CENTER_WHEEL_POS, S.THIRD_WHEEL_POS,
                    S.FOURTH_WHEEL_POS, S.ESCAPE_WHEEL_POS]
    tb, tb_shadow, tb_rib = _bridge(TRAIN_BRIDGE_OUTLINE, z0, z1, [],
                            [BRIDGE_SCREW_POSITIONS["train_bridge:foot"],
                             BRIDGE_SCREW_POSITIONS["train_bridge:fourth"],
                             BRIDGE_SCREW_POSITIONS["train_bridge:center"]],
                            cutouts=TRAIN_BRIDGE_CUTOUTS, boss_xy=train_jewels)
    parts.append(_finish(tb, "train_bridge", S.COPPER_GOLD))
    _add_shadow(parts, tb_shadow, "train_bridge")
    _add_anglage(parts, tb_rib, "train_bridge")
    # domed ruby stone recessed in the sink (rim 0.12 under the table top,
    # 0.14 dome apex at table + 0.02 — under the chrono arbors hovering at
    # 2.95), thin gold chaton ring between the ruby and the bright sink cone
    # — the ruby/gold/dark-moat/polished-cone concentric read of the
    # reference, now with a point highlight on each stone
    for (x, y), name in zip(train_jewels, ("center", "third", "fourth", "escape")):
        parts.append(_finish(Pos(x, y, zb - 0.12) * _ruby_disc(),
                             f"bridge_jewel:{name}", S.RUBY))
        chaton = Pos(x, y, 0) * _ring(0.47, 0.70, 0.32, zb - 0.42)
        parts.append(_finish(chaton, f"chaton:{name}", S.BRASS_MOVEMENT))

    # bridge screws (shanks stay inside the bridge bore: longer ones hung
    # visibly in the open gap between the low plate bosses and the seat;
    # barrel:left shortened to 0.75 — its 0.4 inward shift put the old 0.9
    # shank tip into the barrel tooth flange, probe-verified)
    for name, shank in (("barrel_bridge:left", 0.75), ("barrel_bridge:right", 0.9),
                        ("barrel_bridge:top", 0.75), ("train_bridge:foot", 0.9),
                        ("train_bridge:fourth", 0.9), ("train_bridge:center", 0.75)):
        x, y = BRIDGE_SCREW_POSITIONS[name]
        parts.append(_finish(_place_screw(x, y, z1, shank=shank),
                             f"screw:{name}", S.BLUED))

    # ratchet wheel + raised winding square + blued screw ------------------
    ratchet = F.train_wheel(48, S.RATCHET_WHEEL_DIAMETER, web_thickness=0.26,
                            spoke_count=0, tooth_depth_frac=0.06)
    ratchet = ratchet - Pos(0, 0, 0.13) * F.snailing_cutter(9.2, 2.2)
    beak_gap = _ang(S.BARREL_POS, (2.52, 4.9)) + 3.75
    ratchet = Pos(bx, by, (RATCHET_Z0 + RATCHET_TOP_Z) / 2.0) * Rot(0, 0, beak_gap) * ratchet
    # square hole cut AFTER the mesh-phasing rotation so it stays aligned
    # with the arbor's raised winding square (they clashed when the hole
    # rotated with the wheel); 1.80 clears the widened 1.70 square
    ratchet = ratchet - Pos(bx, by, 3.0) * Box(1.80, 1.80, 1.0)
    parts.append(_finish(ratchet, "ratchet_wheel", S.GILT))
    parts.append(_finish(
        _place_screw(bx, by, RATCHET_SQUARE_TOP_Z, proud=0.04, head_d=1.3,
                     hh=0.34, shank=1.4),
        "screw:ratchet", S.BLUED))

    # crown wheel + recessed polished steel core --------------------------
    crown = F.train_wheel(30, S.CROWN_WHEEL_DIAMETER, web_thickness=0.24,
                          spoke_count=0, tooth_depth_frac=0.08)
    crown = crown - [Pos(0, 0, 0.12) * F.snailing_cutter(5.6, 1.8),
                     _cyl(0.62, 1.0, -0.5),
                     _cyl(1.35, 0.4, 0.02)]     # core recess in the snailed top
    parts.append(_finish(Pos(cwx, cwy, 2.99) * crown, "crown_wheel", S.GILT))
    # polished core is a slotless disc; the screw read comes from a separate
    # spec-sized head (the old 2.2 slotted-dome core was the outsized "screw"
    # the blind critic flagged)
    core = Pos(cwx, cwy, 0) * (_cyl(1.24, 0.14, 3.01) - _cyl(0.40, 1.0, 2.8))
    parts.append(_finish(core, "crown_wheel_core", S.STEEL_BRIGHT))
    parts.append(_finish(
        _place_screw(cwx, cwy, 3.15, proud=0.04, head_d=1.3, hh=0.30, shank=1.0),
        "screw:crown_wheel", S.BLUED))

    # click + click spring (polished steel, engaging the ratchet) ---------
    # smooth polished lever: dense disk chain beak -> pivot -> tail so the
    # envelope reads as one continuous curve (sparse chains scallop)
    click_pts = []
    # pivot boss r 0.68: wide enough that the Ø1.14 screw spot-face leaves a
    # machined rim (still clear of the ratchet teeth in the shared z band)
    for (xa, ya, ra), (xb, yb, rb), n in (((2.52, 4.90, 0.22), (3.74, 3.87, 0.68), 12),
                                          ((3.74, 3.87, 0.68), (4.75, 3.12, 0.32), 10)):
        for i in range(n + 1):
            t = i / n
            tt = t * t * (3 - 2 * t)      # smoothstep radius blend
            click_pts.append((xa + (xb - xa) * t, ya + (yb - ya) * t,
                              ra + (rb - ra) * tt))
    click_prof = _blob(click_pts, 14.0)
    click = Pos(0, 0, 2.9) * extrude(click_prof, amount=0.16)
    click, _ = F.anglage_top(click, 0.06)
    # pivot bore + a shallow spot-face (counterbore Ø = head Ø + 0.14) so the
    # Ø1.0 screw head shows a machined ring gap instead of lying loose on top
    # + straight satin grain along the beak->tail axis, clipped 0.12 inside
    # the outline so it never nicks the anglage bevel
    grain_clip = Pos(0, 0, 2.98) * extrude(
        _blob([(x, y, max(r - 0.12, 0.08)) for x, y, r in click_pts], 14.0),
        amount=0.30)
    click = click - ([Pos(3.74, 3.87, 0) * _cyl(0.3, 1.0, 2.6),
                      Pos(3.74, 3.87, 0) * _cyl(0.57, 0.5, 3.00)]
                     + _grain(3.2, 2.0, 3.63, 4.01, 3.06,
                              _ang((2.52, 4.90), (4.75, 3.12)),
                              clip=grain_clip))
    parts.append(_finish(click, "click", S.STEEL_LEVER))
    parts.append(_finish(
        _place_screw(3.74, 3.87, 3.06, proud=0.05, head_d=1.0, hh=0.24, shank=0.7),
        "screw:click", S.BLUED))

    # blade drawn as a dense chain of overlapping disks along the Bezier
    # (an offset-strip Polygon self-crossed at the tight bend; validate
    # flagged it selfIntersecting)
    p0, p1, p2 = (5.2, 4.3), (5.5, 3.7), (4.98, 3.28)
    blade = []
    for i in range(25):
        t = i / 24.0
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        blade.append((x, y, 0.09))
    spring_prof = _blob(blade, 14.0) + Pos(5.3, 4.6) * Circle(0.62)
    spring = Pos(0, 0, 2.9) * extrude(spring_prof, amount=0.14)
    # screw bore + spot-face + satin grain along the blade axis (no anglage
    # on the spring, so the unclipped tools only cut where they overlap)
    spring = spring - ([Pos(5.3, 4.6, 0) * _cyl(0.26, 1.0, 2.6),
                        Pos(5.3, 4.6, 0) * _cyl(0.52, 0.5, 2.99)]
                       + _grain(2.4, 1.4, 5.18, 3.95, 3.04,
                                _ang((5.3, 4.6), (4.98, 3.28))))
    parts.append(_finish(spring, "click_spring", S.STEEL_LEVER))
    parts.append(_finish(
        _place_screw(5.3, 4.6, 3.04, proud=0.04, head_d=0.9, hh=0.2, shank=0.6),
        "screw:click_spring", S.BLUED))
    return parts


# ---------------------------------------------------------------------------
# 5. Escapement: club-tooth escape wheel, pallet fork + stones, pallet bridge
# ---------------------------------------------------------------------------

def _escape_wheel():
    # inner chord sunk to r1.55 so every tooth overlaps the rim band (a
    # chord at exactly r1.70 touched the rim at ONE point -> 15 disjoint
    # tooth solids, caught by inspect validate)
    tooth = Polygon((1.55, 0.30), (1.55, -0.05), (2.30, -0.45), (2.62, -0.55),
                    (2.70, -0.30), (2.48, -0.12), (2.02, 0.24), align=None)
    prof = Circle(1.70) + [Rot(0, 0, 360.0 * k / S.ESCAPE_WHEEL_TEETH) * tooth
                           for k in range(S.ESCAPE_WHEEL_TEETH)]
    prof = prof - (Circle(1.42) - Circle(0.5))
    spokes = None
    for k in range(4):
        sp = Rot(0, 0, 45 + 90 * k) * Polygon(
            (-1.5, -0.14), (1.5, -0.14), (1.5, 0.14), (-1.5, 0.14), align=None)
        spokes = sp if spokes is None else spokes + sp
    prof = prof + (spokes & Circle(1.6))
    wheel = extrude(prof, amount=0.18)          # spans z [0, 0.18]
    wheel = wheel - _cyl(0.33, 1.0, -0.4)
    ex, ey = S.ESCAPE_WHEEL_POS
    wheel = Pos(ex, ey, _EW_Z - 0.09) * Rot(0, 0, 7.0) * wheel
    return _finish(wheel, "escape_wheel", S.GILT)


def _pallet_parts():
    parts = []
    pp = S.PALLET_FORK_POS
    ec = S.ESCAPE_WHEEL_POS
    bal = S.BALANCE_POS
    th_b = math.radians(_ang(pp, bal))
    dir_b = (math.cos(th_b), math.sin(th_b))
    perp = (-dir_b[1], dir_b[0])
    th_pe = math.radians(_ang(ec, pp))
    stones = []
    for dth, name, ax in ((-30.0, "entry", 38.5), (30.0, "exit", 98.5)):
        a = th_pe + math.radians(dth)
        sx, sy = ec[0] + 2.85 * math.cos(a), ec[1] + 2.85 * math.sin(a)
        stones.append((sx, sy, name, ax))

    def along(t, off=0.0):
        return (pp[0] + t * dir_b[0] + off * perp[0],
                pp[1] + t * dir_b[1] + off * perp[1])

    circles = [(pp[0], pp[1], 0.5)]
    for sx, sy, _n, _a in stones:
        circles.append((sx, sy, 0.42))
        circles.append(((pp[0] + sx) / 2, (pp[1] + sy) / 2, 0.5))
    for t, r in ((1.2, 0.38), (2.4, 0.34), (3.4, 0.30)):
        x, y = along(t)
        circles.append((x, y, r))
    for sgn in (1.0, -1.0):
        x, y = along(3.85, sgn * 0.30)
        circles.append((x, y, 0.24))
    prof = _blob(circles, 14.0)
    nx, ny = along(4.15)
    prof = prof - Pos(nx, ny) * Circle(0.18)
    fork = Pos(0, 0, _FORK_Z[0]) * extrude(prof, amount=_FORK_Z[1] - _FORK_Z[0])
    fork, _ = F.anglage_top(fork, 0.05)

    stone_cuts, stone_parts = [], []
    for sx, sy, name, ax in stones:
        slab = Pos(sx, sy, 1.17) * Rot(0, 0, ax) * Box(0.6, 0.24, 0.34)
        pad = Pos(sx, sy, 1.30) * Rot(0, 0, ax) * Box(0.66, 0.30, 0.44)
        stone_cuts.append(pad)
        stone_parts.append(_finish(slab, f"pallet_stone:{name}", S.RUBY_BRIGHT))
    # satin grain along the fork's long (pivot->horns) axis on the exposed
    # top, clipped 0.12 inside the outline to stay off the anglage bevel
    grain_clip = Pos(0, 0, _FORK_Z[0]) * extrude(
        _blob([(x, y, max(r - 0.12, 0.06)) for x, y, r in circles], 14.0),
        amount=0.30)
    fork = fork - (stone_cuts
                   + [Pos(pp[0], pp[1], 0) * _cyl(0.21, 1.0, 0.9)]
                   + _grain(9.0, 9.0, pp[0], pp[1], _FORK_Z[1],
                            _ang(pp, bal), clip=grain_clip))
    gx, gy = along(3.6)
    fork = fork + Pos(gx, gy, 0) * _cyl(0.07, 0.18, 1.13)   # guard pin
    parts.append(_finish(fork, "pallet_fork", S.STEEL_BRIGHT))
    parts.extend(stone_parts)

    arbor = Pos(pp[0], pp[1], 0) * _cyl(0.2, 2.72, -1.28)
    parts.append(_finish(arbor, "pallet_arbor", S.STEEL_DARK))

    # pallet bridge: small striped copper cock, 1 jewel, 1 blued screw
    # (sink shallow + narrow: the cock is only 0.36 thick and its jewel lobe
    # is r 1.15, so the default counterbore would pierce/eat it)
    pbz0, pbz1 = PALLET_BRIDGE_Z
    pb, pb_shadow, pb_rib = _bridge(PALLET_BRIDGE_OUTLINE, pbz0, pbz1,
                            [pp], [BRIDGE_SCREW_POSITIONS["pallet_bridge"]],
                            jewel_sink_kw=dict(cone_r=0.75, wall_r=0.52,
                                               cone_z=0.10, seat_z=0.22,
                                               bore_r=0.26))
    parts.append(_finish(pb, "pallet_bridge", S.COPPER_GOLD))
    _add_shadow(parts, pb_shadow, "pallet_bridge")
    _add_anglage(parts, pb_rib, "pallet_bridge")
    ruby = Pos(pp[0], pp[1], pbz1 - 0.04) * _ruby_disc(r=0.36, t=0.16, ch=0.04,
                                                       hole_r=0.10)
    parts.append(_finish(ruby, "bridge_jewel:pallet", S.RUBY))
    chaton = Pos(pp[0], pp[1], 0) * _ring(0.37, 0.50, 0.14, pbz1 - 0.22)
    parts.append(_finish(chaton, "chaton:pallet", S.BRASS_MOVEMENT))
    x, y = BRIDGE_SCREW_POSITIONS["pallet_bridge"]
    parts.append(_finish(_place_screw(x, y, pbz1, shank=0.6),
                         "screw:pallet_bridge", S.BLUED))
    return parts


# ---------------------------------------------------------------------------
# 6. Balance assembly: wheel + timing screws, hairspring, staff/rollers,
#    cock with stripes/anglage, lyre-spring shock setting, regulator, stud
# ---------------------------------------------------------------------------

def _balance_parts():
    parts = []
    lx, ly = S.BALANCE_POS
    pp = S.PALLET_FORK_POS
    z_rim0, z_rim1 = BALANCE_RIM_Z

    rim = _ring(4.1, 4.8, z_rim1 - z_rim0, z_rim0)
    arms = Pos(0, 0, 2.14) * Rot(0, 0, 30) * Box(8.5, 0.85, 0.2)
    hub = _cyl(0.65, z_rim1 - z_rim0, z_rim0)
    slits = [Rot(0, 0, 120 + 180 * k) * Pos(4.45, 0, 2.225) * Box(0.9, 0.12, 0.6)
             for k in range(2)]
    wheel = (rim + arms + hub) - (slits + [_cyl(0.28, 1.0, 1.8)])
    # polished catch on the rim's top edges + GILT (train-wheel champagne):
    # brass-on-copper camouflaged the rim against the plate in the blind A/B
    wheel, _ = F.safe_chamfer(
        wheel,
        [e for e in wheel.edges()
         if abs(e.bounding_box().max.Z - z_rim1) < 1e-6
         and abs(e.bounding_box().min.Z - z_rim1) < 1e-6],
        0.08)
    parts.append(_finish(Pos(lx, ly, 0) * wheel, "balance_wheel", S.GILT))

    for k in range(16):
        a = 11.25 + k * 22.5
        s = (Pos(4.85, 0, 2.225) * Rot(0, 90, 0) * Cylinder(0.16, 0.30)
             + Pos(5.03, 0, 2.225) * Rot(0, 90, 0) * Cylinder(0.22, 0.14))
        s = Pos(lx, ly, 0) * Rot(0, 0, a) * s
        parts.append(_finish(s, f"timing_screw:{k}", S.BRASS_MOVEMENT))

    # staff + safety/impulse rollers + collet
    th_p = math.radians(_ang(S.BALANCE_POS, pp))
    pinx = lx + 0.55 * math.cos(th_p)
    piny = ly + 0.55 * math.sin(th_p)
    staff = (_cyl(0.27, 4.26, -1.28)
             + _cyl(0.55, 0.13, 1.05)          # impulse roller
             + _cyl(0.35, 0.10, 1.18)          # safety roller
             + _cyl(0.375, 0.22, 2.46))        # collet
    staff = Pos(lx, ly, 0) * staff
    staff = staff - Pos(pinx, piny, 0) * _cyl(0.10, 0.8, 1.0)
    parts.append(_finish(staff, "balance_staff", S.STEEL_DARK))
    pin = Pos(pinx, piny, 0) * _cyl(0.09, 0.42, 1.05)
    parts.append(_finish(pin, "impulse_jewel", S.RUBY_BRIGHT))

    # hairspring: 12-coil Archimedean band ending at the stud angle (-40 deg).
    # Coil band widened 0.045 -> 0.06 and thickened 0.12 -> 0.16 (z 2.50-2.66,
    # 0.04 under the cock) so the spiral reads at macro instead of vanishing
    # into the shadow line under the cock.
    r0, pitch, turns, width = 0.42, 0.19, 12, 0.06
    phi0 = math.radians(-40.0)
    outer, inner = [], []
    steps = turns * 36
    for i in range(steps + 1):
        th = 2 * math.pi * turns * i / steps
        r = r0 + pitch * th / (2 * math.pi)
        a = phi0 + th
        outer.append(((r + width) * math.cos(a), (r + width) * math.sin(a)))
        inner.append((r * math.cos(a), r * math.sin(a)))
    poly = Polygon(*(outer + list(reversed(inner))), align=None)
    spring = Pos(lx, ly, 2.50) * extrude(poly, amount=0.16)
    parts.append(_finish(spring, "hairspring", S.STEEL_DARK))

    # stud: steel pin dropping from the stud holder to the spring's outer end
    cz0, cz1 = COCK_Z
    sx = lx + 2.85 * math.cos(math.radians(-40))
    sy = ly + 2.85 * math.sin(math.radians(-40))
    stud = Pos(sx, sy, 0) * (_cyl(0.15, cz1 - 2.34, 2.34) + _cyl(0.22, 0.20, 2.42))
    parts.append(_finish(stud, "hairspring_stud", S.STEEL_DARK))

    # balance cock ---------------------------------------------------------
    bootx = lx + 2.85 * math.cos(math.radians(-95))
    booty = ly + 2.85 * math.sin(math.radians(-95))
    extra = [
        Pos(lx, ly, 0) * _cyl(1.28, 1.2, cz0 - 0.3),        # shock-setting seat
        Pos(bootx, booty, 0) * _cyl(0.17, 1.2, cz0 - 0.3),  # regulator boot bore
        Pos(sx, sy, 0) * _cyl(0.18, 1.2, cz0 - 0.3),        # stud bore
    ]
    cock, cock_shadow, cock_rib = _bridge(BALANCE_COCK_OUTLINE,
                                          cz0, cz1, [],
                                          [BRIDGE_SCREW_POSITIONS["balance_cock"]],
                                          extra_cuts=extra)
    parts.append(_finish(cock, "balance_cock", S.COPPER_GOLD))
    _add_shadow(parts, cock_shadow, "balance_cock")
    _add_anglage(parts, cock_rib, "balance_cock")
    x, y = BRIDGE_SCREW_POSITIONS["balance_cock"]
    parts.append(_finish(_place_screw(x, y, cz1, shank=0.8),
                         "screw:balance_cock", S.BLUED))

    # stud holder: small polished plate on the cock's side lobe, clamping
    # the stud with its own tiny blued screw
    holder2d = _blob(((sx, sy, 0.45), (1.45, -9.20, 0.42), (1.12, -8.98, 0.52)), 14.0)
    holder = Pos(0, 0, cz1) * extrude(holder2d, amount=0.12)
    holder, _ = F.anglage_top(holder, 0.05)
    holder = holder - [Pos(1.12, -8.98, 0) * _cyl(0.14, 1.0, cz1 - 0.4),
                       Pos(1.12, -8.98, 0) * _cyl(0.47, 0.5, cz1 + 0.07)]
    parts.append(_finish(holder, "stud_holder", S.STEEL_LEVER))
    parts.append(_finish(
        _place_screw(1.12, -8.98, cz1 + 0.12, proud=0.03, head_d=0.8, hh=0.2,
                     shank=0.5),
        "screw:stud_holder", S.BLUED))

    # shock setting: polished bezel, gold chaton, cap jewel, lyre spring —
    # whole stack sunk ~0.1 vs the first pass (the bezel topped 0.13 proud of
    # the cock and the domed cap bead bulged through the lyre; the cap is now
    # a flat 0.9-dia disc, no pivot hole: cap jewels are blind)
    bezel = Pos(lx, ly, 0) * (_ring(0.85, 1.25, 0.56, 2.72)
                              - Pos(0, 0, 3.28) * Cone(1.3, 0.9, 0.16))
    parts.append(_finish(bezel, "shock_bezel", S.STEEL_BRIGHT))
    gold = Pos(lx, ly, 0) * _ring(0.48, 0.83, 0.36, 2.84)   # top 3.20, under lyre
    parts.append(_finish(gold, "shock_chaton", S.BRASS_MOVEMENT))
    cap = Pos(lx, ly, 3.18) * _ruby_disc(r=0.45, t=0.24, hole_r=0.0)
    parts.append(_finish(cap, "shock_cap_jewel", S.RUBY_BRIGHT))
    # lyre spring: crisp wire form — thin outer arc ring, three radial arms
    # into a small hub ring circling the cap jewel dome, two feet flanking the
    # opening (the old 0.20-wide band + fat feet fused into one white blob at
    # macro). One multi-operand 2D fuse, gap wedge subtracted LAST (/BUGS.md).
    # z 3.20..3.29 stays inside COCK_SHOCK_TOP_Z = 3.4.
    gap_a = -40.0
    outer_ring = Circle(1.06) - Circle(0.95)
    hub_ring = Circle(0.64) - Circle(0.50)
    arm2d = Polygon((0.50, -0.055), (1.00, -0.055), (1.00, 0.055),
                    (0.50, 0.055), align=None)
    lyre2d = outer_ring + (
        [hub_ring]
        + [Rot(0, 0, gap_a + da) * arm2d for da in (90.0, 180.0, 270.0)]
        + [Rot(0, 0, gap_a + s) * Pos(0.94, 0) * Circle(0.12)
           for s in (14.0, -14.0)])
    lyre2d = lyre2d - Rot(0, 0, gap_a) * Polygon(
        (0.0, 0.0), (2.4, -0.55), (2.4, 0.55), align=None)
    lyre = Pos(lx, ly, 3.20) * extrude(lyre2d, amount=0.09)
    parts.append(_finish(lyre, "shock_lyre_spring", S.STEEL_BRIGHT))

    # regulator: black-polished ring + tapered index lever + boot through
    # the cock (curb pins gripping the hairspring's outer coil)
    tail_a = -95.0
    reg2d = Pos(lx, ly) * (Circle(1.72) - Circle(1.36))
    tail = Polygon((-0.27, 1.42), (0.27, 1.42), (0.10, 4.05), (-0.10, 4.05),
                   align=None)
    tip = Polygon((-0.10, 4.05), (0.10, 4.05), (0.0, 4.55), align=None)
    reg2d = reg2d + Pos(lx, ly) * Rot(0, 0, tail_a - 90) * (tail + tip)
    reg = Pos(0, 0, cz1 + 0.01) * extrude(reg2d, amount=0.08)
    # satin grain along the index lever's long axis (field starts outside
    # the r1.72 ring so the black-polished ring stays mirror-clean)
    gx = lx + 3.2 * math.cos(math.radians(tail_a))
    gy = ly + 3.2 * math.sin(math.radians(tail_a))
    reg = reg - _grain(2.8, 0.9, gx, gy, cz1 + 0.09, tail_a)
    boot = Pos(bootx, booty, 0) * _cyl(0.14, 0.82, 2.50)
    parts.append(_finish(reg + boot, "regulator", S.STEEL_DARK))
    return parts


def build_base():
    """All movement-base parts, labeled and colored, in the movement frame."""
    parts = []
    parts += _plate_parts()
    parts += _barrel_parts()
    parts += _train_parts()
    parts += _bridge_parts()
    parts.append(_escape_wheel())
    parts += _pallet_parts()
    parts += _balance_parts()
    return parts
