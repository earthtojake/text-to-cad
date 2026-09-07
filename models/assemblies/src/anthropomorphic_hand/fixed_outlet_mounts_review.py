"""Four-finger fixed guide outlet hardware; full range acceptance is pending."""
from cadgen import build123d as bd,step
from lib.fixed_guide_mounts import fixed_phalanx_guide_mounts

@step(out='../../STEP/anthropomorphic_hand/fixed_outlet_mounts_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def fixed_outlet_mounts_review():
    return bd.Compound(label='fixed_guide_outlet_mounts',children=[p[0] for p in fixed_phalanx_guide_mounts()])

if __name__=='__main__':fixed_outlet_mounts_review()
