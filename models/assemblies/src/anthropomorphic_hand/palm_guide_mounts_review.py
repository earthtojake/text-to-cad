"""Three fixed palm-side reaction banks;42anchored guide endpoints."""
from cadgen import build123d as bd,step
from index_palm_guide_mounts import index_palm_guide_mounts
from middle_palm_guide_mounts import middle_palm_guide_mounts
from ring_palm_guide_mounts import ring_palm_guide_mounts

@step(out='../../STEP/anthropomorphic_hand/palm_guide_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def palm_guide_mounts_review():
    return bd.Compound(label='three_ray_palm_reaction_banks',children=[index_palm_guide_mounts(),middle_palm_guide_mounts(),ring_palm_guide_mounts()])

if __name__=='__main__':palm_guide_mounts_review()
