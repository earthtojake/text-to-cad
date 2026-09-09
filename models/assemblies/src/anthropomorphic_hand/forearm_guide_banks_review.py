from cadgen import build123d as bd,step
from lib.forearm_guide_mounts import make_forearm_guide_mount_bodies

@step(out='../../STEP/anthropomorphic_hand/forearm_guide_banks_review.step')
def forearm_guide_banks_review():
    return bd.Compound(label='96_forearm_guide_mouths',children=make_forearm_guide_mount_bodies())

if __name__=='__main__':forearm_guide_banks_review()
