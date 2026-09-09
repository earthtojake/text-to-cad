from cadgen import build123d as bd,step
from lib.cup_guide_mounts import cup_guide_mounts
@step(out='../../STEP/anthropomorphic_hand/cup_guide_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.015)
def cup_guide_mounts_review():
 return bd.Compound(label='eighteen_cup_guide_mounts',children=[s for s,f,y,k in cup_guide_mounts()])
if __name__=='__main__':cup_guide_mounts_review()
