"""Three actual middle-finger phalanges, laid out with joint clearance."""
from cadgen import build123d as bd, step
from lib.phalanx import make_phalanx

@step(out='../../STEP/anthropomorphic_hand/phalanx_review.step',
      mesh_tolerance=.003,mesh_angular_tolerance=.012)
def phalanx_review():
    return bd.Compound(label='skeletal_phalanx_family',children=[
        make_phalanx(45,18,label='middle_proximal_frame'),
        bd.Pos(25,0,0)*make_phalanx(28,15,label='middle_intermediate_frame'),
        bd.Pos(47,0,0)*make_phalanx(17,12,distal=True,label='middle_distal_frame'),
    ])
if __name__=='__main__':
    phalanx_review()
