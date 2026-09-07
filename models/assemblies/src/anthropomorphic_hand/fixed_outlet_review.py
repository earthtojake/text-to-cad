"""Two fixed PIP drive-guide outlets with real removable side-rail mounts."""
from cadgen import build123d as bd,step
from lib.fixed_guide_mounts import make_fixed_outlet_pair
from lib.phalanx import make_phalanx

@step(out='../../STEP/anthropomorphic_hand/fixed_outlet_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def fixed_outlet_review():
    return bd.Compound(label='fixed_pip_guide_outlet_mounts',children=[make_phalanx(45,18),*make_fixed_outlet_pair(45,18,4.5,'middle_pip_drive_guide')])

if __name__=='__main__':fixed_outlet_review()
