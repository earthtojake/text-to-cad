"""Open forearm chassis with every fixed forearm liner reaction mount."""
from cadgen import build123d as bd,step
from forearm_frame_review import forearm_frame_review
from forearm_guide_banks_review import forearm_guide_banks_review

@step(out='../../STEP/anthropomorphic_hand/forearm_mount_system_review.step')
def forearm_mount_system_review():
    return bd.Compound(label='open_forearm_frame_with_96_mouth_supports',children=[forearm_frame_review(),forearm_guide_banks_review()])

if __name__=='__main__':forearm_mount_system_review()
