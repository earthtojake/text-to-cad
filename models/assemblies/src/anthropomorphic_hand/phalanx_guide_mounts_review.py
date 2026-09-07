"""Complete four-finger phalanx guide-comb mounting hardware."""
from cadgen import build123d as bd,step
from index_guide_mounts import index_guide_mounts
from middle_guide_mounts import middle_guide_mounts
from ring_guide_mounts import ring_guide_mounts
from little_guide_mounts import little_guide_mounts

@step(out='../../STEP/anthropomorphic_hand/phalanx_guide_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def phalanx_guide_mounts_review():
    return bd.Compound(label='four_finger_phalanx_guide_mounts',children=[index_guide_mounts(),middle_guide_mounts(),ring_guide_mounts(),little_guide_mounts()])

if __name__=='__main__':phalanx_guide_mounts_review()
