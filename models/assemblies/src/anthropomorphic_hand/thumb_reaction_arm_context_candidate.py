"""Context-constrained reaction-arm candidate; not yet a clearance certificate."""
from cadgen import build123d as bd,step
from lib.thumb_reaction_arm_candidate import make_candidate
from lib.layout import THUMB_CMC

@step(out='../../STEP/anthropomorphic_hand/thumb_reaction_arm_context_candidate.step')
def thumb_reaction_arm_context_candidate():
    shape=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*make_candidate(bow_x=4.,bow_y=-14.)
    return bd.Compound(label='CMC_reaction_arm_context_candidate',children=[shape])
if __name__=='__main__':thumb_reaction_arm_context_candidate()
