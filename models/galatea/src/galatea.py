"""Galatea: a 1.75 m ivory-and-bronze humanoid. The whole robot, its mechanism and its poses."""

from cad import model

from lib.arm import ARM_LINKS, build_arm
from lib.hand import HAND_LINKS, build_hand
from lib.hardware import Hardware
from lib.head import HEAD_LINKS, build_head
from lib.kit import group, mirror_tree
from lib.leg import LEG_LINKS, build_leg
from lib.rig import animate, articulate
from lib.torso import TRUNK_LINKS, build_trunk


def links():
    """Every link of the robot as a labelled group, by name: the centre links, then each
    left-hand link (l_...) and its mirror image (r_...)."""
    hw = Hardware()
    leg = build_leg(hw)
    trunk = build_trunk(hw, leg["pelvis"])
    arm = build_arm(hw, trunk["shoulder_yoke"])
    hand = build_hand(hw, arm["palm"])
    head = build_head(hw, trunk["neck"])
    nodes = {name: group(name, trunk[name]) for name in TRUNK_LINKS}
    nodes.update({name: group(name, head[name]) for name in HEAD_LINKS})
    for names, parts in ((LEG_LINKS, leg), (ARM_LINKS, arm), (HAND_LINKS, hand)):
        for name in names:
            left = group(f"l_{name}", parts[name])
            nodes[f"l_{name}"] = left
            nodes[f"r_{name}"] = mirror_tree(left, f"r_{name}")
    return nodes


@model
def galatea():
    nodes = links()
    articulate(nodes)
    return animate(group("galatea", list(nodes.values())))


if __name__ == "__main__":
    galatea()
