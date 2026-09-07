"""Finished keyed fifth metacarpal frame in world assembly coordinates."""
from cadgen import step
from lib.palm_frame import make_little_metacarpal

@step(out='../../STEP/anthropomorphic_hand/palm_little_review.step',mesh_tolerance=.003,mesh_angular_tolerance=.012)
def palm_little_review():
    return make_little_metacarpal()

if __name__=='__main__':palm_little_review()
