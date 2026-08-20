"""Keyless and motion works cluster: stem, winding pinion, sliding (castle)
pinion, setting lever + setting lever spring, yoke, cannon pinion, minute
wheel + pinion, hour wheel — the dial-side layer of the caliber-321-lineage
movement at 3 o'clock (+X).

Frame: MOVEMENT local (see `_spec.py`) — bridge side up, z = 0 at the plate's
bridge-side face. The dial side lies below z = -PLATE_THICKNESS (-1.5).
Everything here stays in the dial-side band z [-2.64, -1.5] EXCEPT:

- the stem and its two pinions, which ride the stem axis at
  z = STEM_AXIS_Z_LOCAL (-0.55) inside the plate's keyless recess (the base
  plate carries the matching radial bore), and
- the cannon / hour wheel pipes, which extend below -2.64 because they pass
  through the dial at assembly (pipe ends ~ -3.4 / -3.1).

`_finishing.py`'s align=(None,None,None) datum quirks are
compensated locally exactly as `_mvt_base.py` does: `F.pinion` spans
z [0, L]; `F.slotted_screw` gets corrective shank/slot cuts via `_screw`.

Motion-works mesh (module consistency, verified tip/root sums):

- cannon pinion 12 leaves, tip Ø1.40 (root r 0.434 via F.pinion's 0.62)
- minute wheel 36 t, tip Ø4.20, tooth frac 0.12 (root r 1.848)
  -> center distance 1.848 + 0.700 = 2.548 ~ 2.1 + 0.434 = 2.534 -> 2.54
- minute pinion 10 leaves, tip Ø1.15 (root r 0.357)
- hour wheel 40 t, tip Ø4.37, tooth frac 0.10 (root r 1.967)
  -> center distance 1.967 + 0.575 = 2.542 ~ 2.185 + 0.357 = 2.542 -> 2.54
  (coaxial pairs at (0,0) share ONE minute-wheel post distance; ratios
  12->36 = 3.0, 10->40 = 4.0, total 12:1)
"""

from __future__ import annotations

import math

from build123d import (
    Box,
    Circle,
    Color,
    Cylinder,
    Polygon,
    Pos,
    Rot,
    extrude,
)

import _spec as S
import _finishing as F

# ---------------------------------------------------------------------------
# Exported layout constants (READ-ONLY for other builders)
# ---------------------------------------------------------------------------

STEM_Z = S.STEM_AXIS_Z_LOCAL                 # -0.55 (stem axis, +X / 3 o'clock)
LEVER_Z = (-1.88, -1.58)                     # setting lever / yoke plate band
SPRING_Z = (-2.06, -1.94)                    # setting-lever-spring blade band

MOTION_CENTER_DIST = 2.56                    # cannon<->minute AND minute-pinion<->hour
                                             # (tip/root sums 2.542-2.548 + running clearance)
_MW_ANG = math.atan2(-1.6, 2.6)              # toward the suggested (2.6, -1.6)
MINUTE_WHEEL_POS = (
    MOTION_CENTER_DIST * math.cos(_MW_ANG),  # ~ (2.163, -1.331)
    MOTION_CENTER_DIST * math.sin(_MW_ANG),
)

CANNON_TIP_D = 1.40
MINUTE_TIP_D = 4.20
MINUTE_TOOTH_FRAC = 0.12
MINUTE_PINION_TIP_D = 1.15
HOUR_TIP_D = 4.37
HOUR_TOOTH_FRAC = 0.10

# z plan (motion works, dial side; dial-facing surfaces are the LOW z)
_CANNON_LEAF_Z = (-2.00, -1.60)              # meshes minute wheel web
_MINUTE_WEB_Z = -1.80                        # minute wheel web mid-plane
_MINUTE_PINION_Z = (-2.45, -2.00)            # meshes hour wheel web
_HOUR_WEB_Z = -2.25                          # hour wheel web mid-plane
_CANNON_PIPE_END = -3.40                     # minute hand seat (through dial)
_HOUR_PIPE_END = -3.10                       # hour hand seat (through dial)

# stem plan (local build axis Z maps to +X; x = 8.5 + local z)
_STEM_X0 = 8.5                               # pilot tip (inner end)
_SQ_SIDE = 0.85                              # winding-square side
_SEAT_R = 0.475                              # winding-pinion seat radius
_NECK_R = 0.34                               # setting-lever groove neck
_STEM_SEGS = (
    # (kind, length, size) walking outward from x = 8.5
    ("pilot", 1.05, 0.28),
    ("square", 1.60, _SQ_SIDE),
    ("seat", 0.80, _SEAT_R),
    ("collar", 0.18, 0.575),
    ("neck", 0.50, _NECK_R),
    ("collar", 0.18, 0.575),
    ("thread", 0.69, 0.44),
)                                            # total 5.0 -> outer end x 13.5
_GROOVE_X = 12.38                            # setting-lever groove center

# castle wheel (sliding pinion) on the square, winding pinion on the seat
_CASTLE_X = (9.85, 11.00)
_CASTLE_R = 0.95
_CASTLE_GROOVE = (10.42, 0.38, 0.68)         # (x center, width, neck radius)
_WINDING_X = (11.15, 11.95)
_WINDING_R = 1.05
_CROWN_TEETH = 12


def _cyl(r, h, z0):
    """Cylinder spanning z [z0, z0 + h] (default centered primitive)."""
    return Pos(0, 0, z0 + h / 2.0) * Cylinder(r, h)


def _fuse2d(pieces, clip_r=14.0):
    """ONE multi-operand sketch fuse + a regularizing clip.

    Sketch algebra footgun (measured): pairwise `a + b` on 2D shapes decays
    to Face after the first fuse, `Face + Polygon` returns a raw ShapeList
    face pile, and `ShapeList & Circle` is silently EMPTY — the part then
    extrudes to nothing. The list-operand fuse (`first + [rest]`, as
    `F.train_wheel` uses) keeps a clean single face."""
    prof = pieces[0] + pieces[1:] if len(pieces) > 1 else pieces[0]
    return prof & Circle(clip_r)


def _blob(circles, clip_r=14.0):
    """2D union of (x, y, r) circles."""
    return _fuse2d([Pos(x, y) * Circle(r) for x, y, r in circles], clip_r)


def _chain(chains, extra=(), clip_r=14.0):
    """Smooth lever profile: one or more capsule chains — circles joined by
    chord quads — fused in ONE operation. Raw circle blobs read as bubble
    chains at macro scale; the quads give the straight polished flanks of
    a real lever."""
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
            # counterclockwise winding — a clockwise Polygon fuses as a
            # REVERSED face and shatters the union (measured)
            pieces.append(Polygon(
                (x0 - px * r0, y0 - py * r0),
                (x - px * r, y - py * r),
                (x + px * r, y + py * r),
                (x0 + px * r0, y0 + py * r0),
                align=None,
            ))
    pieces.extend(extra)
    return _fuse2d(pieces, clip_r)


def _ang(frm, to):
    return math.degrees(math.atan2(to[1] - frm[1], to[0] - frm[0]))


def _finish(part, label, color):
    part.label = label
    part.color = Color(*color)
    return part


def _edges_at_z(part, z, tol=1e-4):
    return [
        e
        for e in part.edges()
        if abs(e.bounding_box().max.Z - z) < tol
        and abs(e.bounding_box().min.Z - z) < tol
    ]


def _screw(head_d=S.SCREW_HEAD_DIAMETER, hh=0.32, shank=0.9,
           slot_w=S.SCREW_SLOT_WIDTH, color=S.BLUED):
    """F.slotted_screw + corrective cuts (align datum): flatten
    the shank stub poking through the dome, cut a proper centered slot.
    Returns (part, top): head apex ~ local z = top, shank hanging below."""
    s = F.slotted_screw(head_diameter=head_d, head_height=hh,
                        shank_length=shank, slot_width=slot_w, color=color)
    r = head_d / 2.0
    apex = min(hh / 2.0, 0.2 * r)
    top = apex - 0.038
    s = s - Pos(0, 0, top + 0.5) * Box(head_d * 3, head_d * 3, 1.0)
    depth = min(0.16, hh * 0.5)
    s = s - Pos(0, 0, top + 0.3 - depth) * Box(head_d * 2.2, slot_w, 0.6)
    s.color = Color(*color)
    return s, top


def _dial_screw(x, y, bearing_z, **kw):
    """Screw flipped for the dial side: dome faces -Z (the viewer), shank
    runs UP through the sprung part into the plate. `bearing_z` = the face
    the head bears on (the spring's dial-side surface)."""
    s, _top = _screw(**kw)
    hh = kw.get("hh", 0.32)
    s = Rot(180, 0, 0) * s                    # apex down, shank up
    return Pos(x, y, bearing_z - hh / 2.0) * s


# ---------------------------------------------------------------------------
# Crown-toothed stem pinions (winding pinion + sliding/castle pinion)
# ---------------------------------------------------------------------------

def _crown_pinion(r_out, length, r_inner, n_teeth=_CROWN_TEETH,
                  tooth_depth=0.30, teeth_ends=(0.0,), bore_round=None,
                  bore_square=None, groove=None, side_teeth=0,
                  side_z=None):
    """Crown-toothed pinion, local axis Z spanning z [0, length].

    Face teeth are V-grooves (45-degree rotated boxes) cut into the named
    end(s), leaving sharp triangular crown teeth. Optional side_teeth cuts
    axial V-grooves around the outer wall (winding pinion's bevel-tooth
    band). `groove` = (z_center, width, neck_r) annular yoke groove.
    """
    body = _cyl(r_out, length, 0.0)
    body, _ = F.safe_chamfer(
        body, _edges_at_z(body, 0.0) + _edges_at_z(body, length), 0.07)

    cuts = []
    if bore_round is not None:
        cuts.append(_cyl(bore_round, length + 1.0, -0.5))
    if bore_square is not None:
        cuts.append(Pos(0, 0, length / 2.0)
                    * Box(bore_square, bore_square, length + 1.0))
    w = tooth_depth * 1.4142                  # V-groove half-diag = depth
    r_mid = (r_out + r_inner) / 2.0
    span = r_out - r_inner + 0.6
    for z_e in teeth_ends:
        for k in range(n_teeth):
            tool = Pos(r_mid, 0, z_e) * Rot(45, 0, 0) * Box(span, w, w)
            cuts.append(Rot(0, 0, 360.0 * k / n_teeth) * tool)
    if side_teeth:
        w2 = 0.26
        zc, zspan = side_z
        for k in range(side_teeth):
            tool = Pos(r_out, 0, zc) * Rot(0, 0, 45) * Box(w2, w2, zspan)
            cuts.append(Rot(0, 0, 360.0 * (k + 0.5) / side_teeth) * tool)
    if groove is not None:
        zc, gw, neck_r = groove
        ring = Pos(0, 0, zc - gw / 2.0) * extrude(
            Circle(r_out + 0.3) - Circle(neck_r), amount=gw)
        cuts.append(ring)
    return body - cuts


def _stem_axis(part, x0=0.0):
    """Local +Z axis -> movement +X at the stem height."""
    return Pos(_STEM_X0 + x0, 0, STEM_Z) * Rot(0, 90, 0) * part


# ---------------------------------------------------------------------------
# 1. Stem + winding pinion + sliding pinion (castle wheel)
# ---------------------------------------------------------------------------

def _stem_parts():
    parts = []

    # stem: coaxial segments along local Z (z=0 -> x=8.5 pilot tip)
    segs, cuts, z = [], [], 0.0
    for kind, length, size in _STEM_SEGS:
        if kind == "square":
            segs.append(Pos(0, 0, z + length / 2.0) * Box(size, size, length))
        else:
            segs.append(_cyl(size, length, z))
        if kind == "thread":
            # thread hint: three shallow annular grooves
            for i in range(3):
                gz = z + 0.14 + i * 0.18
                cuts.append(Pos(0, 0, gz) * extrude(
                    Circle(size + 0.03) - Circle(size - 0.08), amount=0.08))
        z += length
    stem = segs[0] + segs[1:]
    stem = stem - cuts
    stem, _ = F.safe_chamfer(
        stem, _edges_at_z(stem, z) + _edges_at_z(stem, 0.0), 0.08)
    parts.append(_finish(_stem_axis(stem), "stem", S.STEEL_BRIGHT))

    # winding pinion (outboard): crown teeth face inboard (-X = local z=0),
    # bevel-tooth band + rim chamfer outboard toward the crown wheel above
    wp_len = _WINDING_X[1] - _WINDING_X[0]
    wp = _crown_pinion(
        _WINDING_R, wp_len, r_inner=_SEAT_R, tooth_depth=0.32,
        teeth_ends=(0.0,), bore_round=_SEAT_R + 0.015,
        side_teeth=16, side_z=(wp_len - 0.18, 0.44))
    wp = _stem_axis(wp, _WINDING_X[0] - _STEM_X0)
    parts.append(_finish(wp, "winding_pinion", S.STEEL_DARK))

    # sliding pinion (castle wheel, inboard): double crown teeth + yoke groove
    cw_len = _CASTLE_X[1] - _CASTLE_X[0]
    gx, gw, neck_r = _CASTLE_GROOVE
    cw = _crown_pinion(
        _CASTLE_R, cw_len, r_inner=_SQ_SIDE / 2.0, tooth_depth=0.30,
        teeth_ends=(0.0, cw_len), bore_square=_SQ_SIDE + 0.03,
        groove=(gx - _CASTLE_X[0], gw, neck_r))
    cw = _stem_axis(cw, _CASTLE_X[0] - _STEM_X0)
    parts.append(_finish(cw, "sliding_pinion", S.STEEL_DARK))
    return parts


# ---------------------------------------------------------------------------
# 2. Levers: setting lever, yoke, setting lever spring + screws
# ---------------------------------------------------------------------------

def _lever_plate(prof, z_band, bevel):
    """Extrude a plan profile through `z_band` and bevel the DIAL-side
    (bottom, -Z) perimeter — that's the face the dial-side viewer sees."""
    z0, z1 = z_band
    body = Pos(0, 0, z0) * extrude(prof, amount=z1 - z0)
    body, _ = F.safe_chamfer(body, _edges_at_z(body, z0), bevel)
    return body


def _lever_parts():
    parts = []
    z0, z1 = LEVER_Z

    # setting lever: pivot boss near 4 o'clock, pin arm into the stem
    # groove, detent arm toward the spring blade
    lever_prof = _chain((
        ((11.5, -2.5, 0.80), (12.05, -1.3, 0.60),
         (12.3, -0.05, 0.42)),               # pin arm under the stem groove
        ((11.5, -2.5, 0.80), (10.4, -3.0, 0.58),
         (9.4, -3.35, 0.52)),                # detent arm
    ))
    lever = _lever_plate(lever_prof, LEVER_Z, S.ANGLAGE_WIDTH_SMALL)
    # pin rising into the stem's setting groove (neck bottom ~ -0.89)
    pin = Pos(_GROOVE_X, 0, 0) * _cyl(0.23, 0.96, -1.80)
    boss = Pos(11.5, -2.5, 0) * _cyl(0.42, 0.10, z1)
    lever = lever + [pin, boss]
    # two detent notches (winding / setting positions) for the spring blade
    notches = [Pos(9.57, -3.82, 0) * _cyl(0.15, 1.0, -2.1),
               Pos(9.23, -3.82, 0) * _cyl(0.15, 1.0, -2.1)]
    lever = lever - notches
    parts.append(_finish(lever, "setting_lever", S.STEEL_LEVER))

    # yoke (return bar): slim lever from its pivot to a fork riding the
    # castle-wheel groove; raised finger pads straddle the groove neck
    fork_c = (_CASTLE_GROOVE[0], 0.0)
    ring = Pos(*fork_c) * (Circle(1.05) - Circle(0.72))
    opening = Pos(*fork_c) * Polygon((0, 0), (2.0, -0.9), (2.0, 0.9),
                                     align=None)
    yoke_prof = _chain(
        (((8.7, 2.7, 0.55), (9.5, 1.8, 0.45), (10.0, 1.15, 0.40)),),
        extra=(ring - opening,))
    yoke = _lever_plate(yoke_prof, LEVER_Z, 0.10)
    pads = [Pos(fork_c[0], sy, 0) * _cyl_box_pad() for sy in (0.80, -0.80)]
    yoke = yoke + [Pos(8.7, 2.7, 0) * _cyl(0.30, 0.10, z1)] + pads
    parts.append(_finish(yoke, "yoke", S.STEEL_LEVER))

    # setting lever spring: flat blade plate, two screws, spring finger
    # with a riser tip seated in the setting-lever detent notch
    sz0, sz1 = SPRING_Z
    spring_prof = _chain((
        ((8.8, -4.3, 0.62), (10.1, -4.1, 0.72), (11.5, -3.6, 0.66),
         (12.4, -2.9, 0.55)),                # spring plate
        ((10.0, -4.15, 0.35), (9.4, -3.82, 0.16)),  # spring blade
    ))
    # slit separating the blade from the plate body (reads as a spring);
    # kept strictly interior to the plate so the profile stays one face
    slit = Polygon((10.35, -4.39), (9.62, -4.09), (9.62, -4.22),
                   (10.35, -4.52), align=None)
    spring_prof = spring_prof - slit
    # screw holes
    spring_prof = spring_prof - (Pos(8.8, -4.3) * Circle(0.38)
                                 + Pos(12.4, -2.9) * Circle(0.38))
    spring = _lever_plate(spring_prof, SPRING_Z, 0.08)
    riser = Pos(9.4, -3.82, 0) * _cyl(0.13, 0.38, sz1 - 0.02)
    spring = spring + riser
    parts.append(_finish(spring, "setting_lever_spring", S.STEEL_DARK))

    for i, (sx, sy) in enumerate(((8.8, -4.3), (12.4, -2.9)), start=1):
        s = _dial_screw(sx, sy, sz0, hh=0.32, shank=1.1)
        parts.append(_finish(s, f"screw:setting_lever_spring:{i}", S.BLUED))
    return parts


def _cyl_box_pad():
    """Yoke fork finger pad: rises from the yoke plane into the castle
    groove (top z -0.95; groove neck half-width there ~0.55, pad inner
    face at |y| 0.59)."""
    return Pos(0, 0, (-1.65 - 0.95) / 2.0) * Box(0.30, 0.42, 0.70)


# ---------------------------------------------------------------------------
# 3. Motion works: cannon pinion, minute wheel + pinion, hour wheel
# ---------------------------------------------------------------------------

def _motion_parts():
    parts = []
    mw = MINUTE_WHEEL_POS
    ctr = (0.0, 0.0)

    # cannon pinion at the center: 12 leaves, pipe down through the dial.
    # -3 deg seats the mesh at the measured minimum flank contact
    # (F.pinion leaves sit half a leaf-width off-axis)
    rot_c = _ang(ctr, mw) + 180.0 / S.CANNON_PINION_LEAVES - 3.0
    leaves = Pos(0, 0, _CANNON_LEAF_Z[0]) * Rot(0, 0, rot_c) * F.pinion(
        S.CANNON_PINION_LEAVES, CANNON_TIP_D,
        _CANNON_LEAF_Z[1] - _CANNON_LEAF_Z[0])
    pipe = _cyl(0.50, _CANNON_LEAF_Z[0] - _CANNON_PIPE_END, _CANNON_PIPE_END)
    stub = _cyl(0.42, 0.14, _CANNON_LEAF_Z[1] - 0.02)
    cannon = (leaves + [pipe, stub]) - _cyl(0.25, 2.2, _CANNON_PIPE_END - 0.1)
    parts.append(_finish(cannon, "cannon_pinion", S.STEEL_DARK))

    # minute wheel: 36 t solid gilt web (motion-works wheels are uncrossed)
    rot_mw = _ang(mw, ctr)
    wheel = F.train_wheel(S.MINUTE_WHEEL_TEETH, MINUTE_TIP_D,
                          web_thickness=0.20, spoke_count=0,
                          tooth_depth_frac=MINUTE_TOOTH_FRAC)
    wheel = wheel - Cylinder(0.30, 1.0)
    wheel = Pos(mw[0], mw[1], _MINUTE_WEB_Z) * Rot(0, 0, rot_mw) * wheel
    parts.append(_finish(wheel, "minute_wheel", S.GILT))

    # minute pinion (riveted below the wheel): 10 leaves + arbor
    rot_mp = _ang(mw, ctr) + 180.0 / S.MINUTE_WHEEL_PINION
    mp = Pos(mw[0], mw[1], _MINUTE_PINION_Z[0]) * Rot(0, 0, rot_mp) * F.pinion(
        S.MINUTE_WHEEL_PINION, MINUTE_PINION_TIP_D,
        _MINUTE_PINION_Z[1] - _MINUTE_PINION_Z[0])
    arbor = Pos(mw[0], mw[1], 0) * _cyl(0.28, 0.83, -2.48)
    parts.append(_finish(mp + arbor, "minute_wheel_pinion", S.STEEL_DARK))

    # hour wheel: 40 t gilt, pipe riding OVER the cannon pipe
    rot_h = _ang(ctr, mw)
    hw = F.train_wheel(S.HOUR_WHEEL_TEETH, HOUR_TIP_D, web_thickness=0.20,
                       spoke_count=0, tooth_depth_frac=HOUR_TOOTH_FRAC)
    pipe = Pos(0, 0, (_HOUR_PIPE_END - _HOUR_WEB_Z) / 2.0 + 0.05) * Cylinder(
        0.85, _HOUR_WEB_Z - _HOUR_PIPE_END + 0.10)
    hw = (hw + pipe) - Cylinder(0.56, 3.0)
    hw = Pos(0, 0, _HOUR_WEB_Z) * Rot(0, 0, rot_h) * hw
    parts.append(_finish(hw, "hour_wheel", S.GILT))
    return parts


def build_keyless():
    """All keyless + motion works parts, labeled/colored, movement frame."""
    parts = []
    parts += _stem_parts()
    parts += _lever_parts()
    parts += _motion_parts()
    return parts
