"""Chronograph works cluster: column wheel, operating/reset/brake levers,
coupling clutch with swinging intermediate wheel, chronograph runner with
heart cam, minute recorder with jumper, dial-side hour recorder, hammer yoke
striking both heart cams, return springs and shoulder studs/screws — the
grey-steel layer riding above the bridges of the caliber-321-lineage
movement — plus the striped chronograph bridge and coupling cock that cap
the runner / minute-recorder / coupling-arm upper pivots with jeweled
countersunk bearings (see the "Chronograph bridge plan" constants).

Frame: MOVEMENT local (see `_spec.py`) — bridge side up, z = 0 at the plate's
bridge-side face. Bridge-side chronograph parts live in z ~ 2.85..4.1 (the
band above `_mvt_base.BRIDGE_TOP_Z`); the hour recorder lives on the dial
side in z ~ [-2.6, -1.6].

Pose: chronograph zeroed / at rest —

- coupling clutch DISENGAGED: its beak rides ON a column flank, the swinging
  wheel held ~0.15 off the runner's tip circle;
- brake ON: pad 0.05 off (visually against) the runner rim;
- hammers SEATED: both faces on the heart cams' low points (cam tips point
  away from the faces), the hammer's column feeler dropped into a gap;
- operating beak resting against a star tooth's drive face, between columns.

Routing is planned against `_mvt_base`'s exported READ-ONLY constants
(bridge outlines/z bands, screw keep-outs, ratchet/crown/click z tops,
balance-cock band). Nothing here dips below its local floor: levers pass
over bridge screw heads (top 2.91) at z >= 2.96, over the ratchet wheel
(top 3.14) / crown wheel (top ~3.2) only where XY-clear, and every pivot
stud drops only onto open plate (z=0) or a bridge top (2.85) that is clear
below (verified against the base's train-wheel plan in `_mvt_base`).

`_finishing.py`'s align=(None,None,None) datum quirks (see /BUGS.md) are
compensated locally exactly as `_mvt_base.py` does (centered primitives via
default align; `F.train_wheel` spoke windows re-cut full depth).
"""

from __future__ import annotations

import math

from build123d import (
    Box,
    Circle,
    Color,
    Cone,
    Cylinder,
    Polygon,
    Pos,
    Rot,
    extrude,
)

import _spec as S
import _finishing as F
import _mvt_base as M  # READ-ONLY routing constants

# ---------------------------------------------------------------------------
# Layout constants (chronograph local plan)
# ---------------------------------------------------------------------------

CWX, CWY = S.COLUMN_WHEEL_POS                # (8.3, 3.6)
MRX, MRY = S.MINUTE_RECORDER_POS             # (10.2, 0.0)
HRX, HRY = S.HOUR_RECORDER_POS               # (0.0, 10.2) dial side
CPX, CPY = S.COUPLING_WHEEL_POS              # (5.6, -4.6)
FWX, FWY = S.FOURTH_WHEEL_POS                # (-10.2, 0.0)

# z plan (bridge side). Bridge tops 2.85; screw heads 2.91; ratchet 3.14;
# crown wheel ~3.11 (+screw 3.19); click ~3.06 (+screw ~3.16); winding
# square/screw 3.46/3.58 (r1.3 keep-out at BARREL_POS); cock shock 3.4.
WHEEL_Z = (2.96, 3.14)          # lateral clutch chain + recorder wheel webs
STAR_Z = (3.20, 3.40)           # column-wheel ratchet star (probe-driven:
#   above the crown wheel top 3.11 and the recorder wheel top 3.14 — the
#   star tip circle XY-overlaps both at the spec plan positions)
COLUMN_Z = (3.40, 3.90)         # the 7 columns
LEVER_Z = (3.00, 3.14)          # jumper plate band
OPER_Z = (3.18, 3.34)           # operating lever (engages the raised star)
CLUTCH_Z = (3.20, 3.38)         # coupling clutch arm plate
RESET_Z = (3.42, 3.60)          # reset lever plate (hammer striking plane)
HAMMER_Z = (3.42, 3.66)         # hammer yoke plate
CAM_Z = (3.36, 3.60)            # heart cams (compressed under the chrono
#   bridge at CHRONO_BRIDGE_Z: cams + collets stack below 3.66 so the bridge
#   can cap the runner/recorder pivots; hammer faces still strike the cams
#   over the shared 3.42..3.60 band)
HOUR_Z = (-2.60, -1.55)         # dial-side hour recorder band

# column-wheel geometry
STAR_TEETH = 21
STAR_TIP_R = 2.30               # = COLUMN_WHEEL_DIAMETER / 2
STAR_ROOT_R = 1.98              # fine crisp ratchet teeth (0.32 deep)
COL_R_IN, COL_R_OUT = 1.30, 2.00
COL_HALF_DEG = 11.5             # column angular half-width (23 of 51.4 pitch)
COL_PITCH = 360.0 / S.COLUMN_COUNT
COL_PHASE = -145.0              # a column centered here (coupling beak rides it)
STAR_PHASE = -19.86             # a tooth tip lands at -7 deg (operating beak)

# wheel plan (tip radii; runner<->coupling center distance 7.25). The
# runner is capped by the base ratchet wheel (r 5.0 at BARREL_POS, same z
# band, center distance 8.157 — probe-verified clash at r 3.5), so the
# runner runs D6.2 and the coupling wheel grows to keep the 0.15 rest gap.
RUNNER_TIP_R = 3.10             # gilt fine-tooth runner
COUPLING_TIP_R = 4.00           # 7.25 - 3.10 - 0.15 mesh gap at rest
DRIVING_TIP_R = 2.40            # on the fourth-wheel axis, above the bridge
MINUTE_REC_TIP_R = 2.30         # 30 teeth (spec)
HOUR_REC_TIP_R = 2.70           # 24 teeth (spec), dial side

# lever pivots (studs planted per the routing notes above)
OPER_PIVOT = (11.4, 4.9)        # on the barrel bridge
BRAKE_PIVOT = (-4.05, 2.80)     # on the barrel bridge, clear of the ratchet
RESET_PIVOT = (10.0, -6.4)      # open plate (clear of the coupling wheel)
HAMMER_PIVOT = (6.9, -0.1)      # open plate (clear of coupling wheel/runner)
JUMPER_PIVOT = (10.05, -3.0)    # open plate (clear of the coupling wheel)
# spring anchor studs
OPER_SPRING_STUD = (12.4, 2.9)      # barrel bridge rim, east of the beak arm
BRAKE_SPRING_STUD = (-5.4, 3.9)     # barrel bridge
RESET_SPRING_STUD = (11.5, -5.9)    # open plate
CLUTCH_SPRING_STUD = (-9.6, -4.2)   # train bridge
JUMPER_SPRING_STUD = (11.35, -3.3)  # open plate

# ---------------------------------------------------------------------------
# Chronograph bridge plan (blind-critic fix: the chrono train read as bare
# wheels on unsupported studs; the real 321 hides most of that train under a
# large striped chronograph bridge, leaving jeweled pivot points, the column
# wheel, the balance and the steel lever-work visible on top).
# ---------------------------------------------------------------------------

#: Bridge band: above the hammer yoke (top 3.66, 0.02 hover), under
#: CHRONO_LAYER_TOP 4.1 (screw heads proud 0.04 top out flush at 4.10).
CHRONO_BRIDGE_Z = (3.68, 4.06)

#: One flowing 321-style Y plate (smooth traced `_mvt_base._Outline`, built
#: by the `_mvt_base._bridge` factory): jeweled heads over the runner (0,0)
#: and minute recorder (10.2,0) on a broad two-armed PLATE — the old crotch
#: gap between the north arm and the coupling stem is filled solid, the arm
#: over the runner is a wide span whose flanks sweep concentric to the
#: wheel, and a round WINDOW over the coupling wheel (rim beveled+ribboned
#: like every other edge) shows its hub and blued screw below. Routing
#: (plan-verified against every exported keep-out):
#: - column wheel stays FULLY visible: every edge >= 2.75 from (8.3,3.6);
#: - hammer strike faces stay visible: edges clear the yoke capsules by
#:   >= 0.2; the hammer PIVOT screw head (top 3.92) pierces the band,
#:   cleared by > 1.35;
#: - reset pivot / reset spring screw heads (tops 3.86 / 3.82) cleared by
#:   > 0.98 / 0.85; the reset lever itself (top 3.60) dives UNDER the
#:   filled plate with the pusher end, pivot and nose all visible;
#: - ratchet wheel, balance, escape wheel, brake, operating lever, minute
#:   jumper nose all stay uncovered (jumper notch kept in the outline);
#: - full-height feet drop only through wheel-free plate: the east foot
#:   clears the minute-recorder tip circle (2.41 vs 2.30), the south foot
#:   clears the coupling wheel's swept circle (4.36 vs 4.00) and the balance
#:   rim / timing-screw sweep (5.42 vs 5.25).
CHRONO_BRIDGE_OUTLINE = M._Outline(
    M._arcpts(0, 0, 1.55, 268, -42, 9)       # runner head cap (S->W->N->E)
    + [(2.0, -1.28), (3.0, -1.70), (4.2, -1.95), (5.9, -2.45), (7.3, -2.95),
       (8.55, -3.28), (9.5, -3.5)]           # north edge OVER the reset lever
    + [(10.62, -3.18)]                       # jumper-window turn (nose visible)
    + [(10.1, -1.55)]
    + M._arcpts(10.2, 0.0, 1.18, 235, 62, 5)  # minute-recorder head
    + [(11.5, 0.62)]
    + M._arcpts(12.05, -0.65, 1.3, 78, 45, 1)  # east rim body
    + M._arcpts(0, 0, 13.13, 3, -7, 2)       # rim arc
    + [(12.55, -1.9), (11.8, -2.45), (10.9, -3.6), (10.15, -4.55),
       (9.2, -4.9), (8.15, -5.2), (7.35, -5.75), (6.85, -6.6),
       (6.5, -7.6), (6.3, -8.6)]             # filled south edge into the stem
    + M._arcpts(5.3, -9.55, 0.85, -30, -150, 3)    # south foot cap
    + [(4.42, -8.5), (4.35, -7.0), (4.3, -5.9), (3.88, -5.22)]  # west flank
    + [(3.3, -4.5), (2.4, -4.1), (1.35, -3.6), (0.55, -2.85)],  # runner sweep
    anchors=((0.0, 0.0, 1.55), (1.6, -2.3, 1.1), (2.9, -2.9, 1.2),
             (4.3, -3.3, 1.4), (6.1, -3.7, 1.5), (7.9, -4.1, 1.1),
             (9.3, -4.0, 0.85), (10.3, -3.75, 0.85), (11.0, -2.9, 0.8),
             (11.4, -2.2, 0.9), (12.05, -0.65, 1.3), (10.2, 0.0, 1.18),
             (5.6, -6.2, 1.3), (5.4, -7.7, 1.1), (5.3, -9.55, 0.8)))
#: Round window (x, y, r) cut over the coupling wheel: hub, spokes and blued
#: retaining screw (head top 3.60, 0.08 under the plate) visible through it.
CHRONO_BRIDGE_WINDOWS = ((5.6, -4.6, 1.15),)
#: Blued bridge screws (sink flare r0.85 + 0.22 bevel fit inside the local
#: plate at each spot; shanks stay short — everything below is under an
#: opaque plate hovering 0.02 above the hammer plane).
CHRONO_BRIDGE_SCREWS = ((11.95, -0.7), (5.55, -7.2), (3.6, -3.3))
#: Full-height turned feet: (x, y, r, base_z) — welded 0.02 into the plate.
CHRONO_BRIDGE_FEET = ((12.75, -1.05, 0.35, 0.01), (5.3, -9.55, 0.60, 0.01))

#: Coupling cock: a small finger cock capping the coupling-arm pivot on the
#: fourth-wheel axis (-10.2,0) — that pivot cannot reach the main bridge
#: across the hammer/column corridor, so it gets its own jewel + screw (the
#: real 321 pattern for isolated chrono pivots). The foot lobe stands on the
#: train-bridge top (sleeve foot from _BRIDGE_STUD_BASE, bored for the screw
#: shank, clear of the driving wheel's swept circle 2.59 vs 2.40); the head
#: hovers over the driving wheel leaving its toothed rim visible.
COUPLING_COCK_OUTLINE = M._Outline(
    M._stroke_pts([(-10.2, 0.0, 1.22),       # jeweled head over the arbor
                   (-10.85, -1.5, 0.74),     # waisted neck
                   (-11.45, -2.92, 1.16)]),  # foot lobe over the train bridge
    anchors=((-10.2, 0.0, 1.22), (-10.85, -1.5, 0.74), (-11.45, -2.92, 1.16)))
COUPLING_COCK_SCREW = (-11.45, -2.92)
#: Jewel sink sized for the r1.15 heads (flat top r0.93 after the 0.22
#: bevel): shallower/narrower than the base default so the polished cone
#: never nicks the anglage ring, and the seat floor (z1 - 0.28) stays inside
#: the 0.38 plate.
_CHRONO_SINK_KW = dict(cone_r=0.88, wall_r=0.66, cone_z=0.14, seat_z=0.28,
                       bore_r=0.26)

_BRIDGE_TOP = M.BRIDGE_TOP_Z            # 2.85
_GAP = 0.01
# stud bases on bridge tops clear the 0.055-proud stripe-shadow skins
_BRIDGE_STUD_BASE = _BRIDGE_TOP + 0.07


def _cyl(r, h, z0):
    """Cylinder spanning z [z0, z0 + h] (default centered primitive)."""
    return Pos(0, 0, z0 + h / 2.0) * Cylinder(r, h)


def _fuse2d(pieces, clip_r=13.4):
    """ONE multi-operand sketch fuse + regularizing clip (see /BUGS.md)."""
    prof = pieces[0] + pieces[1:] if len(pieces) > 1 else pieces[0]
    return prof & Circle(clip_r)


def _chain(chains, extra=(), cuts2d=(), clip_r=13.4):
    """Smooth lever profile: capsule chains (circles joined by CCW chord
    quads) fused in ONE operation — the straight polished flanks of a real
    lever (same pattern as `_mvt_keyless`)."""
    pieces = []
    for pts in chains:
        for i, (x, y, r) in enumerate(pts):
            pieces.append(Pos(x, y) * Circle(r))
            if i == 0:
                continue
            x0, y0, r0 = pts[i - 1]
            d = math.hypot(x - x0, y - y0)
            if d < 1e-6:
                continue
            px, py = -(y - y0) / d, (x - x0) / d
            pieces.append(Polygon(
                (x0 - px * r0, y0 - py * r0),
                (x - px * r, y - py * r),
                (x + px * r, y + py * r),
                (x0 + px * r0, y0 + py * r0),
                align=None,
            ))
    pieces.extend(extra)
    prof = _fuse2d(pieces, clip_r)
    for c in cuts2d:
        prof = prof - c
    return prof


def _ang(frm, to):
    return math.degrees(math.atan2(to[1] - frm[1], to[0] - frm[0]))


def _pol(cx, cy, r, deg):
    a = math.radians(deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def _finish(part, label, color):
    part.label = label
    part.color = Color(*color)
    return part


def _bop_clean(shape):
    """True when BRepAlgoAPI_Check finds no faults (matches what
    `inspect validate` keys its selfIntersecting reason on)."""
    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
        ch = BRepAlgoAPI_Check(shape.wrapped, True, True)
        ch.Perform()
        return bool(ch.IsValid())
    except Exception:
        return True


def _lever(profile, z_band, label, anglage=S.ANGLAGE_WIDTH_SMALL,
           color=S.STEEL_LEVER, cuts=()):
    """Extrude a lever plate, apply top anglage BEFORE the bore cuts
    (chamfer-after-boolean is the OCC segfault class, /BUGS.md).

    F.safe_chamfer only checks volume > 0, but on some capsule-chain
    perimeters OCC returns a positive-volume chamfer whose skinny faces are
    BOP self-intersecting (probe-verified on the reset/brake levers) — so
    each width is also gated on `_bop_clean` and stepped down on failure."""
    body = Pos(0, 0, z_band[0]) * extrude(profile, amount=z_band[1] - z_band[0])
    w = anglage
    while w >= 0.04:
        trial, applied = F.anglage_top(body, w)
        if applied is not None and _bop_clean(trial):
            body = trial
            break
        w *= 0.7
    if cuts:
        body = body - list(cuts)
    return _finish(body, label, color)


def _screw_head(head_d=1.1, hh=0.24, slot_angle=0.0, color=S.BLUED):
    """Flat mirror-top slotted screw head, top at z = 0, hanging below —
    the same constructive read as `_mvt_base._screw` (domed F.slotted_screw
    caps render as featureless blobs at macro; see /BUGS.md)."""
    r = head_d / 2.0
    ch = min(0.07, 0.30 * hh)
    depth = min(0.16, hh - 0.06)
    head = _cyl(r, hh - ch, -hh) + Pos(0, 0, -ch / 2) * Cone(r, r - ch, ch)
    slot = Rot(0, 0, slot_angle) * Box(head_d + 0.5, 0.2 * head_d, 2 * depth)
    s = head - slot
    s.color = Color(*color)
    return s


def _stud_and_screw(parts, x, y, base_z, lever_z0, lever_z1, label,
                    shaft_r=0.40, head_d=1.1):
    """Shoulder stud (STEEL_DARK) + blued retaining screw head at a lever
    pivot: slim turned post from the plate/bridge, short shoulder collar
    just under the lever (full-height fat pillars read as scaffolding in
    the round-1 render), shaft through the bore, screw head on top."""
    collar_h = min(0.30, lever_z0 - 0.02 - base_z)
    post = _cyl(min(shaft_r - 0.06, 0.32), lever_z0 - 0.02 - base_z, base_z)
    shoulder = _cyl(shaft_r + 0.14, collar_h, lever_z0 - 0.02 - collar_h)
    shaft = _cyl(shaft_r, (lever_z1 + 0.02) - base_z, base_z)
    stud = Pos(x, y, 0) * (post + [shoulder, shaft])
    parts.append(_finish(stud, f"stud:{label}", S.STEEL_DARK))
    slot = (x * 47.9 + y * 83.3) * 57.29578 % 180.0
    hh = 0.24
    head = Pos(x, y, lever_z1 + 0.02 + hh) * _screw_head(
        head_d=head_d, hh=hh, slot_angle=slot)
    parts.append(_finish(head, f"screw:{label}", S.BLUED))


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


def _gilt_wheel(teeth, tip_r, pos, z_band, mesh_toward, frac=0.08,
                bore=0.36, spokes=True, rot=None):
    """Crossed-out gilt chrono wheel at `pos`, web spanning `z_band`,
    tooth phase aimed at `mesh_toward` (or an explicit `rot` degrees —
    F.train_wheel centers a TOOTH at local +X)."""
    od = 2.0 * tip_r
    thick = z_band[1] - z_band[0]
    w = F.train_wheel(teeth, od, web_thickness=thick, tooth_depth_frac=frac,
                      spoke_count=5 if spokes else 0)
    cuts = [_cyl(bore, 3.0, -1.5)]
    if spokes:
        cuts.append(_window_cutter(od, frac))
    w = w - cuts
    if rot is None:
        rot = _ang(pos, mesh_toward) if mesh_toward is not None else 0.0
    return Pos(pos[0], pos[1], (z_band[0] + z_band[1]) / 2.0) * Rot(0, 0, rot) * w


# ---------------------------------------------------------------------------
# 1. Column wheel — lower ratchet star, 7 polished columns, cap, blued screw
# ---------------------------------------------------------------------------

def _column_wheel_parts():
    parts = []

    # ratchet star: 21 crisp sawtooth teeth in ONE CCW polygon (rise from
    # root to tip over 3/4 pitch, steep drive-face chord back to the root)
    pitch = 360.0 / STAR_TEETH
    pts = []
    for k in range(STAR_TEETH):
        a = STAR_PHASE + k * pitch
        pts.append(_pol(0, 0, STAR_ROOT_R, a))
        pts.append(_pol(0, 0, STAR_TIP_R, a + 0.75 * pitch))
    star2d = Polygon(*pts, align=None) + [Circle(STAR_ROOT_R + 0.01)]
    star = Pos(0, 0, STAR_Z[0]) * extrude(star2d, amount=STAR_Z[1] - STAR_Z[0])

    # 7 upright polished columns: clean radial wedge prisms (straight
    # flanks — bulged flanks read as melted blobs at macro, round-1 render)
    # with 45-deg chamfered tops baked in (taper cap — OCC chamfer on these
    # rings is the segfault class)
    wedge2d = Polygon(
        _pol(0, 0, COL_R_IN, -COL_HALF_DEG),
        _pol(0, 0, COL_R_OUT, -COL_HALF_DEG),
        _pol(0, 0, COL_R_OUT * 1.006, 0.0),
        _pol(0, 0, COL_R_OUT, COL_HALF_DEG),
        _pol(0, 0, COL_R_IN, COL_HALF_DEG),
        _pol(0, 0, COL_R_IN * 1.006, 0.0),
        align=None,
    )
    ch = 0.14
    h = COLUMN_Z[1] - COLUMN_Z[0]
    proto = (Pos(0, 0, COLUMN_Z[0]) * extrude(wedge2d, amount=h - ch)
             + extrude(Pos(0, 0, COLUMN_Z[1] - ch) * wedge2d, amount=ch,
                       taper=45))
    cols = [Rot(0, 0, COL_PHASE + k * COL_PITCH) * proto
            for k in range(S.COLUMN_COUNT)]
    # ONE fused body with the star + hub pedestal/core (disjoint solids fused
    # pairwise decay to ShapeList; a real column wheel is one machined piece)
    body = star + (cols + [
        _cyl(0.95, STAR_Z[0] - _BRIDGE_STUD_BASE, _BRIDGE_STUD_BASE),
        _cyl(0.95, 3.56 - STAR_Z[1], STAR_Z[1] - 0.01),   # core: 0.02 under cap
    ])
    body = body - _cyl(0.35, 2.0, 2.5)
    body = Pos(CWX, CWY, 0) * body
    parts.append(_finish(body, "column_wheel", S.STEEL_LEVER))

    # polished cap disk inside the column ring (large, chamfered rim — the
    # cap + big slotted screw dominate the center in the reference macro)
    cap = (_cyl(1.16, 0.12, 3.58) + Pos(0, 0, 3.58 + 0.12 + 0.035) *
           Cone(1.16, 1.09, 0.07)) - _cyl(0.34, 1.0, 3.4)
    parts.append(_finish(Pos(CWX, CWY, 0) * cap, "column_wheel_cap",
                         S.STEEL_BRIGHT))
    hh = 0.20
    head = Pos(CWX, CWY, 3.78 + hh) * _screw_head(head_d=1.25, hh=hh,
                                                  slot_angle=63.0)
    core = Pos(CWX, CWY, 0) * _cyl(0.33, 3.80 - 3.3, 3.3)
    parts.append(_finish(head + core, "screw:column_wheel", S.BLUED))
    return parts


# ---------------------------------------------------------------------------
# 2. Chronograph runner — gilt fine-tooth wheel, heart cam, extended arbor
# ---------------------------------------------------------------------------

def _runner_parts():
    parts = []
    wheel = _gilt_wheel(72, RUNNER_TIP_R, (0.0, 0.0), WHEEL_Z,
                        (CPX, CPY), frac=0.06, bore=0.32)
    parts.append(_finish(wheel, "chrono_runner_wheel", S.GILT))

    # heart cam: low point (bottom lobe) faces the hammer-A pad; tip away
    cam_rot = _ang((0, 0), HAMMER_PIVOT) + 90.0   # default bottom at -90 deg
    cam = F.heart_cam(diameter=3.2, thickness=CAM_Z[1] - CAM_Z[0], bore=0.62)
    cam = Pos(0, 0, CAM_Z[0]) * Rot(0, 0, cam_rot) * cam
    parts.append(_finish(cam, "chrono_runner_heart_cam", S.STEEL_BRIGHT))

    # arbor: hovers over the center jewel table (probe-measured top 2.933 in
    # the current _mvt_base), carries wheel seat, cam, a retaining collet and
    # a turned upper pivot running in the chronograph bridge's jewel — the
    # old bare 3.99-tall post was the blind critics' "unsupported upper
    # pivot" read
    arbor = (_cyl(0.30, 3.62 - 2.95, 2.95)
             + _cyl(0.44, 0.10, 3.16)             # wheel seat shoulder
             + _cyl(0.40, 0.05, 3.60)             # collet over the cam
             + _cyl(0.10, 3.92 - 3.60, 3.60))     # pivot into the bridge jewel
    # minute-recorder drive finger, dropped BELOW the cam (3.18..3.30, over
    # the wheel top 3.14): the chronograph bridge now owns the band above
    finger2d = _chain([[(0.0, 0.0, 0.34), (1.55, -0.45, 0.17)]], clip_r=3.0)
    finger = (Pos(0, 0, 3.18)
              * Rot(0, 0, _ang((0, 0), (MRX, MRY)) + 14)
              * extrude(finger2d, amount=0.12))
    arbor = arbor + finger
    parts.append(_finish(arbor, "chrono_runner_arbor", S.STEEL_DARK))
    return parts


# ---------------------------------------------------------------------------
# 3. Minute recorder — 30-tooth wheel, heart cam, polished jumper + spring
# ---------------------------------------------------------------------------

def _minute_recorder_parts():
    parts = []
    # tooth phase: the jumper nose azimuth must land in a tooth GAP (a tooth
    # sits half a pitch away on either side)
    nose_az = _ang((MRX, MRY), (9.54, -2.46))
    pitch = 360.0 / S.MINUTE_RECORDER_TEETH
    wheel = _gilt_wheel(S.MINUTE_RECORDER_TEETH, MINUTE_REC_TIP_R,
                        (MRX, MRY), WHEEL_Z, None, frac=0.12,
                        bore=0.38, spokes=False, rot=nose_az + pitch / 2.0)
    parts.append(_finish(wheel, "minute_recorder_wheel", S.GILT))

    # heart cam: low point faces the hammer-B pad
    cam_rot = _ang((MRX, MRY), HAMMER_PIVOT) + 90.0
    cam = F.heart_cam(diameter=2.6, thickness=CAM_Z[1] - CAM_Z[0], bore=0.74)
    cam = Pos(MRX, MRY, CAM_Z[0]) * Rot(0, 0, cam_rot) * cam
    parts.append(_finish(cam, "minute_recorder_heart_cam", S.STEEL_BRIGHT))

    # recorder post: planted in the plate, shoulder under the wheel, collet
    # over the cam, turned pivot up into the chronograph bridge's jewel (was
    # a bare 3.91-tall post — the critics' unsupported-arbor read)
    post = (_cyl(0.55, 1.2, _GAP) + _cyl(0.36, 3.62 - _GAP, _GAP)
            + _cyl(0.42, 0.05, 3.60)
            + _cyl(0.10, 3.92 - 3.60, 3.60))
    parts.append(_finish(Pos(MRX, MRY, 0) * post, "minute_recorder_post",
                         S.STEEL_DARK))

    # polished jumper: pivoted detent, V-nose seated in the tooth gap at
    # nose_az (apex 0.16 inside the tip circle; flank clearance ~0.04 to the
    # neighboring tooth corners, computed against F.train_wheel's 36%-pitch
    # tooth width). Point order CCW — a CW Polygon shatters the fuse.
    apex = _pol(MRX, MRY, MINUTE_REC_TIP_R - 0.16, nose_az)
    heel_l = _pol(MRX, MRY, MINUTE_REC_TIP_R + 0.28, nose_az - 8.5)
    heel_r = _pol(MRX, MRY, MINUTE_REC_TIP_R + 0.28, nose_az + 8.5)
    nose2d = Polygon(heel_r, apex, heel_l, align=None)
    heel_mid = _pol(MRX, MRY, MINUTE_REC_TIP_R + 0.34, nose_az)
    prof = _chain(
        [[(JUMPER_PIVOT[0], JUMPER_PIVOT[1], 0.50),
          (9.75, -2.78, 0.26),
          (heel_mid[0], heel_mid[1], 0.20)],
         [(JUMPER_PIVOT[0], JUMPER_PIVOT[1], 0.50),      # spring tail
          (10.45, -3.55, 0.24)]],
        extra=[nose2d])
    jumper = _lever(prof, (LEVER_Z[0], LEVER_Z[0] + 0.14), "minute_jumper",
                    cuts=[Pos(JUMPER_PIVOT[0], JUMPER_PIVOT[1], 0)
                          * _cyl(0.42, 1.0, 2.8)])
    parts.append(jumper)
    _stud_and_screw(parts, JUMPER_PIVOT[0], JUMPER_PIVOT[1], _GAP,
                    LEVER_Z[0], LEVER_Z[0] + 0.14, "minute_jumper",
                    head_d=1.0)

    # jumper spring: separate blade from its own stud, pressing the tail
    blade = _chain(
        [[(JUMPER_SPRING_STUD[0], JUMPER_SPRING_STUD[1], 0.40),
          (11.05, -3.38, 0.13),
          (10.792, -3.455, 0.075)]])
    spring = _lever(blade, (LEVER_Z[0] + 0.02, LEVER_Z[0] + 0.14),
                    "minute_jumper_spring", anglage=0.04,
                    color=S.STEEL_DARK,
                    cuts=[Pos(JUMPER_SPRING_STUD[0], JUMPER_SPRING_STUD[1], 0)
                          * _cyl(0.30, 1.0, 2.8)])
    parts.append(spring)
    _stud_and_screw(parts, JUMPER_SPRING_STUD[0], JUMPER_SPRING_STUD[1], _GAP,
                    LEVER_Z[0] + 0.02, LEVER_Z[0] + 0.14,
                    "minute_jumper_spring", shaft_r=0.28, head_d=0.9)
    return parts


# ---------------------------------------------------------------------------
# 4. Hour recorder — dial side: 24-tooth wheel, heart cam, friction spring
# ---------------------------------------------------------------------------

def _hour_recorder_parts():
    parts = []
    wheel = _gilt_wheel(S.HOUR_RECORDER_TEETH, HOUR_REC_TIP_R,
                        (HRX, HRY), (-2.02, -1.84), (0.0, 0.0), frac=0.12,
                        bore=0.38)
    parts.append(_finish(wheel, "hour_recorder_wheel", S.GILT))

    cam = F.heart_cam(diameter=2.8, thickness=0.36, bore=0.74)
    cam = Pos(HRX, HRY, -2.50) * Rot(0, 0, 235.0) * cam
    parts.append(_finish(cam, "hour_recorder_heart_cam", S.STEEL_BRIGHT))

    # post: shaft through wheel (bore 0.38) and cam (bore 0.37), seat collar
    # above the wheel, retaining collet below the cam — nothing wider than
    # the bores crosses the wheel/cam z bands
    post = (_cyl(0.36, 1.03, -2.55)              # shaft -2.55..-1.52
            + _cyl(0.55, 0.10, -1.62)            # seat under the plate
            + _cyl(0.42, 0.06, -2.58))           # collet under the cam
    post = Pos(HRX, HRY, 0) * post
    parts.append(_finish(post, "hour_recorder_post", S.STEEL_DARK))

    # friction spring: three-arm spring washer bearing on the wheel hub
    arms = []
    for k in range(3):
        a0 = 15.0 + 120.0 * k
        arms.append(Polygon(
            _pol(0, 0, 0.52, a0), _pol(0, 0, 1.55, a0 + 34.0),
            _pol(0, 0, 1.55, a0 + 48.0), _pol(0, 0, 0.52, a0 + 22.0),
            align=None))
    ring2d = _fuse2d([Circle(0.62) - Circle(0.40)] + arms, clip_r=2.0)
    spring = Pos(HRX, HRY, -1.82) * extrude(ring2d, amount=0.10)
    parts.append(_finish(spring, "hour_recorder_friction_spring",
                         S.STEEL_DARK))
    return parts


def _clutch_parts():
    """Lateral clutch: driving wheel on the fourth-wheel axis, long swinging
    clutch arm pivoted concentric with it, swinging intermediate (coupling)
    wheel held 0.15 off the runner's tip circle, beak riding ON the column
    at COL_PHASE (clutch disengaged), return spring pressing the arm."""
    parts = []

    # driving wheel above the fourth-wheel jewel boss, + its arbor stub
    drv = _gilt_wheel(54, DRIVING_TIP_R, (FWX, FWY), WHEEL_Z, (CPX, CPY),
                      frac=0.07, bore=0.34)
    parts.append(_finish(drv, "clutch_driving_wheel", S.GILT))
    # arbor with a retaining collar over the swinging arm's ring boss and a
    # turned pivot up into the coupling cock's jewel (replaces the old bare
    # retaining screw head: the cock caps this pivot properly now)
    arbor = Pos(FWX, FWY, 0) * (_cyl(0.32, 3.42 - 2.95, 2.95)
                                + _cyl(0.42, 0.06, 3.40)
                                + _cyl(0.10, 3.92 - 3.42, 3.42))
    parts.append(_finish(arbor, "clutch_driving_arbor", S.STEEL_DARK))

    # swinging clutch arm: ring boss at the driving arbor, long sculpted
    # sweep south of the train bridge, wheel boss at the coupling wheel,
    # feeler rising toward the column wheel. The star (z 3.16-3.40) owns the
    # plate band near the column axis, so the plate stops outside the star
    # tip circle and a stepped finger (riser + raised beak at column height)
    # reaches in to ride ON the column flank at COL_PHASE + COL_PITCH.
    beak_az = COL_PHASE + COL_PITCH
    plate_end = _pol(CWX, CWY, 2.85, beak_az)
    beak_tip = _pol(CWX, CWY, COL_R_OUT + 0.26 + 0.02, beak_az)
    prof = _chain(
        [[(FWX, FWY, 0.85), (-7.5, -2.4, 0.60), (-4.0, -3.9, 0.55),
          (-0.5, -4.8, 0.50), (2.8, -5.0, 0.50), (CPX, CPY, 0.85)],
         [(CPX, CPY, 0.85), (6.7, -2.9, 0.45), (7.6, -1.3, 0.36),
          (8.0, -0.1, 0.30), (plate_end[0], plate_end[1], 0.30)]])
    arm = _lever(prof, CLUTCH_Z, "clutch_arm",
                 cuts=[Pos(FWX, FWY, 0) * _cyl(0.34, 1.0, 3.0),
                       Pos(CPX, CPY, 0) * _cyl(0.32, 1.0, 3.0)])
    riser = Pos(plate_end[0], plate_end[1], 0) * _cyl(
        0.30, 3.62 - CLUTCH_Z[0], CLUTCH_Z[0])
    beak2d = _chain([[(plate_end[0], plate_end[1], 0.28),
                      (beak_tip[0], beak_tip[1], 0.26)]])
    beak = Pos(0, 0, 3.42) * extrude(beak2d, amount=0.20)
    arm = arm + [riser, beak]
    parts.append(_finish(arm, "clutch_arm", S.STEEL_LEVER))

    # coupling wheel on its shoulder stud under the arm (bore r 0.32)
    cpl = _gilt_wheel(92, COUPLING_TIP_R, (CPX, CPY), WHEEL_Z, (0.0, 0.0),
                      frac=0.06, bore=0.32)
    parts.append(_finish(cpl, "coupling_wheel", S.GILT))
    stud = Pos(CPX, CPY, 0) * (_cyl(0.30, CLUTCH_Z[1] - 2.90 + 0.02, 2.90)
                               + _cyl(0.44, 0.04, 2.90))
    parts.append(_finish(stud, "stud:coupling_wheel", S.STEEL_DARK))
    head = Pos(CPX, CPY, CLUTCH_Z[1] + 0.02 + 0.20) * _screw_head(
        head_d=1.0, hh=0.20, slot_angle=41.0)
    parts.append(_finish(head, "screw:coupling_wheel", S.BLUED))

    # clutch return spring: blade on its own train-bridge stud, pressing the
    # arm flank (keeps the beak on the column)
    sx, sy = CLUTCH_SPRING_STUD
    blade = _chain([[(sx, sy, 0.42), (-8.95, -3.62, 0.14), (-8.5, -3.2, 0.10),
                     (-8.12, -2.83, 0.09)]])
    spring = _lever(blade, (CLUTCH_Z[0] + 0.02, CLUTCH_Z[0] + 0.14),
                    "clutch_spring", anglage=0.04, color=S.STEEL_DARK,
                    cuts=[Pos(sx, sy, 0) * _cyl(0.30, 1.0, 3.0)])
    parts.append(spring)
    _stud_and_screw(parts, sx, sy, _BRIDGE_STUD_BASE,
                    CLUTCH_Z[0] + 0.02, CLUTCH_Z[0] + 0.14,
                    "clutch_spring", shaft_r=0.28, head_d=0.9)
    return parts


def _hammer_parts():
    """Hammer yoke: one sculptural mirror-polished two-arm lever striking
    BOTH heart cams simultaneously (reset-complete pose: flat faces on the
    cams' low points), with a column feeler dropped into a gap and a tail
    for the reset lever's nose."""
    parts = []
    hx, hy = HAMMER_PIVOT

    # striking faces: flat pads trimmed by tangent planes 0.03 outside each
    # cam's bottom-lobe radius (runner cam D3.2 -> lobe 1.248, plane 1.28;
    # minute cam D2.6 -> lobe 1.014, plane 1.04)
    az_a = _ang((0.0, 0.0), HAMMER_PIVOT)          # runner cam contact azimuth
    az_b = _ang((MRX, MRY), HAMMER_PIVOT)          # minute cam contact azimuth
    pad_a = _pol(0.0, 0.0, 1.70, az_a - 10.0)
    pad_b = _pol(MRX, MRY, 1.45, az_b + 10.0)
    feeler_tip = _pol(CWX, CWY, 1.50, COL_PHASE + 0.5 * COL_PITCH)

    prof = _chain(
        [[(pad_a[0], pad_a[1], 0.52), (3.2, -0.8, 0.56), (4.9, -0.75, 0.62),
          (hx, hy, 0.78)],
         [(hx, hy, 0.78), (7.8, -0.4, 0.55), (pad_b[0], pad_b[1], 0.50)],
         [(hx, hy, 0.78), (7.1, 0.9, 0.38), (7.3, 1.70, 0.32),
          (feeler_tip[0], feeler_tip[1], 0.26)],
         [(hx, hy, 0.78), (7.7, -1.15, 0.42)]])    # reset tail
    zmid = (HAMMER_Z[0] + HAMMER_Z[1]) / 2.0
    face_cut_a = Rot(0, 0, az_a) * Pos(1.28 - 4.0, 0, zmid) * Box(8, 10, 1.0)
    face_cut_b = (Pos(MRX, MRY, 0) * Rot(0, 0, az_b)
                  * Pos(1.04 - 4.0, 0, zmid) * Box(8, 10, 1.0))
    yoke = _lever(prof, HAMMER_Z, "hammer_yoke", color=S.STEEL_BRIGHT,
                  cuts=[Pos(hx, hy, 0) * _cyl(0.42, 1.0, 3.2),
                        face_cut_a, face_cut_b])
    parts.append(yoke)
    _stud_and_screw(parts, hx, hy, _GAP, HAMMER_Z[0], HAMMER_Z[1],
                    "hammer", shaft_r=0.40, head_d=1.2)
    return parts


def _operating_parts():
    """Operating lever from the 2-o'clock pusher region to the column-wheel
    star: pusher pad, pivot on the barrel bridge, beak resting in the star
    gap just past a drive face; separate return-spring blade."""
    parts = []
    px, py = OPER_PIVOT
    pad = _pol(0, 0, 12.7, 35.0)                   # pusher contact pad

    # beak: base circle clear of the tooth tip at STAR_PHASE's -10 deg tip,
    # triangular nose (CCW) resting at r 2.15 in the gap at -4.5 deg
    base = (10.95, 3.25)
    apex = _pol(CWX, CWY, 2.16, -4.0)
    d = math.hypot(apex[0] - base[0], apex[1] - base[1])
    ux, uy = (apex[0] - base[0]) / d, (apex[1] - base[1]) / d
    heel_a = (base[0] - 0.24 * uy, base[1] + 0.24 * ux)
    heel_b = (base[0] + 0.24 * uy, base[1] - 0.24 * ux)
    nose2d = Polygon(apex, heel_a, heel_b, align=None)   # CCW

    prof = _chain(
        [[(pad[0], pad[1], 0.65), (11.15, 6.2, 0.50), (px, py, 0.75),
          (11.15, 4.0, 0.40), (base[0], base[1], 0.26)]],
        extra=[nose2d])
    lever = _lever(prof, OPER_Z, "operating_lever",
                   cuts=[Pos(px, py, 0) * _cyl(0.42, 1.0, 2.8)])
    parts.append(lever)
    _stud_and_screw(parts, px, py, _BRIDGE_STUD_BASE, OPER_Z[0], OPER_Z[1],
                    "operating_lever", head_d=1.2)

    # return-spring blade on its own bridge stud, pressing the beak arm
    # toward the star (the cramped crown-wheel/column-wheel corner cannot
    # host a stud: probe-verified star/shoulder overlaps at every fit)
    sx, sy = OPER_SPRING_STUD
    blade = _chain([[(sx, sy, 0.40), (11.85, 3.05, 0.14),
                     (11.346, 3.182, 0.09)]])
    spring = _lever(blade, (3.20, 3.32), "operating_spring", anglage=0.04,
                    color=S.STEEL_DARK,
                    cuts=[Pos(sx, sy, 0) * _cyl(0.30, 1.0, 2.8)])
    parts.append(spring)
    _stud_and_screw(parts, sx, sy, _BRIDGE_STUD_BASE, 3.20, 3.32,
                    "operating_spring", shaft_r=0.28, head_d=0.9)
    return parts


def _reset_parts():
    """Reset lever from the 4-o'clock pusher region to the hammer tail
    (nose 0.05 off the tail: reset just completed), + return spring."""
    parts = []
    px, py = RESET_PIVOT
    pad = _pol(0, 0, 12.7, -35.0)
    prof = _chain(
        [[(pad[0], pad[1], 0.62), (px, py, 0.72),
          (8.9, -4.6, 0.48), (8.3, -3.2, 0.38), (8.1, -2.55, 0.33),
          (7.953, -1.878, 0.30)]])
    lever = _lever(prof, RESET_Z, "reset_lever",
                   cuts=[Pos(px, py, 0) * _cyl(0.42, 1.0, 3.2)])
    parts.append(lever)
    _stud_and_screw(parts, px, py, _GAP, RESET_Z[0], RESET_Z[1],
                    "reset_lever", head_d=1.2)

    sx, sy = RESET_SPRING_STUD
    blade = _chain([[(sx, sy, 0.40), (11.15, -6.06, 0.13),
                     (10.815, -6.212, 0.09)]])
    spring = _lever(blade, (RESET_Z[0] + 0.02, RESET_Z[0] + 0.14),
                    "reset_spring", anglage=0.04, color=S.STEEL_DARK,
                    cuts=[Pos(sx, sy, 0) * _cyl(0.30, 1.0, 3.2)])
    parts.append(spring)
    _stud_and_screw(parts, sx, sy, _GAP, RESET_Z[0] + 0.02, RESET_Z[0] + 0.14,
                    "reset_spring", shaft_r=0.28, head_d=0.9)
    return parts


def _brake_parts():
    """Brake (blocking) lever: pad against the runner rim (brake ON at
    rest), pivoted on the barrel bridge, + its return-spring blade."""
    parts = []
    px, py = BRAKE_PIVOT
    pad = _pol(0, 0, RUNNER_TIP_R + 0.44, 135.6)   # rim gap 0.02
    prof = _chain(
        [[(pad[0], pad[1], 0.42), (-3.2, 2.65, 0.45), (px, py, 0.62),
          (-4.75, 2.35, 0.40), (-4.95, 2.20, 0.35)]])
    brake_z = (3.02, 3.18)
    pad_boss = Pos(pad[0], pad[1], 0) * _cyl(0.42, brake_z[0] - 2.98, 2.98)
    lever = _lever(prof, brake_z, "brake_lever",
                   cuts=[Pos(px, py, 0) * _cyl(0.42, 1.0, 2.8)])
    lever = lever + pad_boss
    parts.append(_finish(lever, "brake_lever", S.STEEL_LEVER))

    _stud_and_screw(parts, px, py, _BRIDGE_STUD_BASE, brake_z[0], brake_z[1],
                    "brake_lever", head_d=1.1)

    sx, sy = BRAKE_SPRING_STUD
    blade = _chain([[(sx, sy, 0.40), (-5.32, 3.30, 0.13),
                     (-5.13, 2.70, 0.09)]])
    spring = _lever(blade, (3.04, 3.16), "brake_spring", anglage=0.04,
                    color=S.STEEL_DARK,
                    cuts=[Pos(sx, sy, 0) * _cyl(0.30, 1.0, 2.8)])
    parts.append(spring)
    _stud_and_screw(parts, sx, sy, _BRIDGE_STUD_BASE, 3.04, 3.16,
                    "brake_spring", shaft_r=0.28, head_d=0.9)
    return parts


def _trim_skins(shadow, screw_xy, z1):
    """Clear the stripe-shadow skins around proud screw heads: the base
    `_bridge` sink tool stops AT z1, but the skins ride 0.02..0.055 above it
    on the band edges, so a screw head (r0.65, top z1 + 0.04 + hh) can clip a
    surviving sliver (probe-caught 0.009 overlaps; the base bridges only
    dodge this by screw placement luck). Subtract a generous r0.90 column at
    each screw from every skin solid and re-split."""
    if not shadow:
        return shadow
    tools = [Pos(x, y, 0) * _cyl(0.90, 1.0, z1 - 0.6) for x, y in screw_xy]
    out = []
    for s in shadow:
        t = s - tools
        sols = (t.solids() if hasattr(t, "solids")
                else [q for shp in t for q in shp.solids()])
        out.extend(q for q in sols if q.volume > 1e-6)
    return out or None


def _chrono_bridge_parts():
    """Chronograph bridge + coupling cock: the striped copper layer capping
    the chrono train's upper pivots (plan constants above). Built with
    `_mvt_base`'s bridge factory so circular striping about the movement
    center, the constructive 45-deg anglage + polished ribbon overlay, the
    jewel countersink/chaton/ruby stack and the screw sinks all match the
    base bridges exactly — one finishing vocabulary across the movement."""
    parts = []
    z0, z1 = CHRONO_BRIDGE_Z

    body, shadow, ribbon = M._bridge(
        CHRONO_BRIDGE_OUTLINE, z0, z1,
        [(0.0, 0.0), (MRX, MRY)], CHRONO_BRIDGE_SCREWS,
        cutouts=CHRONO_BRIDGE_WINDOWS,
        jewel_sink_kw=_CHRONO_SINK_KW)
    # full-height turned feet through wheel-free plate (bottom face of the
    # plate is un-beveled, so the 0.02 weld overlap fuses cleanly)
    feet = [Pos(x, y, 0) * _cyl(r, (z0 + 0.02) - bz, bz)
            for x, y, r, bz in CHRONO_BRIDGE_FEET]
    body = body + feet
    parts.append(_finish(body, "chrono_bridge", S.COPPER_GOLD))
    shadow = _trim_skins(shadow, CHRONO_BRIDGE_SCREWS, z1)
    M._add_shadow(parts, shadow, "chrono_bridge")
    M._add_anglage(parts, ribbon, "chrono_bridge")

    # jeweled countersunk bearings: domed ruby stone (rim 0.11 under the
    # striped top so the 0.14 dome apex stays z1 + 0.03 <= CHRONO_LAYER_TOP;
    # body bottom z1 - 0.27 clears the z1 - 0.28 seat floor) nested in a
    # gold chaton ring on the seat floor — the ruby/gold/moat/polished-cone
    # concentric read of the base train jewels. The runner / recorder /
    # coupling pivots (r0.10) rise into the ruby's 0.12 bore.
    jewels = (((0.0, 0.0), "chrono_runner"), ((MRX, MRY), "minute_recorder"))
    for (x, y), name in jewels:
        ruby = Pos(x, y, z1 - 0.11) * M._ruby_disc(r=0.42, t=0.16, hole_r=0.12)
        parts.append(_finish(ruby, f"bridge_jewel:{name}", S.RUBY))
        chaton = Pos(x, y, 0) * M._ring(0.43, 0.64, 0.18, z1 - 0.28)
        parts.append(_finish(chaton, f"chaton:{name}", S.BRASS_MOVEMENT))
    for (x, y), name in zip(CHRONO_BRIDGE_SCREWS, ("east", "south", "west")):
        parts.append(_finish(
            M._place_screw(x, y, z1, proud=0.04, shank=0.30),
            f"screw:chrono_bridge:{name}", S.BLUED))

    # coupling cock --------------------------------------------------------
    body2, shadow2, ribbon2 = M._bridge(
        COUPLING_COCK_OUTLINE, z0, z1,
        [(FWX, FWY)], [COUPLING_COCK_SCREW],
        jewel_sink_kw=_CHRONO_SINK_KW)
    sx, sy = COUPLING_COCK_SCREW
    # sleeve foot standing on the train-bridge top: weld the SOLID foot
    # first, then re-cut one continuous r0.45 screw bore through plate +
    # foot (pre-boring the foot left coincident bore walls at the weld —
    # BOP-self-intersecting, probe-verified)
    foot = Pos(sx, sy, 0) * _cyl(
        0.60, (z0 + 0.02) - _BRIDGE_STUD_BASE, _BRIDGE_STUD_BASE)
    body2 = (body2 + foot) - Pos(sx, sy, 0) * _cyl(
        0.45, (z1 + 0.1) - (_BRIDGE_STUD_BASE - 0.2), _BRIDGE_STUD_BASE - 0.2)
    parts.append(_finish(body2, "coupling_bridge", S.COPPER_GOLD))
    shadow2 = _trim_skins(shadow2, [COUPLING_COCK_SCREW], z1)
    M._add_shadow(parts, shadow2, "coupling_bridge")
    M._add_anglage(parts, ribbon2, "coupling_bridge")
    ruby = Pos(FWX, FWY, z1 - 0.11) * M._ruby_disc(r=0.42, t=0.16, hole_r=0.12)
    parts.append(_finish(ruby, "bridge_jewel:coupling", S.RUBY))
    chaton = Pos(FWX, FWY, 0) * M._ring(0.43, 0.64, 0.18, z1 - 0.28)
    parts.append(_finish(chaton, "chaton:coupling", S.BRASS_MOVEMENT))
    parts.append(_finish(
        M._place_screw(sx, sy, z1, proud=0.04, shank=0.70),
        "screw:coupling_bridge", S.BLUED))
    return parts


def build_chrono():
    """All chronograph-works parts, labeled and colored, movement frame."""
    parts = []
    parts += _column_wheel_parts()
    parts += _runner_parts()
    parts += _minute_recorder_parts()
    parts += _hour_recorder_parts()
    parts += _clutch_parts()
    parts += _hammer_parts()
    parts += _operating_parts()
    parts += _reset_parts()
    parts += _brake_parts()
    parts += _chrono_bridge_parts()

    # Per-component export drops the color of bare-`Compound` leaves (see
    # /BUGS.md) — coerce every leaf to Part and reattach label/color.
    from build123d import Compound, Part
    out = []
    for p in parts:
        if isinstance(p, Compound) and not isinstance(p, Part):
            q = Part(p.wrapped)
            q.label, q.color = p.label, p.color
            p = q
        out.append(p)
    return out
