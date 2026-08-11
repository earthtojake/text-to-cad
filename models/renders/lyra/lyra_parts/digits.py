"""lyra digit links: finger phalanges and the thumb column.

Local frames (see lib.py):
- Finger phalanges: origin at the proximal joint center, +Z distal along
  the segment, +Y palmar, flexion axis -X.
- Thumb segments: origin at the proximal joint center, +X distal along the
  column, +Z palmar pad direction, flexion axis -Y (the thumb_base yaw
  turret tang spins about +Z).

Each phalanx is a pearl composite shell TUBE over an exposed graphite
structural spine: graphite tang barrel -> center spine bar -> fork
crossbar -> clevis cheeks, one connected solid, with the spine visible at
both joint ends (the "visible precision joints" design language). The
soft-touch tactile strip rides the tube's palmar face.

Articulation-safety rules (hold for every joint at any angle in range):
- Full-width child geometry (the shell tube) starts beyond parent lobe
  radius + 0.4 from the joint axis; only the circular tang barrel and the
  narrow center spine (which never shares an x/y band with the parent
  cheeks, and stays clear of the pin bore radius) sit closer.
- Fork crossbars sit >= 9 mm proximal of their own joint axis, outside the
  +/-43 deg corner sweep of the child spine at full flexion.

Joint hardware ownership: the parent link owns clevis cheeks, aluminum rim
washers, and the pivot pin; the child owns the bored tang barrel.
"""

from __future__ import annotations

from build123d import Axis, Box, Cone, Pos, Rot, Sphere

from .chain import (
    SEGMENT_MM,
    THUMB_METACARPAL_LEN_MM,
    THUMB_PROXIMAL_LEN_MM,
    THUMB_BASE_LEN_MM,
)
from .lib import (
    ALU_COLOR,
    GRAPHITE_COLOR,
    PAD_COLOR,
    PEARL_COLOR,
    part_compound,
    pin,
    safe_chamfer,
    safe_fillet,
    styled,
    xcyl,
    ycyl,
    zcyl,
)

# Per-finger width scale (lengths come from chain.SEGMENT_MM).
FINGER_SCALE = {"index": 1.0, "middle": 1.03, "ring": 0.97, "pinky": 0.88}

# Knuckle hardware (mm at scale 1). Tang widths match the parent fork gap
# minus 0.6 clearance; bores give the parent-owned pin a 0.4 running fit.
PALM_LOBE_R = 8.0          # palm knuckle lobe radius (palm.py uses this too)
PROX_TANG_R, PROX_TANG_W, PROX_BORE_R = 7.2, 10.4, 3.0
PROX_FORK_GAP, PROX_CHEEK_T, PROX_LOBE_R = 9.6, 2.6, 6.5
PROX_PIN_R, PROX_RIM_R = 2.4, 4.4
MID_TANG_R, MID_TANG_W, MID_BORE_R = 6.4, 9.0, 2.8
MID_FORK_GAP, MID_CHEEK_T, MID_LOBE_R = 8.4, 2.4, 5.8
MID_PIN_R, MID_RIM_R = 2.1, 3.8
DIST_TANG_R, DIST_TANG_W, DIST_BORE_R = 5.6, 7.8, 2.5

MCP_PIN_R = 2.6            # palm-owned; phalanx bore must clear it
RIM_T = 1.2


def _bored_xbarrel(r, w, bore_r):
    return xcyl(r, w) - xcyl(bore_r, w + 4.0)


def _bored_ybarrel(r, w, bore_r):
    return ycyl(r, w) - ycyl(bore_r, w + 4.0)


def _finger_fork(z, gap, cheek_t, lobe_r, pin_r, rim_r, body_d):
    """Distal clevis of a finger phalanx: cheeks + lobes (one solid, bored),
    rim washers, and the pivot pin."""
    half = gap / 2.0
    fork = None
    for sx in (1.0, -1.0):
        xc = sx * (half + cheek_t / 2.0)
        plate = Pos(xc, 0.2, z - 6.0) * Box(cheek_t, body_d, 12.0)
        lobe = Pos(xc, 0, z) * xcyl(lobe_r, cheek_t)
        cheek = plate + lobe
        fork = cheek if fork is None else fork + cheek
    fork = safe_chamfer(
        fork, [e for e in fork.edges().filter_by(Axis.X)], 0.8
    )
    fork -= Pos(0, 0, z) * xcyl(pin_r + 0.4, gap + 2 * cheek_t + 8.0)
    rims = []
    for sx in (1.0, -1.0):
        xr = sx * (half + cheek_t + RIM_T / 2.0)
        rim = Pos(xr, 0, z) * (
            xcyl(rim_r, RIM_T) - xcyl(pin_r + 0.4, RIM_T + 2.0)
        )
        rims.append(rim)
    pin_len = gap + 2 * cheek_t + 2 * RIM_T + 1.2
    pivot = Pos(0, 0, z) * pin("x", pin_r, pin_len)
    return fork, rims, pivot


def _finger_phalanx(
    label_prefix,
    pin_name,
    s,
    length,
    tang_r,
    tang_w,
    bore_r,
    fork_gap,
    cheek_t,
    lobe_r,
    pin_r,
    rim_r,
    parent_lobe_r,
    body_w,
    body_d,
    y_shift,
):
    """Pearl shell tube over an exposed graphite spine, plus fork hardware."""
    tube_z0 = parent_lobe_r + 0.4
    tube_z1 = length - 13.2 * s
    bar_w = 6.5 * s
    chan_w = bar_w + 0.5

    # Graphite spine: tang barrel + center bar + fork crossbar + clevis.
    core = _bored_xbarrel(tang_r, tang_w, bore_r)
    bar = Pos(0, y_shift, (4.5 * s + length - 9.0 * s) / 2.0) * Box(
        bar_w, bar_w, length - 9.0 * s - 4.5 * s
    )
    core += bar
    crossbar = Pos(0, 0.2, length - 11.0 * s) * Box(
        fork_gap + 2 * cheek_t, bar_w, 4.0 * s
    )
    core += crossbar
    fork, rims, pivot = _finger_fork(
        length, fork_gap, cheek_t, lobe_r, pin_r, rim_r, body_d
    )
    core += fork

    # Pearl composite shell tube around the spine.
    tube = Pos(0, y_shift, (tube_z0 + tube_z1) / 2.0) * Box(
        body_w, body_d, tube_z1 - tube_z0
    )
    tube = safe_fillet(tube, tube.edges().filter_by(Axis.Z), min(2.6, body_w / 4.5))
    tube -= Pos(0, y_shift, (tube_z0 + tube_z1) / 2.0) * Box(
        chan_w, chan_w, tube_z1 - tube_z0 + 4.0
    )
    tube = safe_chamfer(
        tube, [e for e in tube.edges().filter_by(Axis.X)], 0.7
    )

    # Soft-touch tactile strip on the palmar tube face.
    pad = Pos(0, y_shift + body_d / 2.0 + 0.5, (tube_z0 + tube_z1) / 2.0) * Box(
        body_w - 4.0 * s, 1.6, max((tube_z1 - tube_z0) * 0.72, 2.5)
    )
    pad = safe_fillet(pad, pad.edges().filter_by(Axis.Y), min(1.8 * s, 2.0))

    solids = [
        styled(core, f"{label_prefix}_spine", GRAPHITE_COLOR),
        styled(tube, f"{label_prefix}_shell", PEARL_COLOR),
        styled(pad, f"{label_prefix}_pad", PAD_COLOR),
        styled(pivot, f"{pin_name}_pin", ALU_COLOR),
    ]
    for i, rim in enumerate(rims):
        solids.append(styled(rim, f"{pin_name}_rim_{i}", ALU_COLOR))
    return solids


def build_finger_proximal(finger: str):
    s = FINGER_SCALE[finger]
    solids = _finger_phalanx(
        f"{finger}_proximal", f"{finger}_pip", s, SEGMENT_MM[finger][0],
        PROX_TANG_R * s, PROX_TANG_W * s, PROX_BORE_R * s,
        PROX_FORK_GAP * s, PROX_CHEEK_T * s, PROX_LOBE_R * s,
        PROX_PIN_R * s, PROX_RIM_R * s, PALM_LOBE_R * s,
        13.4 * s, 11.4 * s, 0.7 * s,
    )
    return part_compound(f"{finger}_proximal", solids)


def build_finger_middle(finger: str):
    s = FINGER_SCALE[finger]
    solids = _finger_phalanx(
        f"{finger}_middle", f"{finger}_dip", s, SEGMENT_MM[finger][1],
        MID_TANG_R * s, MID_TANG_W * s, MID_BORE_R * s,
        MID_FORK_GAP * s, MID_CHEEK_T * s, MID_LOBE_R * s,
        MID_PIN_R * s, MID_RIM_R * s, PROX_LOBE_R * s,
        12.2 * s, 10.6 * s, 0.6 * s,
    )
    return part_compound(f"{finger}_middle", solids)


def build_finger_distal(finger: str):
    s = FINGER_SCALE[finger]
    length = SEGMENT_MM[finger][2]
    tip_r = 4.4 * s
    cone_z0 = MID_LOBE_R * s + 0.4
    tip_c = length - tip_r

    # Tang + connection collar (graphite, one solid). The collar is
    # center-band only, so it clears the parent pin bore and never shares
    # an x band with the parent cheeks.
    tang = _bored_xbarrel(DIST_TANG_R * s, DIST_TANG_W * s, DIST_BORE_R * s)
    collar_r = 4.0 * s
    collar_len = cone_z0 + 0.5 - 4.4
    tang += Pos(0, 0.4 * s, 4.4 + collar_len / 2.0) * zcyl(collar_r, collar_len)

    cone_h = tip_c - cone_z0
    body = Pos(0, 0.4 * s, cone_z0 + cone_h / 2.0) * Cone(
        bottom_radius=5.3 * s, top_radius=tip_r, height=cone_h
    )
    body += Pos(0, 0.4 * s, tip_c) * Sphere(tip_r)
    # Seat the pearl body on the collar shoulder (face contact, no overlap).
    body -= Pos(0, 0.4 * s, (cone_z0 + 0.5) / 2.0) * zcyl(collar_r + 0.05, cone_z0 + 0.5)

    # Soft-touch fingertip pad: split a palmar cap off the body with a
    # boolean sphere so the seam is face-to-face with no overlap.
    # Palmar-only soft cap: the zone center sits palmar of the tip sphere so
    # the apex and dorsal face stay pearl.
    pad = None
    try:
        zone = Pos(0, 3.6 * s, tip_c + 0.2) * Sphere(4.7 * s)
        cap = body & zone
        if cap.volume > 1.0:
            body = body - zone
            pad = cap
    except Exception:
        pad = None

    solids = [
        styled(tang, f"{finger}_distal_tang", GRAPHITE_COLOR),
        styled(body, f"{finger}_distal_body", PEARL_COLOR),
    ]
    if pad is not None:
        solids.append(styled(pad, f"{finger}_tip_pad", PAD_COLOR))
    return part_compound(f"{finger}_distal", solids)


# ----------------------------------------------------------------- thumb

T_PROX_LOBE_R = 7.0    # thumb_base flex-fork lobe radius (palm relief uses it)
TB_TANG_R, TB_TANG_H, TB_BORE_R = 8.8, 9.5, 3.3
TM_TANG_R, TM_TANG_W, TM_BORE_R = 6.8, 9.8, 2.9
TM_FORK_GAP, TM_CHEEK_T, TM_LOBE_R = 9.8, 2.5, 6.4
TM_PIN_R, TM_RIM_R = 2.3, 4.2
TP_TANG_R, TP_TANG_W, TP_BORE_R = 6.2, 9.2, 2.7
TP_FORK_GAP, TP_CHEEK_T, TP_LOBE_R = 8.6, 2.4, 5.6
TP_PIN_R, TP_RIM_R = 2.1, 3.7
TD_TANG_R, TD_TANG_W, TD_BORE_R = 5.2, 8.0, 2.5
THUMB_TIP_R = 4.8
THUMB_TIP_TOTAL_MM = 24.0  # matches chain.THUMB_TIP_LEN_MM


def _thumb_fork(x, gap, cheek_t, lobe_r, pin_r, rim_r, body_d):
    """Distal clevis of a thumb segment: cheeks normal to Y."""
    half = gap / 2.0
    fork = None
    for sy in (1.0, -1.0):
        yc = sy * (half + cheek_t / 2.0)
        plate = Pos(x - 6.0, yc, 0.2) * Box(12.0, cheek_t, body_d)
        lobe = Pos(x, yc, 0) * ycyl(lobe_r, cheek_t)
        cheek = plate + lobe
        fork = cheek if fork is None else fork + cheek
    fork = safe_chamfer(
        fork, [e for e in fork.edges().filter_by(Axis.Y)], 0.8
    )
    fork -= Pos(x, 0, 0) * ycyl(pin_r + 0.4, gap + 2 * cheek_t + 8.0)
    rims = []
    for sy in (1.0, -1.0):
        yr = sy * (half + cheek_t + RIM_T / 2.0)
        rim = Pos(x, yr, 0) * (
            ycyl(rim_r, RIM_T) - ycyl(pin_r + 0.4, RIM_T + 2.0)
        )
        rims.append(rim)
    pin_len = gap + 2 * cheek_t + 2 * RIM_T + 1.2
    pivot = Pos(x, 0, 0) * pin("y", pin_r, pin_len)
    return fork, rims, pivot


def _thumb_phalanx(
    label_prefix,
    pin_name,
    length,
    tang_r,
    tang_w,
    bore_r,
    fork_gap,
    cheek_t,
    lobe_r,
    pin_r,
    rim_r,
    parent_lobe_r,
    body_w,
    body_d,
    z_shift,
):
    """Thumb segment along +X: pearl tube over graphite spine, Y-axis forks."""
    tube_x0 = parent_lobe_r + 0.4
    tube_x1 = length - 13.2
    bar_w = 6.5
    chan_w = bar_w + 0.5

    core = _bored_ybarrel(tang_r, tang_w, bore_r)
    bar = Pos((4.5 + length - 9.0) / 2.0, 0, z_shift) * Box(
        length - 9.0 - 4.5, bar_w, bar_w
    )
    core += bar
    # Fork cheeks are stacked in Y, so the crossbar spans the Y width.
    crossbar = Pos(length - 11.0, 0, 0.2) * Box(4.0, fork_gap + 2 * cheek_t, bar_w)
    core += crossbar
    fork, rims, pivot = _thumb_fork(
        length, fork_gap, cheek_t, lobe_r, pin_r, rim_r, body_d
    )
    core += fork

    tube = Pos((tube_x0 + tube_x1) / 2.0, 0, z_shift) * Box(
        tube_x1 - tube_x0, body_w, body_d
    )
    tube = safe_fillet(tube, tube.edges().filter_by(Axis.X), min(2.6, body_w / 4.5))
    tube -= Pos((tube_x0 + tube_x1) / 2.0, 0, z_shift) * Box(
        tube_x1 - tube_x0 + 4.0, chan_w, chan_w
    )
    tube = safe_chamfer(
        tube, [e for e in tube.edges().filter_by(Axis.Y)], 0.7
    )

    pad = Pos((tube_x0 + tube_x1) / 2.0, 0, z_shift + body_d / 2.0 + 0.5) * Box(
        max((tube_x1 - tube_x0) * 0.72, 2.5), body_w - 4.0, 1.6
    )
    pad = safe_fillet(pad, pad.edges().filter_by(Axis.Z), 1.8)

    solids = [
        styled(core, f"{label_prefix}_spine", GRAPHITE_COLOR),
        styled(tube, f"{label_prefix}_shell", PEARL_COLOR),
        styled(pad, f"{label_prefix}_pad", PAD_COLOR),
        styled(pivot, f"{pin_name}_pin", ALU_COLOR),
    ]
    for i, rim in enumerate(rims):
        solids.append(styled(rim, f"{pin_name}_rim_{i}", ALU_COLOR))
    return solids


def build_thumb_base():
    """CMC turret tang (spins about +Z on the palm spindle) + flex clevis."""
    disc = zcyl(TB_TANG_R, TB_TANG_H) - zcyl(TB_BORE_R, TB_TANG_H + 4.0)
    disc = safe_chamfer(disc, disc.edges(), 0.8)
    neck = Pos(8.6, 0, 0) * Box(8.6, 12.6, 9.0)
    neck = safe_fillet(neck, neck.edges().filter_by(Axis.Z), 2.0)
    core = disc + neck
    fork, rims, pivot = _thumb_fork(
        THUMB_BASE_LEN_MM, TM_TANG_W + 0.6, 2.6, T_PROX_LOBE_R, 2.5, 4.5, 11.0
    )
    core += fork
    solids = [
        styled(core, "thumb_base_link", GRAPHITE_COLOR),
        styled(pivot, "thumb_cmc_flex_pin", ALU_COLOR),
    ]
    for i, rim in enumerate(rims):
        solids.append(styled(rim, f"thumb_cmc_flex_rim_{i}", ALU_COLOR))
    return part_compound("thumb_base", solids)


def build_thumb_metacarpal():
    solids = _thumb_phalanx(
        "thumb_metacarpal", "thumb_mp", THUMB_METACARPAL_LEN_MM,
        TM_TANG_R, TM_TANG_W, TM_BORE_R,
        TM_FORK_GAP, TM_CHEEK_T, TM_LOBE_R, TM_PIN_R, TM_RIM_R,
        T_PROX_LOBE_R, 12.6, 13.0, 0.5,
    )
    return part_compound("thumb_metacarpal", solids)


def build_thumb_proximal():
    solids = _thumb_phalanx(
        "thumb_proximal", "thumb_ip", THUMB_PROXIMAL_LEN_MM,
        TP_TANG_R, TP_TANG_W, TP_BORE_R,
        TP_FORK_GAP, TP_CHEEK_T, TP_LOBE_R, TP_PIN_R, TP_RIM_R,
        TM_LOBE_R, 11.6, 11.8, 0.4,
    )
    return part_compound("thumb_proximal", solids)


def build_thumb_distal():
    length = THUMB_TIP_TOTAL_MM
    tip_r = THUMB_TIP_R
    cone_x0 = TP_LOBE_R + 0.4
    tip_c = length - tip_r

    tang = _bored_ybarrel(TD_TANG_R, TD_TANG_W, TD_BORE_R)
    collar_r = 4.0
    collar_len = cone_x0 + 0.5 - 4.4
    tang += Pos(4.4 + collar_len / 2.0, 0, 0.4) * xcyl(collar_r, collar_len)

    cone_h = tip_c - cone_x0
    body = Pos(cone_x0 + cone_h / 2.0, 0, 0.4) * Rot(0, 90, 0) * Cone(
        bottom_radius=5.4, top_radius=tip_r, height=cone_h
    )
    body += Pos(tip_c, 0, 0.4) * Sphere(tip_r)
    body -= Pos((cone_x0 + 0.5) / 2.0, 0, 0.4) * xcyl(collar_r + 0.05, cone_x0 + 0.5)

    pad = None
    try:
        zone = Pos(tip_c + 0.2, 0, 3.4) * Sphere(5.0)
        cap = body & zone
        if cap.volume > 1.0:
            body = body - zone
            pad = cap
    except Exception:
        pad = None

    solids = [
        styled(tang, "thumb_distal_tang", GRAPHITE_COLOR),
        styled(body, "thumb_distal_body", PEARL_COLOR),
    ]
    if pad is not None:
        solids.append(styled(pad, "thumb_tip_pad", PAD_COLOR))
    return part_compound("thumb_distal", solids)
