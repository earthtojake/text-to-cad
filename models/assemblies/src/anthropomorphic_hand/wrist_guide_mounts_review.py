from cadgen import build123d as bd,step
from lib.wrist_guide_mounts import wrist_guide_mounts
@step(out='../../STEP/anthropomorphic_hand/wrist_guide_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.015)
def wrist_guide_mounts_review():
 return bd.Compound(label='six_proximal_drive_mouth_mounts',children=[s for s,f,y,k in wrist_guide_mounts()])
if __name__=='__main__':wrist_guide_mounts_review()
