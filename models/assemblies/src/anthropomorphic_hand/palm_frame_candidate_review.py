"""Review the rebuilt route-reserved palm before integration."""
from cadgen import step
from lib.palm_frame_candidate import make_palm_frame
@step(out='../../STEP/anthropomorphic_hand/palm_frame_candidate_review.step',mesh_tolerance=.012,mesh_angular_tolerance=.05)
def palm_frame_candidate_review():return make_palm_frame()
if __name__=='__main__':palm_frame_candidate_review()
