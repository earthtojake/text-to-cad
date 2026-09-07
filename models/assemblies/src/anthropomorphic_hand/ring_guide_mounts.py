"""Physical reaction combs for the ring finger, in assembled neutral fan."""
from cadgen import build123d as bd, step
from lib.guide_mounts import phalanx_guide_mounts

@step(out='../../STEP/anthropomorphic_hand/ring_guide_mounts.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def ring_guide_mounts():
    return bd.Compound(label='ring_phalanx_guide_mounts',children=[row[0] for row in phalanx_guide_mounts(['ring'])])

if __name__=='__main__':ring_guide_mounts()
