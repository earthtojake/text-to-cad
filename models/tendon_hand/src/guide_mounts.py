"""The tendon hand's guide mounts: the reaction combs, fixed outlets and yaw mouths
that hold every liner end, on the fingers and the thumb.

Each model was its own script in `models/tendon_hand/src/`. `phalanx_guide_mounts_review`
called the four finger models; here each finger's combs are one `@memo` stage,
`finger_guide_mounts(finger)` (30-50 s of kernel work each), which the finger's own
model and the four-finger review both place, so a build makes each finger's combs once.
"""

from cadgen import memo, model

import build123d as bd

from lib.bowden_guide import make_bowden_body
from lib.fixed_guide_mounts import fixed_phalanx_guide_mounts, make_fixed_outlet_pair
from lib.guide_mounts import make_phalanx_comb, phalanx_guide_mounts
from lib.layout import THUMB_CMC
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley
from lib.thumb_reaction_arm_candidate import make_candidate
from lib.thumb_remaining_mounts import thumb_downstream_mounts
from lib.universal_carrier import make_universal_carrier
from lib.yaw_guide_mounts import make_yaw_reaction_mounts, yaw_reaction_mounts


@memo
def finger_guide_mounts(finger):
    """One finger's physical reaction combs, in the assembled neutral fan."""
    mounts = bd.Compound(label=f"{finger}_phalanx_guide_mounts",
                         children=[row[0] for row in phalanx_guide_mounts([finger])])
    return mounts


@model
def index_guide_mounts():
    """Physical reaction combs for the index finger, in assembled neutral fan."""
    return finger_guide_mounts("index")


@model
def middle_guide_mounts():
    """Physical reaction combs for the middle finger, in assembled neutral fan."""
    return finger_guide_mounts("middle")


@model
def ring_guide_mounts():
    """Physical reaction combs for the ring finger, in assembled neutral fan."""
    return finger_guide_mounts("ring")


@model
def little_guide_mounts():
    """Physical reaction combs for the little finger, in assembled neutral fan."""
    return finger_guide_mounts("little")


@model
def phalanx_guide_mounts_review():
    """Complete four-finger phalanx guide-comb mounting hardware."""
    return bd.Compound(label="four_finger_phalanx_guide_mounts",
                       children=[finger_guide_mounts(finger) for finger in ("index", "middle", "ring", "little")])


@model
def guide_comb_review():
    """Exact mid-finger reaction comb and original skeletal rail mounting study."""
    pieces = [make_phalanx(45, 18, label="original_middle_proximal_frame")]
    pieces += make_phalanx_comb(45, 18, 12.25, [-4.2, -3., 3., 4.2], "middle_mcp_outlet_comb")
    for lane in [-4.2, -3., 3., 4.2]:
        path = [{"kind": "bezier", "points": [[lane, 7, 0], [lane, 10, 0], [lane, 14, 0], [lane, 18, 0]]}]
        pieces.append(make_bowden_body(path, f"lane_{lane}_liner", liner=True))
        pieces.append(make_bowden_body(path, f"lane_{lane}_tendon"))
    return bd.Compound(label="supported_split_reaction_comb_review", children=pieces)


@model
def fixed_outlet_review():
    """Two fixed PIP drive-guide outlets with real removable side-rail mounts."""
    return bd.Compound(label="fixed_pip_guide_outlet_mounts",
                       children=[make_phalanx(45, 18), *make_fixed_outlet_pair(45, 18, 4.5, "middle_pip_drive_guide")])


@model
def fixed_outlet_mounts_review():
    """Four-finger fixed guide outlet hardware; full range acceptance is pending."""
    return bd.Compound(label="fixed_guide_outlet_mounts", children=[p[0] for p in fixed_phalanx_guide_mounts()])


@model
def yaw_reaction_mounts_review():
    """Eight carrier-anchored finger MCP yaw-reaction outlet mouths."""
    return bd.Compound(label="eight_finger_yaw_reaction_outlet_mounts", children=[s for s, f, y, k in yaw_reaction_mounts()])


@model
def yaw_outlet_mount_review():
    """Reaction mouths attached to the universal carrier beside both drive drums."""
    p = [make_universal_carrier(), *make_yaw_reaction_mounts(18, "middle_mcp")]
    for sign in (-1, 1):
        p.append(bd.Pos(sign * .9, 0, 0) * bd.Rot(0, 90, 0) * make_pulley(5.5, label=f"flexion_{sign}_pulley"))
    return bd.Compound(label="yaw_reaction_open_mouth_clamps", children=p)


@model
def yaw_guide_macro_review():
    """The index MCP's yaw mouths on its actual carrier, beside both flexion drums."""
    parts = make_yaw_reaction_mounts(18, "index_mcp")
    parts.append(make_universal_carrier(phalanx_width=18, label="index_mcp_actual_carrier"))
    for sign in (-1, 1):
        p = bd.Pos(sign * .9, 0, 0) * bd.Rot(0, 90, 0) * make_pulley(5.5)
        p.label = "index_mcp_flexion_" + str(sign) + "_actual_pulley"
        parts.append(p)
    return bd.Compound(label="mounted_index_yaw_mouth_macro", children=parts)


@model
def thumb_cmc_negative_jaw_repair_review():
    """A continuous CMC reaction arm routed around both yaw drums.

    The accepted mouth, attachment clamp, fastener bores and endpoint tangents remain
    fixed. Four interior controls bow upstream, keeping the structural connection
    outside the pulleys instead of machining it into disconnected jaws."""
    parts = make_yaw_reaction_mounts(19, "thumb_cmc", 7., 9.5, negative_bow_y=-12.)
    selected = [p for p in parts if p.label == "thumb_cmc_negative_yaw_outlet_structural_jaw_1"]
    assert len(selected) == 1
    return bd.Compound(label="continuous_CMC_reaction_arm", children=[bd.Pos(*THUMB_CMC) * bd.Rot(0, 0, 45) * selected[0]])


@model
def thumb_downstream_mounts_review():
    """The thumb's downstream guide mounts."""
    return bd.Compound(label="thumb_downstream_guide_mounts", children=[s for s, f, y, k in thumb_downstream_mounts()])


@model
def thumb_reaction_arm_context_candidate():
    """Context-constrained reaction-arm candidate; not yet a clearance certificate."""
    shape = bd.Pos(*THUMB_CMC) * bd.Rot(0, 0, 45) * make_candidate(bow_x=4., bow_y=-14.)
    return bd.Compound(label="CMC_reaction_arm_context_candidate", children=[shape])


if __name__ == "__main__":
    index_guide_mounts()
    middle_guide_mounts()
    ring_guide_mounts()
    little_guide_mounts()
    phalanx_guide_mounts_review()
    guide_comb_review()
    fixed_outlet_review()
    fixed_outlet_mounts_review()
    yaw_reaction_mounts_review()
    yaw_outlet_mount_review()
    yaw_guide_macro_review()
    thumb_cmc_negative_jaw_repair_review()
    thumb_downstream_mounts_review()
    thumb_reaction_arm_context_candidate()
