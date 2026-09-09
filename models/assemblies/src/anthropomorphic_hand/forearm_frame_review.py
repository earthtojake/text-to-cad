"""Two native dark forearm frame bodies, in neutral assembly coordinates."""
from cadgen import build123d as bd,step
from lib.forearm_frame import make_forearm_frame_bodies

@step(out='../../STEP/anthropomorphic_hand/forearm_frame_review.step')
def forearm_frame_review():
    return bd.Compound(label='open_forearm_frame',children=make_forearm_frame_bodies())

if __name__=='__main__':forearm_frame_review()
