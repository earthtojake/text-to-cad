"""The tendon hand's phalanges and fingertips, and the neutral anatomy study.

`anatomy_layout` is the hand's skeleton: every phalanx and every joint's two drive
pulleys at the neutral pose, with the finger joints authored as build123d joints
(below). The other models are phalanx and fingertip reviews. Each
model was its own script in `models/tendon_hand/src/`, and no model calls another:
`phalanx_continuous_representative_r5` read the supports model's STEP, and here both
place `continuous_supports()`, a `@memo` stage (about 20 s of kernel work), clipped against
`lib/phalanx_r5_host.py`'s `warm_host()`.
"""

import copy

from cadgen import memo, model
from cadgen.ap242 import gear_pair, mechanism_state

import build123d as bd

from lib.assembly import matrix_location
from lib.fingernail import fingernail_bodies
from lib.fingertip_bridge_repair import bridge_bodies
from lib.finish import finish
from lib.fingertip_pad import fingertip_pad_bodies, make_fingertip_pad
from lib.fixed_guide_mounts_continuous_r5 import make_fixed_outlet_pair as make_continuous_outlet_pair
from lib.guide_mounts_continuous_r5 import make_phalanx_comb as make_continuous_comb
from lib.layout import FINGERS, JOINT_BY_NAME, JOINTS, THUMB_CMC, THUMB_LENGTHS, finger_fan_matrix
from lib.phalanx import make_phalanx
from lib.phalanx_continuous_r5 import make_phalanx as make_continuous_phalanx
from lib.phalanx_r5_host import warm_host
from lib.pulley import make_pulley

ROLES = ("proximal", "middle", "distal")
THUMB_ROLES = ("metacarpal", "proximal", "distal")
THUMB_WIDTHS = (19., 16., 13.)


def _leaves(node):
    return [leaf for child in node.children for leaf in _leaves(child)] if node.children else [node]


def _middle_place():
    """The middle finger's base in the assembled neutral fan."""
    f = FINGERS[1]
    return matrix_location(finger_fan_matrix(f)) * bd.Pos(f.x, f.base_y, 0)


@memo
def continuous_supports():
    """The guide combs and fixed outlets matched to the continuous rail, clipped
    against its STEP reconstruction (`lib/phalanx_r5_host.py`)."""
    # Avoid OCCT same-domain unification runaway; all strict checks remain required.
    with bd.SkipClean():
        parts = make_continuous_comb(45, 18, 12.25, [-4.2, -3, 3, 4.2], "middle_mcp_outlet_comb")
        parts += make_continuous_comb(45, 18, 32.75, [-4.2, 4.2], "middle_pip_inlet_comb")
        parts += make_continuous_outlet_pair(45, 18, 4.5, "middle_pip_drive_guide")
        place = _middle_place()
        supports = bd.Compound(label="continuous_rail_matched_guide_supports", children=[place * s for s in parts])
    return supports


def _hinge(parent, child, name):
    """The joint `name` of lib.layout: a revolute joint on `parent` about its axis, its
    travel the joint's limits, and the child's rigid joint of the same label where the
    two parts stand, so the label pairs them as built (value 0, the neutral pose)."""
    joint = JOINT_BY_NAME[name]
    bd.RevoluteJoint(name, parent, axis=bd.Axis(joint.origin, joint.axis), angular_range=joint.limits)
    bd.RigidJoint(name, child, parent.joints[name].location)


def _fasten(link, part):
    """`part` rides `link`: two rigid joints of one label, where the part stands."""
    bd.RigidJoint(part.label, link, part.location)
    bd.RigidJoint(part.label, part, part.location)


@model
def anatomy_layout():
    """Neutral anatomy integration study. This is not the complete hand assembly.

    The finger joints are build123d joints at lib.layout's datums, connected at the
    neutral pose (every value 0): MCP flexion, PIP and DIP per finger, and the thumb's
    CMC flexion, MCP abduction, MCP flexion and IP. A joint's drive pulleys ride its
    child. Nothing here is the palm, so the MCP and thumb-CMC abduction carriers --
    each joint's two abduction pulleys -- stand as the ground, and those abductions are
    not modelled. Each finger's curl is one control driving its three flexions, and
    the thumb's its MCP flexion and IP."""
    bones, pulleys = {}, {}
    children = []
    for finger in FINGERS:
        y = finger.base_y
        for index, (length, width) in enumerate(zip(finger.lengths, finger.widths)):
            role = ROLES[index]
            part = make_phalanx(length, width, distal=index == 2, label=f"{finger.name}_{role}_frame")
            bone = bd.Pos(finger.x, y, 0) * part
            bones[f"{finger.name}_{role}"] = bone
            children.append(bone)
            y += length
    station = 0.
    for index, (length, width) in enumerate(zip(THUMB_LENGTHS, THUMB_WIDTHS)):
        role = THUMB_ROLES[index]
        part = make_phalanx(length, width, distal=index == 2, label=f"thumb_{role}_frame")
        bone = bd.Pos(*THUMB_CMC) * bd.Rot(0, 0, 45) * bd.Pos(0, station, 0) * part
        bones[f"thumb_{role}"] = bone
        children.append(bone)
        station += length
    for joint in JOINTS:
        if joint.system in ("wrist", "palm"):
            continue
        yaw = "abduction" in joint.name
        spacing = (9.5 if "cmc" in joint.name else 8.) if yaw else .9
        orient = bd.Plane(origin=joint.origin, z_dir=joint.axis).location
        for sign, side in ((1, "positive"), (-1, "negative")):
            pulley = make_pulley(joint.drive_radius, label=f"{joint.name}_{side}_drive_pulley")
            placed = orient * bd.Pos(0, 0, sign * spacing) * pulley
            pulleys[joint.name, side] = placed
            children.append(placed)

    for finger in FINGERS:
        n = finger.name
        carrier = pulleys[f"{n}_mcp_abduction", "positive"]
        _hinge(carrier, bones[f"{n}_proximal"], f"{n}_mcp_flexion")
        _hinge(bones[f"{n}_proximal"], bones[f"{n}_middle"], f"{n}_pip")
        _hinge(bones[f"{n}_middle"], bones[f"{n}_distal"], f"{n}_dip")
        for joint, link in (("mcp_flexion", "proximal"), ("pip", "middle"), ("dip", "distal")):
            for side in ("positive", "negative"):
                _fasten(bones[f"{n}_{link}"], pulleys[f"{n}_{joint}", side])
    cmc = pulleys["thumb_cmc_abduction", "positive"]
    mcp = pulleys["thumb_mcp_abduction", "positive"]
    _hinge(cmc, bones["thumb_metacarpal"], "thumb_cmc_flexion")
    _hinge(bones["thumb_metacarpal"], mcp, "thumb_mcp_abduction")
    _hinge(mcp, bones["thumb_proximal"], "thumb_mcp_flexion")
    _hinge(bones["thumb_proximal"], bones["thumb_distal"], "thumb_ip")
    _fasten(mcp, pulleys["thumb_mcp_abduction", "negative"])
    for joint, link in (("cmc_flexion", "metacarpal"), ("mcp_flexion", "proximal"), ("ip", "distal")):
        for side in ("positive", "negative"):
            _fasten(bones[f"thumb_{link}"], pulleys[f"thumb_{joint}", side])

    hand = bd.Compound(label="neutral_anatomy_integration_study", children=children)
    curls = []
    for finger in FINGERS:
        flexions = (f"{finger.name}_mcp_flexion", f"{finger.name}_pip", f"{finger.name}_dip")
        gear_pair(hand, f"{finger.name}_curl", **{name: JOINT_BY_NAME[name].limits[1] for name in flexions})
        curls.append(f"{finger.name}_curl")
    gear_pair(hand, "thumb_curl", **{name: JOINT_BY_NAME[name].limits[1] for name in ("thumb_mcp_flexion", "thumb_ip")})
    mechanism_state(hand, "fist", thumb_curl=1, **{curl: 1 for curl in curls})
    mechanism_state(hand, "point", thumb_curl=1, **{curl: 1 for curl in curls if curl != "index_curl"})
    return hand


@model
def phalanx_review():
    """Three actual middle-finger phalanges, laid out with joint clearance."""
    return bd.Compound(label="skeletal_phalanx_family", children=[
        make_phalanx(45, 18, label="middle_proximal_frame"),
        bd.Pos(25, 0, 0) * make_phalanx(28, 15, label="middle_intermediate_frame"),
        bd.Pos(47, 0, 0) * make_phalanx(17, 12, distal=True, label="middle_distal_frame"),
    ])


@model
def phalanx_variants_review():
    """Every actual hand phalanx, in five rows from index through thumb."""
    children = []
    variants = [(f.name, f.lengths, f.widths) for f in FINGERS]
    variants.append(("thumb", (36., 27., 21.), (19., 16., 13.)))
    for row, (name, lengths, widths) in enumerate(variants):
        for column, (length, width) in enumerate(zip(lengths, widths)):
            label = f"{name}_{ROLES[column]}_frame"
            frame = make_phalanx(length, width, column == 2, label)
            children.append(bd.Pos(row * 25, column * 60, 0) * frame)
    return bd.Compound(label="all_actual_phalanx_variants", children=children)


@model
def phalanx_continuous_r5():
    """The continuous-waist middle proximal phalanx, candidate R5."""
    return make_continuous_phalanx(45, 18, label="middle_proximal_frame")


@model
def phalanx_continuous_supports_r5():
    """The R5 rail's matched guide supports, in the assembled neutral fan."""
    return continuous_supports()


@model
def phalanx_continuous_representative_r5():
    """The continuous rail, as STEP gives it back, with its actual guide supports."""
    host = finish(_middle_place() * warm_host(), "aluminum", "middle_proximal_frame")
    return bd.Compound(label="continuous_rail_and_actual_guide_supports",
                       children=[host, *[copy.copy(s) for s in _leaves(continuous_supports())]])


@model
def fingertip_pad_review():
    """Five mounted pads at real scale, plus an isolated index pad macro specimen."""
    parts = []
    variants = [(f.name, f.lengths[2], f.widths[2]) for f in FINGERS] + [("thumb", 21., 13.)]
    for i, (name, length, width) in enumerate(variants):
        place = bd.Pos(i * 18, 0, 0)
        parts.append(place * make_phalanx(length, width, True, name + "_distal_frame"))
        parts.extend(place * p for p in make_fingertip_pad(name, length, width))
    return bd.Compound(label="five_anatomical_fingertip_pad_mounts", children=parts)


@model
def fingertip_pad_export_repair():
    """Export-stable fingertip pads and their actual mounting hardware."""
    return bd.Compound(label="export_stable_fingertip_pad_systems", children=[s for s, *_ in fingertip_pad_bodies()])


@model
def fingertip_bridge_repair_review():
    """Five mounting bridge export repairs; silicone and all hardware are retained."""
    return bd.Compound(label="fingertip_bridge_export_repair", children=[s for s, *_ in bridge_bodies()])


@model
def fingernail_export_repair_review():
    """Export-stable dorsal nail systems with their unchanged mounting datums."""
    return bd.Compound(label="export_stable_dorsal_nail_systems", children=[s for s, *_ in fingernail_bodies()])


@model
def fingernail_review():
    """Actual assembled terminal fingers: host, palmar pad, dorsal nail, hardware."""
    parts = [p for p, f, s, k in fingernail_bodies()] + [p for p, f, s, k in fingertip_pad_bodies()]
    for finger in FINGERS:
        for i, (length, width) in enumerate(zip(finger.lengths, finger.widths)):
            place = matrix_location(finger_fan_matrix(finger)) * bd.Pos(finger.x, finger.base_y + sum(finger.lengths[:i]), 0)
            parts.append(place * make_phalanx(length, width, i == 2, finger.name + "_" + ROLES[i] + "_frame"))
    for i in (1, 2):
        place = bd.Pos(*THUMB_CMC) * bd.Rot(0, 0, 45) * bd.Pos(0, sum(THUMB_LENGTHS[:i]), 0)
        parts.append(place * make_phalanx(THUMB_LENGTHS[i], THUMB_WIDTHS[i], i == 2, "thumb_" + THUMB_ROLES[i] + "_frame"))
    return bd.Compound(label="five_fingernails_in_anatomical_hand_context", children=parts)


if __name__ == "__main__":
    anatomy_layout()
    phalanx_review()
    phalanx_variants_review()
    phalanx_continuous_r5()
    phalanx_continuous_supports_r5()
    phalanx_continuous_representative_r5()
    fingertip_pad_review()
    fingertip_pad_export_repair()
    fingertip_bridge_repair_review()
    fingernail_export_repair_review()
    fingernail_review()
