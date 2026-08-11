"""juno humanoid: dexterous 5-digit hand (4 fingers + opposed thumb).

Local frame: origin = wrist-pitch joint center, fingers extend -Z, thumb on
the +X (forward) edge. RIGHT hand palm normal = +Y; LEFT is the XZ-mirror.

Locked interfaces:
- Clevis cheek plates normal to Y at y in [22,30] / [-30,-22], z 0..-44,
  x -20..+24, aluminum boss disc dia 34 coaxial with Y on each outer face.
- Keep |y| < 21 clear for r < 26 around the Y axis near the origin
  (wrist-pitch actuator dia 48 x len 40 lives there; owned by the forearm).
"""

from __future__ import annotations

import sys
from pathlib import Path



import math  # noqa: F401  (kept for tuning)

from build123d import (
    Axis,
    Box,
    Cone,
    Cylinder,
    Plane,
    Polyline,
    Pos,
    Rot,
    Sphere,
    chamfer,
    extrude,
    fillet,
    make_face,
    mirror,
)

from .juno_lib import (
    ACCENT_COLOR,
    ALU_COLOR,
    RUBBER_COLOR,
    SHELL_COLOR,
    STRUCT_COLOR,
    VISOR_COLOR,
    part_compound,
    styled,
)

# ---------------------------------------------------------------- helpers


def _safe_chamfer(part, edges, length, length2=None):
    try:
        edges = list(edges)
        if not edges:
            return part
        if length2 is not None:
            return chamfer(edges, length, length2)
        return chamfer(edges, length)
    except Exception:
        return part


def _safe_fillet(part, edges, radius):
    try:
        edges = list(edges)
        if not edges:
            return part
        return fillet(edges, radius)
    except Exception:
        return part


def _xcyl(r, h):
    """Cylinder along +X centered at origin."""
    return Rot(0, 90, 0) * Cylinder(radius=r, height=h)


def _ycyl(r, h):
    """Cylinder along +Y centered at origin."""
    return Rot(-90, 0, 0) * Cylinder(radius=r, height=h)


# ---------------------------------------------------------------- wrist clevis

CHEEK_X0, CHEEK_X1 = -20.0, 24.0
CHEEK_Z0, CHEEK_Z1 = 0.0, -44.0
LOBE_R = 24.0


def _wrist_clevis():
    """Twin cheek plates + pivot lobes + lower cross bridge (one solid)."""
    cheeks = []
    for ys in (1.0, -1.0):
        yc = ys * 26.0
        plate = Pos(
            (CHEEK_X0 + CHEEK_X1) / 2.0, yc, (CHEEK_Z0 + CHEEK_Z1) / 2.0
        ) * Box(CHEEK_X1 - CHEEK_X0, 8.0, CHEEK_Z0 - CHEEK_Z1)
        lobe = Pos(0, yc, 0) * _ycyl(LOBE_R, 8.0)
        cheek = plate + lobe
        # bevel the face outlines (machined plate look)
        face_edges = []
        for f in cheek.faces().filter_by(Axis.Y):
            face_edges.extend(f.edges())
        cheek = _safe_chamfer(cheek, face_edges, 1.2)
        cheeks.append(cheek)

    bridge = Pos(2.0, 0.0, -37.0) * Box(44.0, 44.0, 14.0)
    bridge = _safe_chamfer(bridge, bridge.edges().filter_by(Axis.X), 2.0)
    bridge = _safe_chamfer(bridge, bridge.edges().filter_by(Axis.Y), 2.0)

    clevis = cheeks[0] + cheeks[1] + bridge

    # shallow turned ring groove on each outer face, around the boss disc
    for ys in (1.0, -1.0):
        try:
            ring = (Pos(0, ys * 30.0, 0) * _ycyl(21.0, 1.6)) - (
                Pos(0, ys * 30.0, 0) * _ycyl(19.0, 3.0)
            )
            clevis -= ring
        except Exception:
            pass
    return styled(clevis, "wrist_clevis", STRUCT_COLOR)


def _cheek_bolts():
    out = []
    i = 0
    for ys in (1.0, -1.0):
        for bx in (-13.0, 17.0):
            bolt = Pos(bx, ys * 30.7, -37.0) * _ycyl(2.2, 1.4)
            bolt = _safe_chamfer(bolt, bolt.edges(), 0.5)
            out.append(styled(bolt, f"cheek_bolt_{i}", ALU_COLOR))
            i += 1
    return out


def _boss_discs():
    out = []
    for ys, tag in ((1.0, "l"), (-1.0, "r")):
        boss = Pos(0, ys * 31.6, 0) * _ycyl(17.0, 3.2)
        boss = _safe_chamfer(boss, boss.edges(), 0.8)
        out.append(styled(boss, f"wrist_boss_{tag}", ALU_COLOR))
    return out


# ---------------------------------------------------------------- palm

KNUCKLE_Z = -112.0
KNUCKLE_Y = -2.0
KNUCKLE_XS = (-27.0, -9.0, 9.0, 27.0)

# thumb CMC frame (root on the +X palm edge)
THUMB_ROOT = (39.5, 2.0, -60.0)
T_CMC = Pos(*THUMB_ROOT) * Rot(0, -28, 0) * Rot(0, 0, 38)  # hinge axis = local X
T_SEG1 = T_CMC * Rot(12, 0, 0)  # CMC curl
T_SEG2 = T_SEG1 * Pos(0, 0, -32.0) * Rot(30, 0, 0)  # IP curl


def _palm_outline_face(pts, y):
    pts3 = [(x, y, z) for x, z in pts]
    wire = Polyline(*pts3, close=True)
    return make_face(wire)


def _palm_core():
    pts = [
        (-20.0, -44.0),
        (24.0, -44.0),
        (44.0, -58.0),
        (44.0, -96.0),
        (36.0, -108.0),
        (-36.0, -108.0),
    ]
    core = extrude(_palm_outline_face(pts, -16.0), amount=34.0, dir=(0, 1, 0))
    core = _safe_fillet(core, core.edges().filter_by(Axis.Y), 4.0)

    # raked palm-side bottom edge over the knuckle line
    rake = [
        e
        for e in core.edges()
        if e.center().Y > 16.5 and e.center().Z < -107.0
    ]
    core = _safe_chamfer(core, rake, 5.0)

    # knuckle scallops (clearance arches over the proximal barrels)
    for kx in KNUCKLE_XS:
        core -= Pos(kx, KNUCKLE_Y, KNUCKLE_Z) * _xcyl(8.0, 15.5)

    # thumb CMC pocket + diagonal thumb relief groove
    core -= T_CMC * _xcyl(9.5, 30.0)
    core -= T_SEG1 * Pos(0, 0, -14.0) * Rot(0, 90, 0) * Cylinder(
        radius=11.2, height=60.0
    )

    # palm sensor recess
    core -= Pos(2.0, 17.4, -80.0) * _ycyl(8.3, 3.2)

    return styled(core, "palm_core", STRUCT_COLOR)


def _dorsal_cover():
    pts = [
        (-18.0, -46.0),
        (22.0, -46.0),
        (42.0, -59.0),
        (42.0, -95.0),
        (34.5, -106.0),
        (-34.0, -106.0),
    ]
    cover = extrude(_palm_outline_face(pts, -20.0), amount=4.0, dir=(0, 1, 0))
    cover = _safe_fillet(cover, cover.edges().filter_by(Axis.Y), 4.0)
    try:
        outer = cover.faces().sort_by(Axis.Y)[0]
        cover = _safe_chamfer(cover, outer.edges(), 1.2)
    except Exception:
        pass
    # shallow panel-line grooves on the outer face
    for gz in (-64.0, -69.0):
        try:
            cover -= Pos(2.0, -20.0, gz) * Box(52.0, 1.2, 1.5)
        except Exception:
            pass
    return styled(cover, "dorsal_cover", SHELL_COLOR)


def _palm_sensor():
    ring_raw = Cylinder(radius=8.1, height=1.2) - Cylinder(radius=6.3, height=4.0)
    ring = Pos(2.0, 16.5, -80.0) * Rot(-90, 0, 0) * ring_raw
    lens = Pos(2.0, 16.7, -80.0) * _ycyl(6.1, 1.6)
    return [
        styled(ring, "palm_sensor_ring", ALU_COLOR),
        styled(lens, "palm_sensor_lens", VISOR_COLOR),
    ]


# ---------------------------------------------------------------- digits


def _link(length, width, r_a, r_b, shaft_w, shaft_d, slot_w, bore_r):
    """Phalanx link: barrel at z=0, shaft, forked barrel at z=-length."""
    barrel_a = _xcyl(r_a, width)
    shaft_h = length - 7.0
    shaft = Pos(0, 0, -(4.0 + shaft_h / 2.0)) * Box(shaft_w, shaft_d, shaft_h)
    barrel_b = Pos(0, 0, -length) * _xcyl(r_b, width)
    link = barrel_a + shaft + barrel_b
    link = _safe_chamfer(link, link.edges().filter_by(Axis.Z), 1.2)
    # fork slot for the next segment
    link -= Pos(0, 0, -(length + 0.5)) * Box(slot_w, 40.0, 15.0)
    # pin bores
    link -= _xcyl(bore_r, width + 8.0)
    link -= Pos(0, 0, -length) * _xcyl(bore_r, width + 8.0)
    return link


def _tip_segment(r_barrel, w_barrel, r_top, r_tip, tip_z, cone_top_z, pad_c, pad_r, bore_r):
    """Distal segment: hinge barrel + tapered body + rounded tip.

    Returns (body, pad) where pad is a rubber fingertip cap split off the
    body by a boolean intersection (face-to-face, no overlap), or None.
    """
    barrel = _xcyl(r_barrel, w_barrel)
    cone_h = cone_top_z - tip_z
    cone = Pos(0, 0, (cone_top_z + tip_z) / 2.0) * Cone(
        bottom_radius=r_tip, top_radius=r_top, height=cone_h
    )
    tip = Pos(0, 0, tip_z) * Sphere(r_tip)
    body = barrel + cone + tip
    body -= _xcyl(bore_r, w_barrel + 8.0)
    pad = None
    try:
        zone = Pos(*pad_c) * Sphere(pad_r)
        cap = body & zone
        if cap.volume > 1.0:
            body = body - zone
            pad = cap
    except Exception:
        pad = None
    return body, pad


def _pin(r, h):
    pin = _xcyl(r, h)
    return _safe_chamfer(pin, pin.edges(), 0.7)


def _finger(idx, kx, curl1=21.0, curl2=25.0):
    t1 = Pos(kx, KNUCKLE_Y, KNUCKLE_Z) * Rot(curl1, 0, 0)
    t2 = t1 * Pos(0, 0, -36.0) * Rot(curl2, 0, 0)

    prox = _link(
        length=36.0, width=15.0, r_a=7.5, r_b=7.0,
        shaft_w=13.0, shaft_d=13.5, slot_w=9.5, bore_r=3.9,
    )
    body, pad = _tip_segment(
        r_barrel=6.6, w_barrel=9.0, r_top=6.2, r_tip=4.6,
        tip_z=-25.0, cone_top_z=-4.0,
        pad_c=(0, 1.9, -24.5), pad_r=5.5, bore_r=3.9,
    )

    solids = [
        styled(t1 * prox, f"finger{idx}_proximal", STRUCT_COLOR),
        styled(t2 * body, f"finger{idx}_distal", STRUCT_COLOR),
        styled(Pos(kx, KNUCKLE_Y, KNUCKLE_Z) * _pin(3.7, 17.5),
               f"finger{idx}_pin_mcp", ALU_COLOR),
        styled(t1 * Pos(0, 0, -36.0) * _pin(3.7, 17.5),
               f"finger{idx}_pin_pip", ALU_COLOR),
    ]
    if pad is not None:
        solids.append(styled(t2 * pad, f"finger{idx}_tip_pad", ACCENT_COLOR))
    return solids


def _thumb():
    seg1 = _link(
        length=32.0, width=15.0, r_a=8.5, r_b=7.5,
        shaft_w=13.0, shaft_d=13.0, slot_w=9.7, bore_r=4.2,
    )
    body, pad = _tip_segment(
        r_barrel=6.7, w_barrel=9.2, r_top=6.2, r_tip=4.9,
        tip_z=-21.5, cone_top_z=-5.0,
        pad_c=(0, 1.8, -21.0), pad_r=5.7, bore_r=3.9,
    )
    solids = [
        styled(T_SEG1 * seg1, "thumb_proximal", STRUCT_COLOR),
        styled(T_SEG2 * body, "thumb_distal", STRUCT_COLOR),
        styled(T_CMC * _pin(4.0, 17.0), "thumb_pin_cmc", ALU_COLOR),
        styled(T_SEG1 * Pos(0, 0, -32.0) * _pin(3.7, 16.0),
               "thumb_pin_ip", ALU_COLOR),
    ]
    if pad is not None:
        solids.append(styled(T_SEG2 * pad, "thumb_tip_pad", ACCENT_COLOR))
    return solids


# ---------------------------------------------------------------- assembly


def _right_solids():
    solids = [_wrist_clevis()]
    solids += _boss_discs()
    solids += _cheek_bolts()
    solids.append(_palm_core())
    solids.append(_dorsal_cover())
    solids += _palm_sensor()
    for i, kx in enumerate(KNUCKLE_XS):
        solids += _finger(i, kx)
    solids += _thumb()
    return solids


def _fallback_solids():
    blk = Pos(4, 0, -100) * Box(80, 36, 200)
    return [styled(blk, "hand_fallback", STRUCT_COLOR)]


def build_hand(side: str):
    try:
        solids = _right_solids()
        if side == "left":
            mirrored = []
            for s in solids:
                lbl, col = s.label, s.color
                m = mirror(s, about=Plane.XZ)
                mirrored.append(styled(m, lbl, col))
            solids = mirrored
        for s in solids:
            s.label = f"{side}_{s.label}"
    except Exception:
        solids = _fallback_solids()
    return part_compound(f"hand_{side}", solids)


def gen_step():
    right = build_hand("right")
    left = build_hand("left")
    right.location = Pos(0, -125, 0)
    left.location = Pos(0, 125, 0)
    return part_compound("hand_demo", [right, left])
