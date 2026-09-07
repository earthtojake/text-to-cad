"""Eight carrier-anchored finger MCP yaw-reaction outlet mouths."""
from cadgen import build123d as bd,step
from lib.yaw_guide_mounts import yaw_reaction_mounts

@step(out='../../STEP/anthropomorphic_hand/yaw_reaction_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.015)
def yaw_reaction_mounts_review():
    return bd.Compound(label='eight_finger_yaw_reaction_outlet_mounts',children=[s for s,f,y,k in yaw_reaction_mounts()])

if __name__=='__main__':yaw_reaction_mounts_review()
