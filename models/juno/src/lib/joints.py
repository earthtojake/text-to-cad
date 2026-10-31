"""Connective joint hardware for juno: yokes, carriers, collars.

These small machined parts link the sculpted body segments and carry the
exposed actuator cans for the joints they own. Frames follow the chain table
in juno.py; all builders return identity-location compounds.
"""

from __future__ import annotations

import build123d as bd

from .juno_lib import (
    ACCENT,
    ALU,
    STRUCT,
    actuator_solids,
    part_compound,
    styled,
)


def _s(side: str) -> float:
    return 1.0 if side == "left" else -1.0


def build_hip_bracket(side: str) -> bd.Compound:
    """Hip yaw can + C-yoke down to the hip-roll axis. Origin: hip-yaw center.

    Compact stack (proportion audit): yaw can dia 70 x 34, roll axis at
    z = -64, sized for the carrier's dia-56 roll housing (caps to |x| 30).
    """
    children = actuator_solids(
        "hip_yaw", 70, 34, center=(0, 0, -17), axis=(0, 0, 1), bolts=False
    )
    plates = []
    for sx in (1.0, -1.0):
        plates.append(bd.Pos(sx * 38, 0, -65) * bd.Box(12, 46, 54))
    bridge = bd.Pos(0, 0, -38) * bd.Box(88, 46, 8)
    yoke = plates[0].fuse(plates[1]).fuse(bridge)
    children.append(styled(yoke, "hip_yoke", STRUCT))
    for sx in (1.0, -1.0):
        boss = bd.Pos(sx * 47, 0, -64) * bd.Rot(0, 90, 0) * bd.Cylinder(radius=25, height=6)
        children.append(styled(boss, f"hip_roll_boss_{'f' if sx > 0 else 'b'}", ALU))
    return part_compound(f"hip_bracket_{side}", children)


def build_hip_carrier(side: str) -> bd.Compound:
    """Hip roll housing + medial plate to the hip-pitch axis. Origin: roll center.

    Compact stack: dia-56 roll housing, hip-pitch axis at z = -78 (clears the
    thigh's dia-92 pitch can: 78 > 28 + 46).
    """
    s = _s(side)
    children = []
    housing = bd.Rot(0, 90, 0) * bd.Cylinder(radius=28, height=48)
    plate = bd.Pos(0, -s * 44, -42) * bd.Box(76, 8, 110)
    bridge = bd.Pos(0, -s * 36, 0) * bd.Box(56, 16, 50)
    body = housing.fuse(bridge).fuse(plate)
    children.append(styled(body, "hip_carrier_body", STRUCT))
    for sx in (1.0, -1.0):
        cap = bd.Pos(sx * 27, 0, 0) * bd.Rot(0, 90, 0) * bd.Cylinder(radius=30, height=6)
        children.append(styled(cap, f"hip_roll_cap_{'f' if sx > 0 else 'b'}", ALU))
    boss = bd.Pos(0, -s * 38.5, -78) * bd.Rot(90, 0, 0) * bd.Cylinder(radius=32, height=3)
    children.append(styled(boss, "hip_pitch_boss", ALU))
    return part_compound(f"hip_carrier_{side}", children)


def build_ankle_link(side: str) -> bd.Compound:
    """Fused two-axis ankle block: pitch core at origin, roll core 30 below."""
    children = []
    pitch_core = bd.Rot(90, 0, 0) * bd.Cylinder(radius=27, height=36)
    roll_core = bd.Pos(0, 0, -30) * bd.Rot(0, 90, 0) * bd.Cylinder(radius=22, height=28)
    neck = bd.Pos(0, 0, -15) * bd.Box(30, 30, 30)
    body = pitch_core.fuse(roll_core).fuse(neck)
    children.append(styled(body, "ankle_body", STRUCT))
    for sy in (1.0, -1.0):
        cap = bd.Pos(0, sy * 20.5, 0) * bd.Rot(90, 0, 0) * bd.Cylinder(radius=24, height=5)
        children.append(styled(cap, f"ankle_pitch_cap_{'l' if sy > 0 else 'r'}", ALU))
    for sx in (1.0, -1.0):
        cap = bd.Pos(sx * 16, 0, -30) * bd.Rot(0, 90, 0) * bd.Cylinder(radius=19, height=4)
        children.append(styled(cap, f"ankle_roll_cap_{'f' if sx > 0 else 'b'}", ALU))
    return part_compound(f"ankle_link_{side}", children)


def build_shoulder_pod(side: str) -> bd.Compound:
    """Shoulder-pitch can + outboard drum + roll clevis. Origin: pitch center.

    The outboard module is a chamfered cylindrical drum capping the pitch can
    (reads as the shoulder actuator housing, per style review), with a blade
    dropping to the shoulder-roll clevis.
    """
    s = _s(side)
    children = actuator_solids(
        "shoulder_pitch", 72, 58, center=(0, s * 14, 0), axis=(0, 1, 0)
    )
    drum = bd.Pos(0, s * 50, 0) * bd.Rot(90, 0, 0) * bd.Cylinder(radius=40, height=14)
    try:
        drum = bd.chamfer(drum.edges(), 3.0)
    except Exception:
        pass
    blade = bd.Pos(0, s * 50, -42) * bd.Box(58, 14, 90)
    clevis_f = bd.Pos(35, s * 34, -72) * bd.Box(10, 48, 56)
    clevis_b = bd.Pos(-35, s * 34, -72) * bd.Box(10, 48, 56)
    body = drum.fuse(blade).fuse(clevis_f).fuse(clevis_b)
    children.append(styled(body, "pod_body", STRUCT))
    face = bd.Pos(0, s * 58.5, 0) * bd.Rot(90, 0, 0) * bd.Cylinder(radius=30, height=3)
    children.append(styled(face, "pod_face_ring", ALU))
    hub = bd.Pos(0, s * 61, 0) * bd.Rot(90, 0, 0) * bd.Cylinder(radius=12, height=2)
    children.append(styled(hub, "pod_face_hub", ACCENT))
    for sx in (1.0, -1.0):
        boss = (
            bd.Pos(sx * 43, s * 34, -72) * bd.Rot(0, 90, 0) * bd.Cylinder(radius=25, height=6)
        )
        children.append(styled(boss, f"roll_boss_{'f' if sx > 0 else 'b'}", ALU))
    return part_compound(f"shoulder_pod_{side}", children)


def build_yaw_housing(side: str) -> bd.Compound:
    """Shoulder-roll can + saddle to the upper-arm yaw ring. Origin: roll center."""
    children = []
    parts = actuator_solids("shoulder_roll", 70, 56, center=(0, 0, 0), axis=(1, 0, 0))
    core = parts[0]
    saddle = bd.Pos(0, 0, -14) * bd.Cylinder(radius=26, height=16)
    core = styled(core.fuse(saddle), "shoulder_roll_can", STRUCT)
    children.append(core)
    children.extend(parts[1:])
    ring = bd.Pos(0, 0, -22) * bd.Cylinder(radius=28, height=4)
    children.append(styled(ring, "yaw_ring", ALU))
    return part_compound(f"yaw_housing_{side}", children)


def build_wrist_carrier(side: str) -> bd.Compound:
    """Wrist-roll disc + wrist-pitch can block. Origin: roll center."""
    children = []
    disc = bd.Pos(0, 0, -2) * bd.Cylinder(radius=22, height=4)
    children.append(styled(disc, "wrist_roll_disc", ALU))
    parts = actuator_solids(
        "wrist_pitch", 48, 40, center=(0, 0, -28), axis=(0, 1, 0), bolts=False
    )
    core = parts[0]
    block = bd.Pos(0, 0, -10) * bd.Box(34, 34, 14)
    core = styled(core.fuse(block), "wrist_pitch_can", STRUCT)
    children.append(core)
    children.extend(parts[1:])
    return part_compound(f"wrist_carrier_{side}", children)


def build_neck_collar() -> bd.Compound:
    """Neck yaw can + pitch clevis. Origin: neck-yaw joint center."""
    children = actuator_solids(
        "neck_yaw", 44, 30, center=(0, 0, 15), axis=(0, 0, 1), bolts=False
    )
    for sy in (1.0, -1.0):
        plate = bd.Pos(0, sy * 19, 44) * bd.Box(36, 6, 36)
        children.append(styled(plate, f"neck_clevis_{'l' if sy > 0 else 'r'}", STRUCT))
        boss = bd.Pos(0, sy * 23, 46) * bd.Rot(90, 0, 0) * bd.Cylinder(radius=14, height=3)
        children.append(styled(boss, f"neck_boss_{'l' if sy > 0 else 'r'}", ALU))
    can = actuator_solids(
        "neck_pitch", 40, 28, center=(0, 0, 46), axis=(0, 1, 0), bolts=False
    )
    children.extend(can)
    return part_compound("neck_collar", children)
