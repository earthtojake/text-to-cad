"""Two palm frame solids in their assembled neutral relationship."""
from pathlib import Path
from cadgen import build123d as bd,step,read_step
from lib.palm_frame import make_palm_frame

@step(out='../../STEP/anthropomorphic_hand/palm_frame_review.step',mesh_tolerance=.003,mesh_angular_tolerance=.012)
def palm_frame_review():
    main=make_palm_frame()
    little=read_step(Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand/palm_little_review.step')
    common=main.intersect(little)
    if common and sum(s.volume for s in common.solids())>1e-6:
        raise ValueError('palm and fifth metacarpal intersect')
    return bd.Compound(label='palm_frame_and_cupping_metacarpal',children=[main,little])

if __name__=='__main__':palm_frame_review()
