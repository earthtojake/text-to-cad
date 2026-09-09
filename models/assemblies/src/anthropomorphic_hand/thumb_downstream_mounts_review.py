from cadgen import build123d as bd,step
from lib.thumb_remaining_mounts import thumb_downstream_mounts
@step(out='../../STEP/anthropomorphic_hand/thumb_downstream_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.015)
def thumb_downstream_mounts_review():
 return bd.Compound(label='thumb_downstream_guide_mounts',children=[s for s,f,y,k in thumb_downstream_mounts()])

if __name__=='__main__':thumb_downstream_mounts_review()
