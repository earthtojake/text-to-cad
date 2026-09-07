"""Middle-ray fixed guide reaction bank attached to its real palm truss."""
from pathlib import Path
from cadgen import build123d as bd,read_step,step
from lib.palm_guide_mounts import make_palm_ray_mounts

@step(out='../../STEP/anthropomorphic_hand/palm_guide_bank_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def palm_guide_bank_review():
    source=Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand/palm_frame_review.step'
    host=next(c for c in read_step(source).children if c.label=='palm_metacarpal_truss')
    mounts=make_palm_ray_mounts('middle',host)
    return bd.Compound(label='middle_ray_palm_guide_reaction_bank',children=[host,*[p[0] for p in mounts]])

if __name__=='__main__':palm_guide_bank_review()
