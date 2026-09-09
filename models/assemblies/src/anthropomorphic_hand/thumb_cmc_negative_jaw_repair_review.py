"""A continuous CMC reaction arm routed around both yaw drums.

The accepted mouth, attachment clamp, fastener bores and endpoint tangents
remain fixed. Four interior controls bow upstream, keeping the structural
connection outside the pulleys instead of machining it into disconnected jaws.
"""
from cadgen import build123d as bd,step
from lib.yaw_guide_mounts import make_yaw_reaction_mounts
from lib.layout import THUMB_CMC

@step(out='../../STEP/anthropomorphic_hand/thumb_cmc_negative_jaw_repair_review.step')
def thumb_cmc_negative_jaw_repair_review():
    parts=make_yaw_reaction_mounts(19,'thumb_cmc',7.,9.5,negative_bow_y=-12.)
    selected=[p for p in parts if p.label=='thumb_cmc_negative_yaw_outlet_structural_jaw_1']
    assert len(selected)==1
    return bd.Compound(label='continuous_CMC_reaction_arm',children=[bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*selected[0]])

if __name__=='__main__':thumb_cmc_negative_jaw_repair_review()
