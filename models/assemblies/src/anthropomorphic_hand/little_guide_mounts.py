"""Physical reaction combs for the little finger, in assembled neutral fan."""
from cadgen import build123d as bd, step
from lib.guide_mounts import phalanx_guide_mounts

@step(out='../../STEP/anthropomorphic_hand/little_guide_mounts.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def little_guide_mounts():
    return bd.Compound(label='little_phalanx_guide_mounts',children=[row[0] for row in phalanx_guide_mounts(['little'])])

if __name__=='__main__':little_guide_mounts()
